# -*- coding: utf-8 -*-

import os
import urllib.parse
from itertools import tee
from shutil import copy2
from typing import List

import pandas as pd
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QInputDialog, QMessageBox

import processing
from qgis.analysis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.utils import *

class ProcessPath(object):
    """處理站間路徑相關"""
    def save(self, path_list: List[int], save_dir: str, show_path: bool = False):
        """把站牌間路徑儲存成文字檔"""
        path_str = ','.join(map(str, path_list))
        path_path = os.path.join(save_dir, '{}_{}.txt'.format(path_list[0], path_list[-1])) #路徑的路徑
        path_file = open(path_path, 'w')
        path_file.write(path_str)
        path_file.close()
        if show_path:
            #跳出視窗展示儲存的結果
            QMessageBox().information(None, \
                '路徑已儲存', '{} -> {}\n{}'.format(str(path_list[0]), str(path_list[-1]), path_str))

    def load(self, ori_node: int, des_node: int, load_dir: str, show_path: bool = False):
        """讀取已經儲存的站牌間路徑"""
        path_path = os.path.join(load_dir, '{}_{}.txt'.format(ori_node, des_node))
        if_saved = os.path.isfile(path_path)
        
        if if_saved:
            path_file = open(path_path, 'r')
            path_str = path_file.read()
            path_file.close()
            if show_path:
                QMessageBox().information(None, \
                    '路徑已載入', '{} -> {}\n{}'.format(ori_node, des_node, path_str))
            path = path_str.split(',')
            path = list(map(int, path))
            path = list(map(abs, path))
        else:
            path = [ori_node, 0, des_node]
        
        return path, not if_saved

class PrepareRoute(object):
    """匯入公車路線相關"""
    def choose_route(self, data_dir, zone2dir):
        """選擇路線"""
        path_check = True
        
        while True:
            routeUID, OK = QInputDialog().getText(None, '輸入UID', '請輸入路線UID >w<:')

            if OK:
                #讀取站牌序列的csv
                route_zone = routeUID[0:3].upper() #讀取公車主管機關代碼(MIA, TXG, CHA, NAN, YUN, THB)
                if route_zone not in zone2dir: #檢查是不是在目標縣市
                    QMessageBox().information(None, '錯誤', '路線不在目標縣市')
                    continue
                route_dir = os.path.join(data_dir, zone2dir[route_zone]) #路線檔所在的資料夾路徑
                route_list = pd.read_csv(os.path.join(route_dir, 'route_list.csv')) #匯入該區域的路徑列表

                candidate_route = route_list[route_list.SubRouteUID == routeUID]
                
                if candidate_route.shape[0] == 2:
                    while True:
                        direction, dir_OK = QInputDialog().getItem(None, '去返程', '請選取路線方向', \
                            list(map(str, candidate_route.Direction.tolist())), editable=False)
                        if dir_OK:
                            break
                elif candidate_route.shape[0] == 1:
                    direction = str(candidate_route.Direction.tolist()[0])
                else:
                    QMessageBox().information(None, '錯誤', '路線不存在')
                    continue

                if candidate_route.if_pass_zone[candidate_route.Direction == int(direction)].tolist()[0] == 0:
                    QMessageBox().information(None, '錯誤', '這條路線不在目標區域裡\n不用處理啦~')
                else:
                    SubRouteName = candidate_route.SubRouteName[candidate_route.Direction == int(direction)].tolist()[0]
                    route_spec = [routeUID, SubRouteName, direction, route_dir]
                    break
            else:
                route_spec = []
                break

        return route_spec, OK
    
    def read_seq_to_UID(self, data_dir, route_spec):
        """讀取站序與UID的對應"""
        file_path = os.path.join(data_dir, '{}.csv'.format(route_spec[0:3]))
        route_stops = pd.from_csv(file_path)
        route_stops.set_index('StopSequence', inplace=True)
        return route_stops

def pairwise(self, iterable):
    """參考https://stackoverflow.com/questions/5764782/iterate-through-pairs-of-items-in-a-python-list?lq=1\n
    s -> (s0, s1), (s1, s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)
    
def append_to_final_list(self, bus_route, section_result):
    """把區間的結果加進最終結果"""
    #如果是第一個區間就加進最終結果的list，不是的話就沿用現有結果
    if len(bus_route) == 0:
        bus_route.append(section_result[0])
    #通過節點用負值加入最終結果的list
    for n in range(1, len(section_result) - 1):
        bus_route.append(-section_result[n])
    #把區間的終點加入最終結果的list
    bus_route.append(section_result[-1])
    return bus_route

def main():
    data_dir = 'P:/09091-中臺區域模式/Working/04_交通資料/公車站牌/new/'
    result_dir = 'P:/09091-中臺區域模式/Working/04_交通資料/公車站牌/new/'

    checked_path_dir = os.path.join(result_dir, '03_checked_path')
    result_route_dir = os.path.join(result_dir, '05_final_result_route')

    zone2dir = {
        'MIA': 'City/MiaoliCounty/',
        'TXG': 'City/Taichung/',
        'CHA': 'City/ChanghuaCounty/',
        'NAN': 'City/NantouCounty/',
        'YUN': 'City/YunlinCounty/',
        'THB': 'InterCity'
        }
    vlayer = {}

    while True:
        route_spec, OK = PrepareRoute().choose_route(data_dir, zone2dir)

        if OK:
            route_UID2node, if_exist = ProcessUID2node().read_route(route_UID2node_dir, route_spec)
            
            if not if_exist:
                QMessageBox().information(None, '掰掰', '這條路線還沒處理過喔\n請下次再來')
                continue
            
            else:
                final_bus_route = [] #最終輸出這個
                for s1, s2 in FindPath().pairwise(vlayer['route'].getFeatures()):
                    StopUID = [s1.attributes()[1], s2.attributes()[1]]

                    #計算起終點對應的ID
                    OD_info, in_zone = FindPath().get_node(vlayer['node'], StopUID2node, StopUID, init_path_dir)

                    if in_zone:
                        if OD_info[3][0] != OD_info[3][1]:
                            #讀取已確認的路徑
                            passed_node_list, no_checked_path = ProcessPath().load(
                                OD_info[3][0], OD_info[3][1], checked_path_dir)
                            if no_checked_path:
                                #讀取已輸出的路徑
                                passed_node_list, no_saved_path = ProcessPath().load(
                                    OD_info[3][0], OD_info[3][1], init_path_dir)
                                if not no_saved_path:
                                    path_layer = ProcessResult().display_path(vlayer['node'], passed_node_list)
                                    passed_node_list = ProcessResult().manually_input(
                                        StopUID, passed_node_list, init_path_dir, frthr_inspct_dir, checked_path_dir)
                                else:
                                    passed_node_list = [OD_info[3][0], 0, OD_info[3][1]]
                                    manual_input = QMessageBox().information(None, '載入失敗', '未有該區間已輸出路徑\n要手動輸入嗎？', \
                                        buttons=QMessageBox.Ok|QMessageBox.Cancel)
                                    if manual_input == QMessageBox.Ok:
                                        path_layer = ProcessResult().display_path(vlayer['node'], passed_node_list)
                                        passed_node_list = ProcessResult().manually_input(
                                            StopUID, passed_node_list, init_path_dir, frthr_inspct_dir, checked_path_dir)
                                QgsProject.instance().removeMapLayer(path_layer)
                            else:
                                QMessageBox().information(None, '恭喜', '這個區間已經確認過囉')
                        else:
                            QMessageBox().information(None, \
                                '點號相同', '{} -> {}\n兩站同點'.format(str(OD_info[3][0]), str(OD_info[3][1])))
                    else:
                        QMessageBox().information(None, '站點超出區域', '其中一站不在計畫區域')
                        ProcessPath().save_outlier(StopUID[0], StopUID[1], outbnd_path_dir)
    #接上已經找到的路，沒停靠的通過節點在這邊才加負數
    final_bus_route = append_to_final_list(final_bus_route, passed_node_list)

