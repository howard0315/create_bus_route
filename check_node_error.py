# -*- coding: utf-8 -*-

from csv import reader as csv_reader
from math import cos, radians, sin, sqrt, tan
from os.path import isfile
from re import compile as re_compile
from re import match as re_match
from re import sub as re_sub

def check_csv_file(file_name: str, file_type: str, pass_all: bool):
    while not isfile(file_name) and not pass_all:
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

def get_road_list(road_csv_path: str):
    road_list = {}
    with open(road_csv_path, newline='') as road_csv:
        road_row = csv_reader(road_csv)
        for r in road_row:
            if r[0] == 'ID':
                continue
            else:
                if int(r[4]) == 0:
                    road_list[(int(r[2]), int(r[3]))] = float(r[1])
                    road_list[(int(r[3]), int(r[2]))] = float(r[1])
                elif int(r[4]) == 1:
                    road_list[(int(r[2]), int(r[3]))] = float(r[1])
                else:
                    road_list[(int(r[3]), int(r[2]))] = float(r[1])
    print('完成道路讀取...')
    return road_list

def get_node_list(node_csv_path: str):
    node_list = {}
    with open(node_csv_path, newline='') as node_csv:
        road_row = csv_reader(node_csv)
        for r in road_row:
            if r[0] == 'N':
                continue
            else:
                node_list[int(r[0])] = (float(r[1]), float(r[2]))
    print('完成節點讀取...')
    return node_list

def get_file_name():
    file_name = input('請輸入公車路線資料檔名(包含副檔名, *.lin, *.txt, ...)：')
    while not isfile(file_name):
        file_name = input('無此檔案，請重新輸入：')
    
    file_option = input(
        '這個要檢查的檔案長得如何呢？\n'
        '1 = 內容像是要匯入cube的樣子 (eg. 有LINE NAME=之類的)\n'
        '2 = 這個檔案裡面只有點號順序 (eg. 只有123,-456,...之類的)\n'
        '請輸入1或2：')
    while file_option != '1' and file_option != '2':
        file_option = input(
            '亂填!!!，重來\n'
            '1 = 裡面像是要匯入cube的樣子 (eg. 有LINE NAME=之類的)\n'
            '2 = 那個檔案裡面只有點號順序 (eg. 只有123,-456,...之類的)\n'
            '這個要檢查的檔案長得如何呢？')
    file_option = int(file_option)

    return file_name, file_option

class CheckError(object):
    """檢查錯誤都會用到的東西"""

    def __init__(self, check_type: str):
        self.get_option(check_type)

    def get_option(self, check_type: str):
        output_option = input(
            '要如何顯示{}的結果呢？\n'
            '1 = 直接顯示在這邊\n'
            '2 = 輸出到一個文字檔\n'
            '請輸入1或2：'.format(check_type))
        while output_option != '1' and output_option != '2':
            output_option = input(
                '亂填!!!，重來\n'
                '1 = 直接顯示在這邊\n'
                '2 = 輸出到一個文字檔\n'
                '要如何顯示結果呢？')
        output_option = int(output_option)

        if output_option == 2:
            result_filename = input('請輸入{}結果輸出檔名(要包含.txt)：'.format(check_type))
            while re_match(r'.*\.txt', result_filename) is None:
                result_filename = input('格式不符，請重新輸入{}結果輸出檔名(要包含.txt)：'.format(check_type))
        else:
            result_filename = ''
        
        self.output_option = output_option
        self.result_filename = result_filename

    def open_file(self):
        """ Open the text file for printing result if necessary."""
        if self.output_option == 2:
            self.ER_file = open(self.result_filename, 'w')

    def close_file(self):
        if self.output_option == 2:
            self.ER_file.close()

    def print_result(self, result_line: str):
        """ Print the result based on the output option previously input."""
        if self.output_option == 1:
            print(result_line)
        else:
            self.ER_file.write('{}\n'.format(result_line))

    def progress_bar(self, current_num: int, total_num: int):
        """ Display the progress bar if the result is printed to the text file. """
        if self.output_option == 2:
            print(
                '\r[{:<50}] checked routes: {}/{}'.format(
                '=' * int(current_num / (2 * total_num) * 100), current_num, total_num), 
                end='')
    
    def clean_up_progress_bar(self):
        """ If the progress bar is displayed, print an empty line when the progress reaches 100%. """
        if self.output_option == 2:
            print()

class CheckSyntaxError(CheckError):
    """語法錯誤的相關東西"""

    def __init__(self, error_type: dict):
        print('\n首先檢查點號序之中的語法錯誤，像是多打逗點、打錯逗點之類的...')
        super().__init__('檢查語法錯誤')
        self.error_type = error_type

    def check_syntax(self, route_data: str, file_option: int):
        route_dict = self.process_route(route_data, file_option)
        
        self.open_file()
        no_syntax_error = True

        route_num = 0
        total_route = len(route_dict.keys())
        for LINE_NAME in route_dict:
            route_num += 1
            node_seq = route_dict[LINE_NAME]
            failed_caption = []

            if node_seq != '':
                route_dict[LINE_NAME] = node_seq
                syntax_error_info, new_no_syntax_error = self.check_node_seq(node_seq)
                
                if len(syntax_error_info) > 0:
                    failed_caption.append('{}'.format('\n'.join(syntax_error_info)))
                
                try:
                    passed_node_list = list(map(int, node_seq.split(',')))
                except:
                    new_no_syntax_error = False
                    failed_caption.append('  可能有其他不明錯誤')

                if not new_no_syntax_error:
                    self.print_result(
                        '({}/{}) LINE NAME=\"{}\"，有以下語法錯誤：\n'
                        '{}'.format(route_num, total_route, LINE_NAME, '\n'.join(failed_caption))
                    )
                    self.print_result('')
                
                no_syntax_error = no_syntax_error and new_no_syntax_error

            self.progress_bar(route_num, total_route)
    
        self.clean_up_progress_bar()
        self.close_file()
        
        print('語法檢查完畢')

        return route_dict, no_syntax_error
    
    def process_route(self, route_data: str, file_option: int):
        """ process route_data based on file_option"""
        route_dict = {}

        route_data = route_data.replace('\n', '')
        if file_option == 1:
            route_data = route_data.replace(';;<<PT>><<LINE>>;;', '')
            route_data = re_sub(r';+臺中公車;+', '', route_data)
            route_data = re_sub(r';+台中公車;+', '', route_data)
            route_data = route_data.split('LINE NAME=\"')
            route_data = [rd for rd in route_data if len(rd) > 0]
            for rd in route_data:
                LINE_NAME = rd[:rd.index('\"')]
                node_seq = rd[rd.index('N=')+2:]
                if len(node_seq) > 0:
                    route_dict[LINE_NAME] = node_seq
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

    def __init__(self, road_list: dict, node_list: dict):
        print('\n再來檢查點號序之中的點號錯誤，像是重覆點號、點號錯誤之類的...')
        super().__init__('檢查點號錯誤')
        self.road_list = road_list
        self.node_list = node_list
        self.checked_result = {}

    def line_sanity_check(self, route_dict: dict):
        """檢查是不是有非區域內道路混進來了"""
        self.open_file()

        num_checked_line = 0
        total_line = len(route_dict.keys())
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
                if (p1, p2) not in self.road_list:
                    if_fail = True
                    failed_pair.append((p1, p2))
                    
            if if_fail:
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
                        failed_caption, found = self.check_section(
                            p1, p2, failed_path, section_type, failed_caption)

                    # p0 -> p2
                    if not found and p0 != p1:
                        section_type = '中間有誤、第一點({})可能有誤'.format(p1)
                        failed_caption, found = self.check_section(
                            p0, p2, failed_path, section_type, failed_caption)

                    # p1 -> p3
                    if not found and p3 != p2:
                        section_type = '中間有誤、最後點({})可能有誤'.format(p2)
                        failed_caption, found = self.check_section(
                            p1, p3, failed_path, section_type, failed_caption)

                    # p0 -> p3
                    if not found and p0 != p1 and p3 != p2:
                        section_type = '中間有誤、頭尾點({} & {})可能有誤'.format(p1, p2)
                        failed_caption, found = self.check_section(
                            p0, p3, failed_path, section_type, failed_caption)
                    
                    if not found:
                        failed_caption.append(' {}  (其他錯誤)'.format(', '.join(map(str, failed_path))))

                self.print_result(
                    '({}/{}) LINE NAME=\"{}\"，下列區間不在路網內：\n' 
                    '{}\n\n'.format(num_checked_line, total_line, line_name, '\n'.join(failed_caption))
                )

            # progress bar
            self.progress_bar(num_checked_line, total_line)

        self.clean_up_progress_bar()
        self.close_file()

        print('點號檢查完畢')
    
    def check_section(self, st: int, ed: int, failed_path: list, section_type: str, failed_caption: list):
        found = False
        if (st, ed) in self.checked_result:
            path = self.checked_result[(st, ed)]
        else:
            path, _ = self.check_feasible_path(st, ed)

        if len(path) > 0:
            found = True
            failed_caption.append(' {}  ({}，可行解：{})'.format(
                ', '.join(map(str, failed_path)), section_type, ', '.join(map(str, path))))
            self.checked_result[(st, ed)] = path
        
        return failed_caption, found

    def check_feasible_path(self, p1: int, p2: int, max_level: int = 500):
        # 兩點相鄰
        if (p1, p2) in self.road_list:
            return [p1, p2], self.road_list[(p1, p2)]

        # 中間隔一點
        midpoint_list = [line[1] for line in self.road_list if p1 == line[0]]
        min_dist = 1e10
        midpoint = 0
        for m in midpoint_list:
            if (m, p2) in self.road_list:
                if self.road_list[(p1, m)] + self.road_list[(m, p2)] < min_dist:
                    min_dist = self.road_list[(p1, m)] + self.road_list[(m, p2)]
                    midpoint = m
        if midpoint != 0:
            return [p1, midpoint, p2], min_dist

        # 中間隔超過一點
        if p1 in self.node_list and p2 in self.node_list:
            path, distance = a_star_alg(p1, p2, self.road_list, self.node_list, max_level)
            return path, distance

class Node():
    """A node class for A* Pathfinding"""

    def __init__(self, parent=None, number=None, lonlat=None):
        self.parent = parent
        self.number = number
        self.x, self.y = LatLonToTWD97().convert(lonlat[1], lonlat[0])
        self.g = 0
        self.h = 0
        self.f = 0

    def __eq__(self, other):
        return self.number == other.number

def a_star_alg(p1: int, p2: int, road_list: dict, node_list: dict, max_level: int = 500):
    """Returns a list of nodes as a path from the given start to the given end in the given road network"""
    
    # Create start and end node
    start_node = Node(None, p1, node_list[p1])
    start_node.g = start_node.h = start_node.f = 0
    end_node = Node(None, p2, node_list[p2])
    end_node.g = end_node.h = end_node.f = 0

    # Initialize both open and closed list
    open_list = []
    closed_list = []

    # Add the start node
    open_list.append(start_node)

    level = 0

    # Loop until you find the end
    while len(open_list) > 0 and level < max_level:
        level += 1

        # Get the current node
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
        for new_number in [line[1] for line in road_list if current_node.number == line[0]]: # Adjacent nodes
            new_node = Node(current_node, new_number, node_list[new_number]) # Create new node
            children.append(new_node) # Append

        # Loop through children
        for child in children:

            # Child is on the closed list
            for closed_child in closed_list:
                if child == closed_child:
                    continue

            # Create the f, g, and h values
            child.g = current_node.g + road_list[(current_node.number, child.number)]
            # child.h = sqrt(((child.x - end_node.x) ** 2) + ((child.y - end_node.y) ** 2))
            child.h = 0.5 * (abs(child.x - end_node.x) + abs(child.y - end_node.y))
            child.f = child.g + child.h

            # Child is already in the open list
            for open_node in open_list:
                if child == open_node and child.g > open_node.g:
                    continue

            # Add the child to the open list
            open_list.append(child)

    return [], 1e10

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

    def __init__(self, a = 6378137.0, b = 6356752.314245,
        long0 = radians(121), k0 = 0.9999, dx = 250000,):
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

        x = K4 * p + K5 * (p ** 3) + self.dx
        return x, y

def main():

    error_type = {
        '以逗點結尾': re_compile(r'-*\d+,+\s*$'),
        '連續逗點': re_compile(r'-*\d+,\s*,\s*-*\d+'),
        '點號數字過多': re_compile(r'-*\d{6,}'),
        '把逗點打成句點': re_compile(r'-*\d+\.\s*-*\d+'),
        '兩點號間有空格無逗號': re_compile(r'-*\d+\s+-*\d+'),
        '兩負點號間無空格無逗號': re_compile(r'-*\d+-+\d+'),
        '連續負號': re_compile(r'\s*-\s*-\s*\d+'),
        '負號跟數字之間有空格': re_compile(r'-\s+\d+'),
        '負號不是連接數字': re_compile(r'-\D+'),
        '第一點為負點號': re_compile(r'^-\d+'),
        '最後一點為負點號': re_compile(r'-\d+,*\s*$'),
    }

    node_csv_path = 'C_TWN_ROAD_picked_node.csv'
    road_csv_path = 'C_TWN_ROAD_picked.csv'
    pass_all = False

    # check node file
    node_csv_path, pass_all = check_csv_file(node_csv_path, '路口節點資料檔', pass_all)

    # check road file
    road_csv_path, pass_all = check_csv_file(road_csv_path, '公路節線資料檔', pass_all)

    if not pass_all:
        node_list = get_node_list(node_csv_path)
        road_list = get_road_list(road_csv_path)

        file_name, file_option = get_file_name()
        with open(file_name, 'r', encoding = "Big5") as routes:
            route_data = routes.read()

        SyntaxCheck = CheckSyntaxError(error_type)
        route_dict, no_syntax_eror = SyntaxCheck.check_syntax(route_data, file_option)

        if no_syntax_eror:
            NodeCheck = CheckNodeError(road_list, node_list)
            NodeCheck.line_sanity_check(route_dict)
            input('檢查完畢')
        else:
            input('公車路線資料檔內有語法錯誤，結束程式')

if __name__ == '__main__':
    main()