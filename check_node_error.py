# -*- coding: utf-8 -*-

import os
import re
import csv
from math import cos, radians, sin, sqrt, tan
from pathlib import Path


def check_csv_file(file_name: str, file_type: str, pass_all: bool):
    while not os.path.isfile(file_name) and not pass_all:
        while True:
            new_input = input(
                '{}不存在(檔名：{})\n'
                '是否重新輸入檔名？(Y/N)'.format(file_type, file_name)
            )
            new_input = new_input.upper()
            if new_input == 'Y':
                new_input = True
                break
            elif new_input == 'N':
                new_input = False
                break
        
        if new_input:
            file_name = input('請輸入{}的檔名(包含副檔名)：'.format(file_type))
        else:
            pass_all = True
            input('無法取得{}，結束程式'.format(file_type))

    return file_name, pass_all

class ImportNetwork():
    @staticmethod
    def get_road_list(road_csv_path: str, excluded_roadtype: list):
        road_dict = {}
        with open(road_csv_path, newline='', encoding='utf-8') as road_csv:
            road_row = csv.reader(road_csv)
            first = True
            for r in road_row:
                if first:
                    roadtype = r.index('ROADTYPE')
                    length = r.index('LENGTH')
                    A = r.index('A')
                    B = r.index('B')
                    dir = r.index('DIR')
                    spdclass = r.index('SPDCLASS')
                    first = False
                else:
                    if r[roadtype] not in excluded_roadtype:
                        if int(r[spdclass]) <= 2:
                            speed = 100
                        elif int(r[spdclass]) <= 4:
                            speed = 90
                        elif int(r[spdclass]) <= 19:
                            speed = 60
                        elif int(r[spdclass]) <= 34:
                            speed = 50
                        else:
                            speed = 40
                        travel_time = float(r[length]) / speed
                        if int(r[dir]) == 0 or int(r[dir]) == 2:
                            road_dict[(int(r[A]), int(r[B]))] = travel_time
                            road_dict[(int(r[B]), int(r[A]))] = travel_time
                        elif int(r[dir]) == 1:
                            road_dict[(int(r[A]), int(r[B]))] = travel_time
                        else:
                            road_dict[(int(r[B]), int(r[A]))] = travel_time
        
        print('完成道路讀取...')
        return road_dict

    @staticmethod
    def get_node_list(node_csv_path: str, min_N: int, max_N: int):
        node_list = {}
        with open(node_csv_path, newline='', encoding='utf-8') as node_csv:
            node_row = csv.reader(node_csv)
            first = True
            for n in node_row:
                if first:
                    N = n.index('N')
                    X = n.index('X')
                    Y = n.index('Y')
                    first = False
                else:
                    if int(n[N]) <= max_N and int(n[N]) >= min_N:
                        node_list[int(n[N])] = LatLonToTWD97().convert(radians(float(n[Y])), radians(float(n[X])))
            
        print('完成節點讀取...')
        return node_list

    @staticmethod
    def generate_tree(node_dict: dict, road_dict: dict):
        road_tree = {n: [] for n in node_dict}
        for r in road_dict:
            road_tree[r[0]].append(r[1])
        print('完成相鄰節點建立...')
        return road_tree

class ShortestPath(object):
    """尋找最短路徑"""

    def __init__(self, node_dict: dict, road_dict: dict, road_tree: dict):
        self.node_dict = node_dict
        self.road_dict = road_dict
        self.road_tree = road_tree

    def find_shortest_path(self, OD_node: list, max_level: int = 1000):
        p1 = OD_node[0]
        p2 = OD_node[1]
        # 兩點相鄰
        if (p1, p2) in self.road_dict:
            return [p1, p2], self.road_dict[(p1, p2)]

        if p1 in self.node_dict and p2 in self.node_dict:
            path, distance = self.a_star_alg(p1, p2, max_level)
            return path, distance

    def a_star_alg(self, p1: int, p2: int, max_level: int = 1000):
        """Returns a list of nodes as a path from the given start to the given end in the given road network"""
        
        # Create start and end node
        start_node = Node(None, p1, self.node_dict[p1])
        start_node.g = start_node.h = start_node.f = 0
        end_node = Node(None, p2, self.node_dict[p2])
        end_node.g = end_node.h = end_node.f = 0

        # Initialize both open and closed list
        open_list = []
        closed_list = []

        # Add the start node
        open_list.append(start_node)

        # Loop until you find the end
        level = 0
        while len(open_list) > 0 and level < max_level:
            level += 1

            # Get the current node (the node in open_list with the lowest cost)
            current_node = open_list[0]
            current_index = 0
            for index, item in enumerate(open_list):
                if item.f < current_node.f:
                    current_node = item
                    current_index = index

            # Pop current off open list, add to closed list
            open_list.pop(current_index)
            closed_list.append(current_node)

            # Found the goal
            if current_node == end_node:
                path = []
                distance = current_node.g
                current = current_node
                while current is not None:
                    path.append(current.number)
                    current = current.parent

                return path[::-1], distance # Return reversed path

            # Generate children
            children = []
            for new_number in self.road_tree[current_node.number]: # Adjacent nodes
                new_node = Node(current_node, new_number, self.node_dict[new_number])
                children.append(new_node)

            # Loop through children
            for child in children:
                append_to_open_list = False

                # Create the f, g, and h values
                child.g = current_node.g + self.road_dict[(current_node.number, child.number)]
                child.h = sqrt((child.x - end_node.x) ** 2 + (child.y - end_node.y) ** 2) / 200
                child.f = child.g + child.h

                # Child is already in the closed list
                closed_list, append_to_open_list = self.check_in_list(child, closed_list, append_to_open_list)

                # Child is already in the open list
                open_list, append_to_open_list = self.check_in_list(child, open_list, append_to_open_list)

                # Add the child to the open list
                if append_to_open_list:
                    open_list.append(child)

        return [], 1e10

    @staticmethod
    def check_in_list(child, check_list, append_to_open_list):
        '''check if the child is in open or closed list'''
        child_in_check_list = [index for index, check_node in enumerate(check_list) if check_node == child]
        if len(child_in_check_list) > 0:
            for index in child_in_check_list:
                if child.g < check_list[index].g:
                    check_list.pop(index)
                    append_to_open_list = True
                    break
        else:
            append_to_open_list = True
        
        return check_list, append_to_open_list

class Node():
    """A node class for A* Pathfinding"""

    def __init__(self, parent=None, number=None, coord=None):
        self.parent = parent
        self.number = number
        self.x, self.y = coord[0], coord[1]
        self.g = 0
        self.h = 0
        self.f = 0

    def __eq__(self, other):
        return self.number == other.number

class LatLonToTWD97(object):
    """This object provide method for converting lat/lon coordinate to TWD97
    coordinate

    the formula reference to
    http://www.uwgb.edu/dutchs/UsefulData/UTMFormulas.htm (there is lots of typo)
    http://www.offshorediver.com/software/utm/Converting UTM to Latitude and Longitude.doc

    Parameters reference to
    http://rskl.geog.ntu.edu.tw/team/gis/doc/ArcGIS/WGS84%20and%20TM2.htm
    http://blog.minstrel.idv.tw/2004/06/taiwan-datum-parameter.html
    """

    def __init__(self, a = 6378137.0, b = 6356752.314245, long0 = radians(121), k0 = 0.9999, dx = 250000,):
        self.a = a # Equatorial radius
        self.b = b # Polar radius
        self.long0 = long0 # central meridian of zone
        self.k0 = k0 # scale along long0
        self.dx = dx # delta x in meter

    def convert(self, lat, lon):
        """Convert lat lon to twd97"""
        a = self.a
        b = self.b
        long0 = self.long0
        k0 = self.k0
        dx = self.dx

        e = (1 - b ** 2 / a ** 2) ** 0.5
        e2 = e ** 2 / (1 - e ** 2)
        n = (a - b) / (a + b)
        nu = a / (1 - (e ** 2) * (sin(lat) ** 2)) ** 0.5
        p = lon - long0

        A = a * (1 - n + (5 / 4.0) * (n ** 2 - n ** 3) + (81 / 64.0)*(n ** 4  - n ** 5))
        B = (3 * a * n / 2.0) * (1 - n + (7 / 8.0) * (n ** 2 - n ** 3) + (55 / 64.0) * (n ** 4 - n ** 5))
        C = (15 * a * (n ** 2) / 16.0) * (1 - n + (3 / 4.0) * (n ** 2 - n ** 3))
        D = (35 * a * (n ** 3) / 48.0) * (1 - n + (11 / 16.0) * (n ** 2 - n ** 3))
        E = (315 * a * (n ** 4) / 51.0) * (1 - n)

        S = A * lat - B * sin(2 * lat) + C * sin(4 * lat) - D * sin(6 * lat) + E * sin(8 * lat)

        K1 = S * k0
        K2 = k0 * nu * sin(2 * lat)/4.0
        K3 = (k0 * nu * sin(lat) * (cos(lat) ** 3) / 24.0) * \
            (5 - tan(lat) ** 2 + 9 * e2 * (cos(lat) ** 2) + 4 * (e2 ** 2) * (cos(lat) ** 4))

        y = K1 + K2 * (p ** 2) + K3 * (p ** 4)

        K4 = k0 * nu * cos(lat)
        K5 = (k0 * nu * (cos(lat) ** 3) / 6.0) * (1 - tan(lat) ** 2 + e2 * (cos(lat) ** 2))

        x = K4 * p + K5 * (p ** 3) + dx
        return x, y

def get_file_name():
    file_names = {}
    folder_option = ''
    while folder_option != '1' and folder_option != '2':
        folder_option = input(
            '請問要檢查單一檔案還是資料夾內的全部檔案呢？\n'
            '1 = 單一檔案\n'
            '2 = 資料夾內的全部檔案\n'
            '請輸入1或2：')

    if folder_option == '1':
        file_name = None
        while file_name is None or (
            not os.path.isfile(file_name) and 
            not (file_name.endswith(".lin") or file_name.endswith(".txt"))
        ):
            file_name = input('請輸入公車路線資料檔名(包含副檔名: *.lin 或 *.txt)：')
        file_names[file_name] = file_name
    
    else:
        folder_name = None
        while folder_name is None or not os.path.isdir(folder_name):
            folder_name = input('請輸入資料夾路徑：')

        for f in os.listdir(folder_name):
            if f.endswith(".lin") or f.endswith(".txt"):
                file_names[f] = os.path.join(folder_name, f)

    return file_names

def progress_bar(bar_name: str, current_num: int, total_num: int, output_option: int = 2):
    """ Display the progress bar if the result is printed to the text file. """
    if output_option == 2:
        print(
            '\r[{:<50}] {}: {}/{}'.format(
                '=' * int(current_num / (2 * total_num) * 100), 
                bar_name, current_num, total_num
            ), 
                end=''
        )
        if current_num == total_num:
            print()

class CheckError(object):
    """檢查錯誤都會用到的東西"""

    def __init__(self, check_type: str):
        self.check_type = check_type
        self.get_debug_option()
        self.get_output_option()
        self.get_remove_option()

    def get_debug_option(self):
        debug_str = ''
        while debug_str.upper() != 'Y' and debug_str.upper() != 'N':
            debug_str = input('\n發現{}時，要提示錯誤型態或可能解法嗎？[Y/N]: '.format(self.check_type))
        
        if debug_str.upper() == 'Y':
            debug_option = True
        else:
            debug_option = False

        self.debug_option = debug_option

    def get_output_option(self):
        output_option = ''
        while output_option != '1' and output_option != '2':
            output_option = input(
                '\n要如何顯示檢查{}的結果呢？\n'
                '1 = 直接顯示在這邊\n'
                '2 = 輸出到一個文字檔\n'
                '請輸入1或2：'.format(self.check_type))

        if output_option == '2':
            result_filename = ''
            while not result_filename.endswith('.txt'):
                result_filename = input(
                    '請輸入{}結果輸出檔名(要包含.txt)：'.format(self.check_type)
                )
        else:
            result_filename = None

        self.output_option = int(output_option)
        self.result_filename = result_filename

    def get_remove_option(self):
        remove_option = ''
        while remove_option != '1' and remove_option != '2' and remove_option != '3':
            remove_option = input(
                '\n要如何處理有{}的檔案呢？\n'
                '1 = 不處理\n'
                '2 = 刪除\n'
                '3 = 移動到其他地方\n'
                '請輸入1、2或3：'.format(self.check_type)
            )
        remove_option = int(remove_option)
        
        trashcan_dir = None
        if remove_option == 3:
            while trashcan_dir is None or os.path.isdir(trashcan_dir):
                trashcan_dir = input('請輸入{}檔案移動的目標路徑：'.format(self.check_type))
        
        self.remove_option = remove_option
        self.trashcan_dir = trashcan_dir

    def remove_failed_path(self, file_name: str):
        if self.remove_option == 2:
            os.remove(file_name)
            print('\n已刪除 {}\n'.format(file_name.replace('\\', '/')))
        elif self.remove_option == 3:
            target_filename = os.path.join(self.trashcan_dir, os.path.split(file_name)[-1])
            if os.path.isfile(target_filename):
                os.remove(target_filename)
            Path(file_name).rename(target_filename)
            print('\n已移動檔案\n舊路徑: {}\n新路徑: {}\n'.format(
                    file_name.replace('\\', '/'), target_filename.replace('\\', '/')
                )
            )

    def open_logfile(self):
        """ Open the text file for printing result if necessary."""
        if self.output_option == 2:
            self.ER_file = open(self.result_filename, 'w')

    def close_logfile(self):
        if self.output_option == 2:
            self.ER_file.close()

    def print_failed_info(self, file_name, num_checked_line, total_line, line_name, failed_caption):
        if line_name != 'current_line':
            line_name_text = '\n({}/{}) LINE NAME=\"{}\"'.format(
                num_checked_line, total_line, line_name
            )
        else:
            line_name_text = ''
        
        if len(failed_caption) > 0:
            failed_info = '下列區間不在路網內：\n{}'.format('\n'.join(failed_caption))
        else:
            failed_info = '本路線有{}'.format(self.check_type)
        
        self.print_result('{}{}\n{}\n'.format(file_name, line_name_text, failed_info))

    def print_result(self, result_line: str):
        """ Print the result based on the output option previously input."""
        if self.output_option == 1:
            print(result_line)
        else:
            self.ER_file.write('{}\n'.format(result_line))

class CheckSyntaxError(CheckError):
    """格式錯誤的相關東西"""

    def __init__(self, error_type: dict):
        print('\n首先檢查點號序之中的格式錯誤，像是多打逗點、打錯逗點之類的...')
        super().__init__('格式錯誤')
        self.error_type = error_type

    def go_over_files(self, files_data: dict, file_paths: dict):
        files_dict = {}
        total_error = True
        self.open_logfile()
        for f in files_data:
            route_dict, no_syntax_error = self.check_syntax(f, files_data[f])
            files_dict[f] = route_dict
            total_error = total_error and no_syntax_error
            if not no_syntax_error:
                self.remove_failed_path(file_paths[f])
        self.close_logfile()

        print('格式檢查完畢')

        return files_dict, total_error

    def check_syntax(self, file_name: str, route_data: str):
        route_dict = self.process_route(route_data)
        no_syntax_error = True
        route_num = 0
        total_route = len(route_dict.keys())
        for line_name in route_dict:
            route_num += 1
            node_seq = route_dict[line_name]
            failed_caption = []

            if node_seq != '':
                route_dict[line_name] = node_seq
                syntax_error_info, new_no_syntax_error = self.check_node_seq(node_seq)
                
                if len(syntax_error_info) > 0:
                    failed_caption.append('{}'.format('\n'.join(syntax_error_info)))
                
                try:
                    passed_node_list = list(map(int, node_seq.split(',')))
                except:
                    new_no_syntax_error = False
                    failed_caption.append('  可能有其他不明錯誤')

                if not new_no_syntax_error:
                    self.print_failed_info(
                        file_name, route_num, total_route, line_name, failed_caption
                    )
                
                no_syntax_error = no_syntax_error and new_no_syntax_error

            progress_bar(file_name, route_num, total_route, self.output_option)

        return route_dict, no_syntax_error
    
    def process_route(self, route_data: str):
        """ process route_data based on file_option """
        route_dict = {}

        route_data = re.sub(r';+[^;]+;+\n', '', route_data)
        route_data = route_data.replace('\n', '')
        if 'LINE NAME' in route_data:
            route_data = route_data.split('LINE NAME=\"')
            route_data = [rd for rd in route_data if len(rd) > 0 if 'N=' in rd]
            for rd in route_data:
                line_name = rd[:rd.index('\"')]
                node_seq = rd[rd.index('N='):] # start from the first N
                node_seq = node_seq.replace('N=', '')
                node_seq = re.sub(r'TIME\s*=\s*[0-9\.]+\s*,', '', node_seq)
                if len(node_seq) > 0:
                    route_dict[line_name] = node_seq
        else:
            route_dict['current_line'] = route_data

        return route_dict

    def check_node_seq(self, node_seq: str):
        """ Check the syntax error of the node sequence. """
        syntax_error_info = []
        no_syntax_error = True
        # syntax error
        for tp in self.error_type:
            result = self.error_type[tp].findall(node_seq)
            if len(result) > 0:
                no_syntax_error = False
                for r in result:
                    syntax_error_info.append('  {}: {}'.format(tp, r))
        return syntax_error_info, no_syntax_error

class CheckNodeError(CheckError):
    """點號錯誤的相關東西"""

    def __init__(self, path_finder: ShortestPath):
        print('\n再來檢查點號序之中的點號錯誤，像是重覆點號、點號錯誤之類的...')
        super().__init__('點號錯誤')
        self.path_finder = path_finder
        self.checked_result = {}

    def go_over_files(self, files_dict: dict, file_paths: dict):
        self.open_logfile()
        count = 0
        for f in files_dict:
            count += 1
            no_node_error = self.line_sanity_check(f, files_dict[f])
            if not no_node_error:
                self.remove_failed_path(file_paths[f])
        self.close_logfile()
        print('點號檢查完畢')

    def line_sanity_check(self, file_name: str, route_dict: dict):
        """檢查是不是有非區域內道路混進來了"""
        num_checked_line = 0
        total_line = len(route_dict.keys())
        progress_bar(file_name, num_checked_line, total_line, self.output_option)
        no_node_error = True
        for line_name in route_dict:
            num_checked_line += 1
            passed_node_str = route_dict[line_name]
            failed_caption = []
            
            passed_node_list = list(map(int, passed_node_str.split(',')))
            passed_node_list = list(map(abs, passed_node_list))
            stop_pair = list(zip(passed_node_list, passed_node_list[1:]))
            
            if_fail = False
            failed_pair = []
            for (p1, p2) in stop_pair:
                if (p1, p2) not in self.path_finder.road_dict:
                    if_fail = True
                    failed_pair.append((p1, p2))
            
            no_node_error = no_node_error and (not if_fail)
            if if_fail:
                if self.debug_option:
                    #處理頭尾同點
                    FP_no_same_pt = []
                    for (p1, p2) in failed_pair:
                        if p1 == p2:
                            failed_caption.append(' {}, {}  (首尾同點)'.format(p1, p2))
                        else:
                            FP_no_same_pt.append((p1, p2))

                    #將連續錯誤編入同一個list
                    FP_group = []
                    temp_group = []
                    temp_end = 0
                    for (p1, p2) in FP_no_same_pt:
                        if p1 != temp_end and temp_group != []:
                            FP_group.append(temp_group)
                            temp_group = []
                        temp_group.append((p1, p2))
                        temp_end = p2
                    if temp_group != []:
                        FP_group.append(temp_group)

                    for group in FP_group:
                        failed_path = [group[0][0]]
                        for p in group:
                            failed_path.append(p[1])
                        
                        p1 = failed_path[0]
                        p2 = failed_path[-1]

                        head_index = stop_pair.index(group[0])
                        if head_index == 0:
                            p0 = p1
                        else:
                            p0 = stop_pair[head_index-1][0]
                        
                        tail_index = stop_pair.index(group[-1])
                        if tail_index == len(stop_pair) - 1:
                            p3 = p2
                        else:
                            p3 = stop_pair[tail_index+1][1]
                        
                        found = False
                        # p1 -> p2
                        if not found:
                            section_type = '中間有誤'
                            failed_caption, found = self.check_section(p1, p2, failed_path, section_type, failed_caption)
                        # p0 -> p2
                        if not found and p0 != p1:
                            section_type = '中間有誤、第一點({})可能有誤'.format(p1)
                            failed_caption, found = self.check_section(p0, p2, failed_path, section_type, failed_caption)
                        # p1 -> p3
                        if not found and p3 != p2:
                            section_type = '中間有誤、最後點({})可能有誤'.format(p2)
                            failed_caption, found = self.check_section(p1, p3, failed_path, section_type, failed_caption)
                        # p0 -> p3
                        if not found and p0 != p1 and p3 != p2:
                            section_type = '中間有誤、頭尾點({} & {})可能有誤'.format(p1, p2)
                            failed_caption, found = self.check_section(p0, p3, failed_path, section_type, failed_caption)
                        if not found:
                            failed_caption.append(' {}  (其他錯誤)'.format(', '.join(map(str, failed_path))))

                self.print_failed_info(file_name, num_checked_line, total_line, line_name, failed_caption)

            # progress bar
            progress_bar(file_name, num_checked_line, total_line, self.output_option)
            
        return no_node_error
    
    def check_section(self, st: int, ed: int, failed_path: list, section_type: str, failed_caption: list):
        found = False
        if (st, ed) in self.checked_result:
            path = self.checked_result[(st, ed)]
        else:
            path, _ = self.path_finder.find_shortest_path([st, ed], 10000)

        if len(path) > 0:
            found = True
            failed_caption.append(' {}  ({}，可行解：{})'.format(', '.join(map(str, failed_path)), section_type, ', '.join(map(str, path))))
            self.checked_result[(st, ed)] = path
        
        return failed_caption, found

def main():

    error_type = {
        '以逗點結尾': re.compile(r'-*\d+,+\s*$'),
        '連續逗點': re.compile(r'-*\d+,\s*,\s*-*\d+'),
        '點號數字過多': re.compile(r'-*\d{6,}'),
        '把逗點打成句點': re.compile(r'-*\d+\.\s*-*\d+'),
        '兩點號間有空格無逗號': re.compile(r'-*\d+\s+-*\d+'),
        '兩負點號間無空格無逗號': re.compile(r'-*\d+-+\d+'),
        '連續負號': re.compile(r'\s*-\s*-\s*\d+'),
        '負號跟數字之間有空格': re.compile(r'-\s+\d+'),
        '負號不是連接數字': re.compile(r'-\D+'),
        '第一點為負點號': re.compile(r'^-\d+'),
        '最後一點為負點號': re.compile(r'-\d+,*\s*$'),
    }

    node_csv_path = 'P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_NET_node.csv'
    road_csv_path = 'P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_NET_link.csv'
    pass_all = False

    # check node file
    node_csv_path, pass_all = check_csv_file(node_csv_path, '路口節點資料檔', pass_all)

    # check road file
    road_csv_path, pass_all = check_csv_file(road_csv_path, '公路節線資料檔', pass_all)

    if not pass_all:
        excluded_roadtype = ['RR', 'ZL', 'WL', 'TL']
        node_dict = ImportNetwork.get_node_list(node_csv_path, min_N=5001, max_N=150000)
        road_dict = ImportNetwork.get_road_list(road_csv_path, excluded_roadtype=excluded_roadtype)
        road_tree = ImportNetwork.generate_tree(node_dict, road_dict)
        path_finder = ShortestPath(node_dict, road_dict, road_tree)

        file_paths = get_file_name()
        files_data = {}
        files_read = 0
        total_files = len(file_paths.keys())
        progress_bar('已讀取檔案數', files_read, total_files)
        for file_name in file_paths:
            try:
                with open(file_paths[file_name], 'r', encoding = "Big5") as routes:
                    files_data[file_name] = routes.read()
            except:
                with open(file_paths[file_name], 'r', encoding = "UTF-8") as routes:
                    files_data[file_name] = routes.read()
            files_read += 1
            progress_bar('已讀取檔案數', files_read, total_files)
            
        SyntaxCheck = CheckSyntaxError(error_type)
        files_dict, no_syntax_error = SyntaxCheck.go_over_files(files_data, file_paths)

        if no_syntax_error:
            NodeCheck = CheckNodeError(path_finder)
            NodeCheck.go_over_files(files_dict, file_paths)
            input('檢查完畢')
        else:
            input('公車路線資料有格式錯誤，結束程式')

if __name__ == '__main__':
    main()
