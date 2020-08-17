# -*- coding: utf-8 -*-

import os
import sys

from pandas import read_csv
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox


class ProcessStopList(object):
    """處理站間路徑相關"""
    def save(self, path_list: list, save_dir: str, route_spec: list):
        """把路線的站牌間路徑儲存成文字檔"""
        path_str = ', '.join(map(str, path_list))
        path_file = open(
            os.path.join(save_dir, '{}.txt'.format('_'.join(route_spec[0:3]))), 'w'
        )
        path_file.write(path_str)
        path_file.close()

    def load(self, OD_node: list, load_dir: str):
        """讀取已經儲存的站牌間路徑"""
        path_path = os.path.join(load_dir, '{}_{}.txt'.format(OD_node[0], OD_node[1]))
        if_saved = os.path.isfile(path_path)
        
        if if_saved:
            path_file = open(path_path, 'r')
            path_str = path_file.read()
            path_file.close()
            path = path_str.split(',')
            path = list(map(int, path))
            path = list(map(abs, path))
        else:
            path = [OD_node[0], 0, OD_node[1]]
        
        return path, not if_saved

class ProcessRoute(object):
    """處理公車路線相關"""
    def choose_route(self, data_dir, zone2dir):
        """選擇路線"""
        route_spec = []
        while True:
            routeUID, OK = QInputDialog().getText(None, '輸入UID', '請輸入路線UID >w<:')

            if OK:
                #讀取站牌序列的csv
                routeUID = routeUID.upper()
                route_zone = routeUID[0:3] #讀取公車主管機關代碼(MIA, TXG, CHA, NAN, YUN, THB)
                if route_zone not in zone2dir: #檢查是不是在目標縣市
                    QMessageBox().information(None, '錯誤', '路線未經目標縣市')
                    continue
                route_dir = os.path.join(data_dir, zone2dir[route_zone]) #路線檔所在的資料夾路徑
                route_list = read_csv(os.path.join(route_dir, 'route_list.csv')) #匯入該區域的路徑列表

                candidate = route_list[route_list.SubRouteUID == routeUID]
                
                if candidate.shape[0] == 2:
                    direction, dir_OK = QInputDialog().getItem(
                        None, '去返程', '請選取路線方向',
                        list(map(str, candidate.Direction.tolist())), editable=False
                    )
                    if not dir_OK:
                        continue
                elif candidate.shape[0] == 1:
                    direction = str(candidate.Direction.tolist()[0])
                else:
                    QMessageBox().information(None, '錯誤', '路線不存在')
                    continue

                if candidate.if_pass_zone[candidate.Direction == int(direction)].tolist()[0] == 0:
                    QMessageBox().information(None, '錯誤', '這條路線不在目標區域裡\n不用處理啦~')
                else:
                    SubRouteName = candidate.SubRouteName[candidate.Direction == int(direction)].tolist()[0]
                    route_spec = [routeUID, SubRouteName, direction, route_dir]
                    break
            else:
                break

        return route_spec, OK

    def read_route_UID2node(self, file_dir, route_spec):
        """讀取UID到點號的對應"""
        route_chart_path = os.path.join(file_dir, '{}.csv'.format('_'.join(route_spec[0:3])))
        saved_exist = os.path.isfile(route_chart_path)
        if saved_exist:
            route_UID2node = read_csv(route_chart_path)
            route_UID2node.set_index('InputID', inplace=True)
        else:
            route_UID2node = []
        return route_UID2node, saved_exist

    def append_to_final_list(self, bus_route, section_result):
        """把區間的結果加進最終結果"""
        #如果是第一個區間就加進最終結果的list，不是的話就沿用現有結果
        if len(bus_route) == 0:
            bus_route.append(section_result[0])
        #通過節點用負值加入最終結果的list
        for node in section_result[1:-1]:
            bus_route.append(-node)
        #把區間的終點加入最終結果的list
        if bus_route[-1] != section_result[-1]:
            bus_route.append(section_result[-1])
        return bus_route

def main():
    app = QApplication(sys.argv)
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

    while True:
        route_spec, OK = ProcessRoute().choose_route(data_dir, zone2dir)

        if OK:
            route_UID2node, if_exist = ProcessRoute().read_route_UID2node(route_UID2node_dir, route_spec)
            
            if not if_exist:
                QMessageBox().information(None, '掰噗', '這條路線還沒處理過喔\n請下次再來')
            
            else:
                node_list = route_UID2node['TargetID'].to_list()
                final_bus_route = [] #最終輸出這個
                no_failed_section = True
                for OD_node in zip(node_list, node_list[1:]):
                    #計算起終點對應的ID
                    section_name = '{} -> {}'.format(OD_node[0], OD_node[1])
                    if OD_node[0] != 0 and OD_node[1] != 0:
                        if OD_node[0] != OD_node[1]:
                            #讀取已確認的路徑
                            path_list, no_checked_path = ProcessStopList().load(
                                OD_node, checked_path_dir)
                            if no_checked_path:
                                QMessageBox().information(
                                    None, '失敗 ╮(╯_╰)╭', 
                                    '本區間({})未確認'.format(section_name)
                                )
                                no_failed_section = False
                    else:
                        QMessageBox().information(
                            None, '失敗 ╮(╯_╰)╭', 
                            '本區間({})有一為0'.format(section_name)
                        )
                        no_failed_section = False

                    if no_failed_section:
                        #接上已經找到的路，沒停靠的通過節點在這邊才加負數
                        final_bus_route = ProcessRoute().append_to_final_list(final_bus_route, path_list)

                if no_failed_section:
                    ProcessStopList().save(final_bus_route, result_route_dir, route_spec)
                    QMessageBox().information(None, '耶咿(ﾉ>ω<)ﾉ', '站序製作完成')
                else:
                    QMessageBox().information(None, '嗚嗚。･ﾟ･(つд`ﾟ)･ﾟ･', '本路線還沒完全確認過')
        else:
            second_check = QMessageBox().information(None, '確認', '真的要結束嗎？', \
                    buttons=QMessageBox.Yes|QMessageBox.No)
            if second_check == QMessageBox.Yes:
                break

main()
