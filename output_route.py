# -*- coding: utf-8 -*-

import os

from pandas import read_csv


def save_route(path_list: list, save_dir: str, route_spec: list):
    """把路線的站牌間路徑儲存成文字檔"""
    path_str = ', '.join(map(str, path_list))
    path_file = open(
        os.path.join(save_dir, '{}.txt'.format('_'.join(route_spec[0:3]))), 'w'
    )
    path_file.write(path_str)
    path_file.close()

def load_path(OD_node: list, load_dir: str):
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

def choose_route(data_dir, zone2dir):
    """選擇路線"""
    route_spec = []
    while True:
        routeUID = input('請輸入路線UID (要跳出則輸入0): ')
        OK = routeUID != '0'

        if OK:
            #讀取站牌序列的csv
            routeUID = routeUID.upper()
            route_zone = routeUID[0:3] #讀取公車主管機關代碼(MIA, TXG, CHA, NAN, YUN, THB)
            if route_zone not in zone2dir: #檢查是不是在目標縣市
                print('錯誤: 路線未經目標縣市')
                continue
            route_dir = os.path.join(data_dir, zone2dir[route_zone]) #路線檔所在的資料夾路徑
            route_list = read_csv(os.path.join(route_dir, 'route_list.csv')) #匯入該區域的路徑列表

            candidate = route_list[route_list.SubRouteUID == routeUID]
            
            if candidate.shape[0] == 2:
                direction = input(
                    '請輸入路線方向[{}]: '.format(
                        ', '.join(map(str, candidate.Direction.tolist()))
                    )
                )
                if direction not in map(str, candidate.Direction.tolist()):
                    print('方向輸入錯誤')
                    continue
            elif candidate.shape[0] == 1:
                direction = str(candidate.Direction.tolist()[0])
            else:
                print('錯誤: 路線不存在')
                continue

            if candidate.if_pass_zone[candidate.Direction == int(direction)].tolist()[0] == 0:
                print('錯誤: 這條路線未經計畫區域')
            else:
                SubRouteName = candidate.SubRouteName[candidate.Direction == int(direction)].tolist()[0]
                route_spec = [routeUID, SubRouteName, direction, route_dir]
                break
        else:
            break

    return route_spec, OK

def read_node_list(file_dir, route_spec):
    """讀取UID到點號的對應"""
    route_chart_path = os.path.join(file_dir, '{}.csv'.format('_'.join(route_spec[0:3])))
    if os.path.isfile(route_chart_path):
        route_UID2node = read_csv(route_chart_path)
        node_list = route_UID2node['TargetID'].to_list()
    else:
        node_list = []
    return node_list

def append_path(bus_route, section_result):
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

def progress_bar(current_num: int, total_num: int):
    """ Display the progress bar if the result is printed to the text file. """
    print(
        '\r[{:<50}] ({}/{})'.format(
            '=' * int(current_num / (2 * total_num) * 100), current_num, total_num
        ), 
        end=''
    )

def main():
    P_drive = 'P:/09091-中臺區域模式/Working/'
    data_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')
    result_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')

    route_UID2node_dir = os.path.join(result_dir, '00_route_UID2node')
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
        route_spec, OK = choose_route(data_dir, zone2dir)

        if OK:
            node_list = read_node_list(route_UID2node_dir, route_spec)
            
            if len(node_list) == 0:
                print('掰噗: 這條路線還沒處理過喔，請下次再來')

            else:
                final_bus_route = [] #最終輸出這個
                no_failed_section = True
                num_path = len(node_list) - 1
                for i, OD_node in enumerate(zip(node_list, node_list[1:])):
                    #計算起終點對應的ID
                    if OD_node[0] != OD_node[1]:
                        if OD_node[0] != 0 and OD_node[1] != 0:
                            #讀取已確認的路徑
                            path_list, no_checked_path = load_path(OD_node, checked_path_dir)
                            if no_checked_path:
                                print('\n失敗: [{} -> {}] 未確認'.format(OD_node[0], OD_node[1]))
                                no_failed_section = False
                        else:
                            print('\n失敗: [{} -> {}] 有一為0'.format(OD_node[0], OD_node[1]))
                            no_failed_section = False

                        if no_failed_section:
                            #接上已經找到的路，沒停靠的通過節點在這邊才加負數
                            progress_bar(i + 1, num_path)
                            final_bus_route = append_path(final_bus_route, path_list)

                if no_failed_section:
                    save_route(final_bus_route, result_route_dir, route_spec)
                    print('\n耶咿 (ﾉ>ω<)ﾉ: 站序製作完成')
                else:
                    print('嗚嗚 。･ﾟ･(つд`ﾟ)･ﾟ･: 本路線還沒完全確認過')
        else:
            second_check = input('真的要結束嗎? [Y/N]: ')
            if second_check == 'Y' or second_check == 'y':
                break

if __name__ == '__main__':
    main()
