# -*- coding: utf-8 -*-

import os
# import sys
import urllib.parse
from shutil import copy2
from typing import List

import pandas as pd
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox


class ProcessStopList(object):
    """處理站間路徑相關"""
    def save(self, path_list: List[int], save_dir: str, route_spec: List[str] = []):
        """
        把站牌間路徑儲存成文字檔\n
        如果有輸入route_spec，就用路線作為檔名\n
        否則以起迄點當作檔名
        """
        if route_spec == []:
            file_name = '{}_{}.txt'.format(path_list[0], path_list[-1])
        else:
            file_name = '{}.txt'.format('_'.join(route_spec[0:3]))
        path_str = ', '.join(map(str, path_list))
        path_path = os.path.join(save_dir, file_name) #路徑的路徑
        path_file = open(path_path, 'w')
        path_file.write(path_str)
        path_file.close()

    def load(self, ori_node: int, des_node: int, load_dir: str):
        """讀取已經儲存的站牌間路徑"""
        path_path = os.path.join(load_dir, '{}_{}.txt'.format(ori_node, des_node))
        if_saved = os.path.isfile(path_path)
        
        if if_saved:
            path_file = open(path_path, 'r')
            path_str = path_file.read()
            path_file.close()
            path = path_str.split(',')
            path = list(map(int, path))
            path = list(map(abs, path))
        else:
            path = [ori_node, 0, des_node]
        
        return path, not if_saved

    def load_outbound_path(self, ori_UID: str, des_UID: str, load_dir: str):
        """讀取有到區外的站牌間路徑"""
        path_path = os.path.join(load_dir, '{}_{}.txt'.format(ori_UID, des_UID))
        if_sucess = os.path.isfile(path_path)
        path = []

        if if_sucess:
            path_file = open(path_path, 'r')
            path_str = path_file.read()
            path_file.close()
            if path_str != 'to be filled...':
                if path_str != '':
                    path = path_str.split(',')
                    path = list(map(int, path))
                    path = list(map(abs, path))
            else:
                if_sucess = False
        
        return path, not if_sucess

class ProcessRoute(object):
    """處理公車路線相關"""
    def choose_route(self, data_dir, zone2dir):
        """選擇路線"""
        path_check = True
        
        while True:
            routeUID, OK = QInputDialog().getText(None, '輸入UID', '請輸入路線UID >w<:')

            if OK:
                #讀取站牌序列的csv
                routeUID = routeUID.upper()
                route_zone = routeUID[0:3] #讀取公車主管機關代碼(MIA, TXG, CHA, NAN, YUN, THB)
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
                route_dir = []
                break

        return route_spec, route_dir, OK
    
    def read_route_seq(self, data_dir, route_spec):
        """讀取站序與UID的對應"""
        file_path = os.path.join(data_dir, '{}.csv'.format('_'.join(route_spec[0:3])))
        route_stops = pd.read_csv(file_path)
        route_stops.set_index('StopSequence', inplace=True)
        stop_seq = list(sorted(map(int, route_stops.index.to_list())))
        return route_stops, stop_seq

    def read_route_UID2node(self, file_dir, route_spec):
        """讀取UID到點號的對應"""
        route_chart_path = os.path.join(file_dir, '{}.csv'.format('_'.join(route_spec[0:3])))
        saved_exist = os.path.isfile(route_chart_path)
        if saved_exist:
            route_UID2node = pd.read_csv(route_chart_path)
            route_UID2node.set_index('InputID', inplace=True)
        else:
            route_UID2node = []
        return route_UID2node, saved_exist
    
    def get_node(self, UID_table: pd.DataFrame, OD_UID: List[str]):
        """取得路徑起終點的點號"""
        stop_in_zone = True
        start_node = UID_table.loc[[OD_UID[0]], 'TargetID'].tolist()[0]
        end_node = UID_table.loc[[OD_UID[1]], 'TargetID'].tolist()[0]

        if start_node == 0 or end_node == 0:
            stop_in_zone = False

        return [start_node, end_node], stop_in_zone

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
    # app = QApplication(sys.argv)
    P_drive = 'P:/09091-中臺區域模式/Working/'
    data_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')
    result_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')

    route_UID2node_dir = os.path.join(data_dir, '00_route_UID2node')
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
        route_spec, route_dir, OK = ProcessRoute().choose_route(data_dir, zone2dir)

        if OK:
            route_stops, stop_seq = ProcessRoute().read_route_seq(route_dir, route_spec)
            route_UID2node, if_exist = ProcessRoute().read_route_UID2node(route_UID2node_dir, route_spec)
            
            if not if_exist:
                QMessageBox().information(None, '掰噗', '這條路線還沒處理過喔\n請下次再來')
                continue
            
            else:
                final_bus_route = [] #最終輸出這個
                failed_section = [] #發生錯誤的區間
                for s1, s2 in zip(stop_seq, stop_seq[1:]):
                    StopUID = [route_stops.StopUID[s1], route_stops.StopUID[s2]]

                    #計算起終點對應的ID
                    OD_info, in_zone = ProcessRoute().get_node(route_UID2node, StopUID)
                    section_name = '{} ({}) -> {} ({})'.format(s1, OD_info[0], s2, OD_info[1])

                    if in_zone:
                        if OD_info[0] != OD_info[1]:
                            #讀取已確認的路徑
                            passed_node_list, no_checked_path = ProcessStopList().load(
                                OD_info[0], OD_info[1], checked_path_dir)
                            if no_checked_path:
                                QMessageBox().information(None, '失敗 ╮(╯_╰)╭', '這個區間還沒有確認過喔\n{}'.format(section_name))
                                failed_section.append(section_name)
                        else:
                            QMessageBox().information(None, \
                                '點號相同', '{} -> {}\n兩站同點'.format(str(OD_info[0]), str(OD_info[1])))
                    else:
                        QMessageBox().information(None, '站點超出區域', '其中一站不在計畫區域')
                        passed_node_list, no_checked_path = ProcessStopList().load_outbound_path(
                            StopUID[0], StopUID[1], checked_path_dir)
                        if no_checked_path:
                            QMessageBox().information(None, '失敗 ╮(╯_╰)╭', '這個區間還沒有確認過喔\n{}'.format(section_name))
                            failed_section.append(section_name)

                    if len(failed_section) == 0:
                        #接上已經找到的路，沒停靠的通過節點在這邊才加負數
                        final_bus_route = ProcessRoute().append_to_final_list(final_bus_route, passed_node_list)

                if len(failed_section) == 0:
                    ProcessStopList().save(final_bus_route, result_route_dir, route_spec)
                    QMessageBox().information(None, '耶咿(ﾉ>ω<)ﾉ', '站序製作完成')
                else:
                    QMessageBox().information(
                        None, '嗚嗚。･ﾟ･(つд`ﾟ)･ﾟ･', 
                        '以下區間發生錯誤：\n{}'.format('\n'.join(failed_section)))
        else:
            second_check = QMessageBox().information(None, '再次確認', '真的要結束嗎？', \
                    buttons=QMessageBox.Ok|QMessageBox.Cancel)
            if second_check == QMessageBox.Ok:
                break

main()
