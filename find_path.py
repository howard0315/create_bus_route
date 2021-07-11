# -*- coding: utf-8 -*-

import csv
import os
import urllib.parse
from math import cos, radians, sin, sqrt, tan
from shutil import copy2
from typing import List

import pandas as pd
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QInputDialog, QMessageBox, QFileDialog
from qgis.analysis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.utils import *


class GetFile():
    @staticmethod
    def get_dir(dir_description: str, ):
        while True:
            result_dir = QFileDialog.getExistingDirectory(None, dir_description, )
            if os.path.isdir(result_dir):
                return result_dir

    @staticmethod
    def get_file():
        pass

class ImportNetwork():
    @staticmethod
    def get_road_list(road_csv_path: str, excluded_roadtype: List[str]):
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

    def find_shortest_path(self, OD_node: List[int], max_level: int = 1000):
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

class ProcessPath():
    """處理站間路徑相關"""
    
    @staticmethod
    def save(path_list: List[int], save_dir: str, path_filename: str):
        """把站牌間路徑儲存成文字檔"""
        path_str = ','.join(map(str, path_list))
        path_path = os.path.join(save_dir, '{}.txt'.format(path_filename)) #路徑的路徑
        path_file = open(path_path, 'w')
        path_file.write(path_str)
        path_file.close()

    @staticmethod
    def load(OD_node: List[int], load_dir: str, path_filename: str):
        """讀取已經儲存的站牌間路徑"""
        path_path = os.path.join(load_dir, '{}.txt'.format(path_filename))
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

    @staticmethod
    def move(ori_node: int, des_node: int, ori_dir: str, des_dir: str):
        sucess = False
        ori_file = os.path.join(ori_dir, '{}_{}.txt'.format(ori_node, des_node))
        if os.path.isfile(ori_file):
            copy2(ori_file, des_dir)
            sucess = True
        return sucess

    @staticmethod
    def get_file_list(folder):
        """return a list of the filename in the folder"""
        result = []
        if os.path.isdir(folder):
            result = os.listdir(folder)
        return result

class SearchGeometry(object):
    """尋找各種位置資訊"""

    def __init__(self, layer_dict: dict):
        self.vlayer = layer_dict
    
    def distance(self, node_pair: list = None, point_pair: list = None):
        """算兩點之間的距離"""
        if node_pair is not None:
            point_pair = self.get_point('node', 'N', node_pair)

        distance = 1e10
        if point_pair is not None and (point_pair[0] != [] and point_pair[1] != []):
            if point_pair[0].x() < 1000:
                x0, y0 = LatLonToTWD97().convert(radians(point_pair[0].y()), radians(point_pair[0].x()))
                x1, y1 = LatLonToTWD97().convert(radians(point_pair[1].y()), radians(point_pair[1].x()))
            else:
                x0 = point_pair[0].x()
                y0 = point_pair[0].y()
                x1 = point_pair[1].x()
                y1 = point_pair[1].y()
            distance = sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        return distance
    
    def get_point(self, layer_name: str, attribute_name: str, value_list: list):
        """取得特定屬性的幾何資訊"""
        feature_list = [[] for _ in value_list]
        if layer_name in self.vlayer:
            for i, feature in enumerate(value_list):
                self.vlayer[layer_name].removeSelection()
                self.vlayer[layer_name].selectByExpression('\"{}\" = {}'.format(attribute_name, feature))
                #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
                #get the geometry of the feature
                selected_point = self.vlayer[layer_name].selectedFeatures()
                if len(selected_point) > 0:
                    feature_list[i] = QgsGeometry.asPoint(selected_point[0].geometry())
        return feature_list

    def is_in_zone(self, layer_name: str, attribute_name: str, value_list: list):
        """確認點號存在且不是0，有一個錯就是全錯，拿不到分數啦"""
        in_layer = True
        point_list = self.get_point(layer_name, attribute_name, value_list)
        for p in point_list:
            in_layer = p != [] and in_layer
        return in_layer

    def display_points(self, nodes_list=None, points_list=None, color: str = 'cyan'):
        """把最短路徑通過的節點選取出來\n
        https://gis.stackexchange.com/questions/86812/how-to-draw-polygons-from-the-python-console
        """
        # create a memory layer with two points
        nodes_layer = QgsVectorLayer('Point', 'path', "memory")
        if nodes_list is not None:
            points_list = self.get_point('node', 'N', nodes_list)
        
        if points_list is not None:
            pr = nodes_layer.dataProvider()
            for point in points_list:
                pt = QgsFeature()
                pt.setGeometry(QgsGeometry.fromPointXY(point))
                pr.addFeatures([pt])
                nodes_layer.updateExtents()
            nodes_layer.updateExtents() # update extent of the layer

            nodes_layer.renderer().symbol().setColor(QColor(color))
            # add the layer to the canvas
            QgsProject.instance().addMapLayers([nodes_layer])

            #zoom to frame
            extent = nodes_layer.extent()
            iface.mapCanvas().setExtent(extent)

            #zoom out a little bit
            iface.mapCanvas().setWheelFactor(1.5)
            iface.mapCanvas().zoomOut()

        return nodes_layer

class PrepareRoute():
    """匯入公車路線相關"""

    @staticmethod
    def choose_route(data_dir, zone2dir):
        """選擇路線"""
        while True:
            routeUID, OK = QInputDialog().getText(None, '輸入UID', '請輸入路線UID ＞ω＜:')

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
                    route_spec = {
                        'routeUID': routeUID, 'SubRouteName': SubRouteName, 'direction': direction,
                        'route_dir': route_dir, 'route_name': '{}_{}_{}'.format(routeUID, SubRouteName, direction)
                    }
                    break
            else:
                route_spec = {
                    'routeUID': None, 'SubRouteName': None, 'direction': None, 
                    'route_dir': None, 'route_name': None
                }
                break

        return route_spec, OK

    @staticmethod
    def init_route_layer(route_spec):
        """初始化route_layer"""
        route_layer = PrepareRoute.import_csv_to_layer(route_spec) #匯入並建立layer物件
        QgsProject.instance().addMapLayer(route_layer) #把站牌序列圖層加到圖面上
        route_layer.setLabelsEnabled(True) #打開圖層的標籤
        label = PrepareRoute.set_label('StopSequence') #設定標籤
        route_layer.setLabeling(label) #設定圖層的標籤
        route_layer.renderer().symbol().setColor(QColor('red'))
        route_layer.triggerRepaint() #更新圖面

        #zoom to layer
        route_layer = iface.activeLayer()
        canvas = iface.mapCanvas()
        extent = route_layer.extent()
        canvas.setExtent(extent)
        return route_layer

    @staticmethod
    def import_csv_to_layer(route_spec):
        """匯入CSV進圖層"""
        #匯入站牌序列的csv到圖面上
        file_dir = urllib.parse.quote(
            os.path.join(route_spec['route_dir'], '{}.csv'.format(route_spec['route_name'])
        ).replace('\\', '/'))
        
        uri = (
            'file:///{dir}?type=csv&detectTypes=yes&xField={x}&yField={y}'
            '&crs=EPSG:3824&spatialIndex=no&subsetIndex=no&watchFile=no'.format(
                dir=file_dir, x='PositionLon', y='PositionLat'
            )
        ) #設定路徑、X、Y
        
        #參考https://gis.stackexchange.com/questions/358682/using-the-labeling-engine-api-vs-the-simple-labeling-interface-api-in-qgis-3
        route_layer = QgsVectorLayer(uri, route_spec['route_name'], 'delimitedtext') #建立layer物件
        return route_layer

    @staticmethod
    def set_label(field_name):
        """設定標籤樣式\n
        參考https://gis.stackexchange.com/questions/358682/using-the-labeling-engine-api-vs-the-simple-labeling-interface-api-in-qgis-3
        """
        label = QgsPalLayerSettings() #建立標籤設定物件
        label.fieldName = field_name #指定作為標籤的欄位
        label_txt_format = QgsTextFormat() #建立字型設定的欄位
        label_txt_format.setFont(QFont('華康新特黑體')) #設定字型
        label_txt_format.setSize(18) #設定大小
        label.setFormat(label_txt_format) #設定標籤設定裡的字型設定
        label = QgsVectorLayerSimpleLabeling(label) #用"label"設定SimpleLabeling(QGIS其中一種標籤形式)
        return label

class ProcessUID2node(object):
    """處理UID與點號對應相關"""

    def __init__(self, route_spec: List[str], GeometryFinder: SearchGeometry, StopUID2node_path: str, route_UID2node_dir: str, io_node_path: str):
        self.dialog = QInputDialog()
        self.dialog.setGeometry(100, 100, 0, 0)
        self.msgbox = QMessageBox()
        self.msgbox.setGeometry(100, 100, 0, 0)
        self.route_spec = route_spec
        self.route_UID2node_dir = route_UID2node_dir

        self.seq2UID_fullpath = os.path.join(self.route_spec['route_dir'], '{}.csv'.format(self.route_spec['route_name']))
        self.UID2node_fullpath = os.path.join(self.route_UID2node_dir, '{}.csv'.format(self.route_spec['route_name']))

        #讀取站序與UID的對應
        self.seq_to_UID = pd.read_csv(os.path.join(self.route_spec['route_dir'], '{}.csv'.format(self.route_spec['route_name'])))

        self.StopUID2node = pd.read_csv(StopUID2node_path)
        self.StopUID2node.set_index('InputID', inplace=True)

        self.io_node = pd.read_csv(io_node_path, encoding='big5')
        self.io_node.set_index('point', inplace=True)

        self.read_route()

        self.GeometryFinder = GeometryFinder

    def read_route(self):
        """讀取UID到點號的對應"""
        self.saved_exist = os.path.isfile(self.UID2node_fullpath)
        if self.saved_exist:
            self.route_UID2node = pd.read_csv(self.UID2node_fullpath)
        else:
            self.route_UID2node = []
        
    def modify(self):
        """人工修正UID與點號的對應"""
        normal_route = False
        self.ask_use_saved()
        if not self.saved_exist or not self.use_saved:
            self.fill_route_UID2node()

            QMessageBox().information(None, '開始', '開始修正站牌')
            #進入逐站修正前的確認，要在這邊濾除區外點
            io_zone, normal_route = self.check_outbound_stop()
            
            if normal_route:
                route_seq = self.seq_to_UID['StopSequence'].tolist()
                unconfirmed_stops = [s for s in range(len(route_seq)) if io_zone[s]]
                seq_index = unconfirmed_stops[0]
                while True:
                    seq_index, if_continue = self.choose_stop(seq_index, io_zone)
                    if if_continue:
                        current_scale = 3000
                        this_seq = self.seq_to_UID.loc[seq_index, 'StopSequence']
                        self.display_point('route', 'StopSequence', this_seq, current_scale)
                        self.get_newID(seq_index, current_scale)
                        seq_index = unconfirmed_stops[(unconfirmed_stops.index(seq_index) + 1) % len(unconfirmed_stops)]
                    else:
                        second_check = QMessageBox().information(
                            None, '再次確認', '要結束修正點號嗎？', 
                            buttons=QMessageBox.Yes|QMessageBox.No
                        )
                        if second_check == QMessageBox.Yes:
                            break
            
            #回存該路線修正後的UID與點號對應
            self.route_UID2node.to_csv(self.UID2node_fullpath, index=False)

    def ask_use_saved(self):
        """詢問是否使用既有成果"""
        self.use_saved = False
        if self.saved_exist:
            answer = QMessageBox().information(None, '確認', 
                '找到已經校正過的點號對應\n'
                '要沿用既有的點號對應校正成果嗎？', 
                buttons=QMessageBox.Yes|QMessageBox.No)
            if answer == QMessageBox.Yes:
                self.use_saved = True

    def choose_stop(self, seq_index, io_zone: List[bool]):
        """選擇站牌"""
        choice_set = []
        stop_list = []
        for i in range(self.seq_to_UID.shape[0]):
            if io_zone[i]:
                choice_set.append(i)
                stop_list.append(
                    '{} ({}): {}'.format(
                        self.seq_to_UID.loc[i, 'StopSequence'], 
                        self.seq_to_UID.loc[i, 'StopUID'], 
                        self.route_UID2node.loc[i, 'TargetID'].tolist()
                    )
                )
        stop_str, choose_OK = self.dialog.getItem(
            self.dialog, '選擇站牌', 
            '選擇要編輯的站牌\n要跳出則按取消', stop_list, 
            current=choice_set.index(seq_index), 
            editable=False
        )
        if choice_set:
            return choice_set[stop_list.index(stop_str)], choose_OK
        else:
            return seq_index, choose_OK

    def check_outbound_stop(self):
        """
        處理區外站牌，回傳站牌在區內與否的io_zone: List[bool]及代表處理路線與否的normal_route\n
        如果路線中間跑掉就不是normal_route\n
        如果是normal_route就輸入進出區域的邊界點，直接修改route_UID2node
        """
        route_StopUID = self.seq_to_UID['StopUID'].tolist()
        io_zone = [s in self.StopUID2node.index for s in route_StopUID]
        normal_route = True
        #先標記有到區外的路線
        for s in io_zone:
            normal_route = s and normal_route
        
        #有到區外的路線再繼續檢查下去
        if not normal_route:
            in_iloc = -1
            out_iloc = len(io_zone)
            
            #進來區內
            num_in = 0
            for i in range(len(io_zone) - 1):
                if not io_zone[i] and io_zone[i] != io_zone[i+1]:
                    normal_route = True
                    num_in += 1
                    in_iloc = i

            #跑到區外
            num_out = 0
            for i in range(len(io_zone) - 1, 0, -1):
                if not io_zone[i] and io_zone[i] != io_zone[i-1]:
                    normal_route = True
                    num_out += 1
                    out_iloc = i
            
            #剔除進進出出的路線；只能處理中間在區內，所以要排除中間在區外
            if normal_route and ((num_in > 1 or num_out > 1) or out_iloc < in_iloc):
                normal_route = False
            
            #選取進入點
            if normal_route and num_in == 1:
                self.set_border_node(in_iloc, True)
            
            #選取離開點
            if normal_route and num_out == 1:
                self.set_border_node(out_iloc, False)
        
        return io_zone, normal_route

    def set_border_node(self, border_iloc: int, into_the_zone: bool):
        """設定邊界節點"""
        route_StopUID = self.seq_to_UID['StopUID'].tolist()
        if into_the_zone:
            point_list = self.io_node[self.io_node.type >= 0].index.tolist()
            node_list = self.io_node.node[self.io_node.type >= 0].tolist()
            display_list = ['{} ({})'.format(point_list[i], node_list[i]) for i in range(len(point_list))]
            point_type = '進入'
            outbound_range = range(0, border_iloc + 1)
        else:
            point_list = self.io_node[self.io_node.type <= 0].index.tolist()
            node_list = self.io_node.node[self.io_node.type <= 0].tolist()
            display_list = ['{} ({})'.format(point_list[i], node_list[i]) for i in range(len(point_list))]
            point_type = '離開'
            outbound_range = range(border_iloc, len(route_StopUID))
        
        while True:
            point_str, OK = self.dialog.getItem(
                self.dialog, '選取{}點'.format(point_type),
                '請選取本路線{}區域的位置'.format(point_type),
                display_list, 
                editable=False
            )
            if OK:
                chosen_node = node_list[point_list.index(point_str.split(' ')[0])]
                path_layer = self.GeometryFinder.display_points(nodes_list=[chosen_node], color='cyan')
                iface.mapCanvas().zoomScale(25000)
                iface.mapCanvas().refresh()
                option = self.msgbox.information(
                    self.msgbox, '小等一下',
                    '確定是這個點嗎？\n'
                    '{}: {}'.format(point_str, chosen_node),
                    buttons=QMessageBox.Yes|QMessageBox.No
                )
                if option == QMessageBox.Yes:
                    for i in outbound_range:
                        self.route_UID2node.loc[i, 'TargetID'] = chosen_node
                    QgsProject.instance().removeMapLayer(path_layer)
                    break

    def display_point(self, layer_name: str, attribute_name: str, value: int, scale: int):
        """在地圖上顯示要修改的那個點"""
        point = self.GeometryFinder.get_point(layer_name, attribute_name, [value])[0]
        if point != []:
            iface.mapCanvas().setCenter(point)
            iface.mapCanvas().zoomScale(scale)
            iface.mapCanvas().refresh()
    
    def fill_route_UID2node(self):
        """把路線的UID與點號對應初始化，如果已經有值就略過"""
        if not self.use_saved:
            InputID = self.seq_to_UID['StopUID'].tolist()
            TargetID = []
            for ID in InputID:
                if ID in self.StopUID2node.index:
                    node_num = self.StopUID2node.loc[[ID], 'TargetID'].tolist()[0]
                else:
                    node_num = 0
                TargetID.append(node_num)
            self.route_UID2node = pd.DataFrame.from_dict({'InputID': InputID, 'TargetID': TargetID})

    def get_newID(self, seq_index: int, scale: int):
        """設定ID對應"""
        this_seq = self.seq_to_UID.loc[seq_index, 'StopSequence']
        this_UID = self.seq_to_UID.loc[seq_index, 'StopUID']
        old_ID = self.route_UID2node.loc[seq_index, 'TargetID']
        while True:
            new_ID, OK = self.dialog.getInt(
                self.dialog, '新的ID', 
                '{} ({}): {} ({}/{})\n'
                '請輸入新的ID\n'
                '按取消來更改比例尺'.format(this_seq, this_UID, old_ID, seq_index + 1, self.seq_to_UID.shape[0]), 
                value=old_ID
            )
            if OK:
                self.display_point('node', 'N', new_ID, scale)
                if new_ID != old_ID:
                    SN_dist = self.stop_to_node_distance(seq_index, new_ID)
                    option = self.msgbox.information(
                        self.msgbox, '確認新的節點',
                        '新輸入的節點({})與站牌距離約{:.2f}m\n'
                        '確定是這個點嗎？'.format(new_ID, SN_dist),
                        buttons=QMessageBox.Yes|QMessageBox.No
                    )
                    if option == QMessageBox.No:
                        continue
                self.route_UID2node.TargetID[seq_index] = new_ID
                break
            else:
                self.set_scale(scale)
    
    def stop_to_node_distance(self, stop: int, node: int):
        """算站牌到節點的距離"""
        stop_point = self.GeometryFinder.get_point('route', 'StopSequence', [self.seq_to_UID.loc[stop, 'StopSequence']])[0]
        node_point = self.GeometryFinder.get_point('node', 'N', [node])[0]
        distance = self.GeometryFinder.distance(point_pair=[stop_point, node_point])
        return distance

    def set_scale(self, current_scale):
        """設定比例尺"""
        while True:
            iface.mapCanvas().zoomScale(current_scale)
            iface.mapCanvas().refresh()
            new_scale, scale_change_OK = self.dialog.getInt(
                self.dialog, '更改比例尺','輸入新的比例尺', value=current_scale
            )
            if scale_change_OK:
                if new_scale > 0:
                    if new_scale != current_scale:
                        current_scale = new_scale
                    else:
                        if_quit = self.msgbox.information(
                            self.msgbox, '是否跳出', 
                            '輸入相同比例尺，要結束更改比例尺嗎？',
                            buttons=QMessageBox.Yes|QMessageBox.No
                        )
                        if if_quit == QMessageBox.Yes:
                            break
                else:
                    self.dialog.information(self.dialog, '錯誤', '請輸入正整數')
            else:
                if_quit = self.msgbox.information(
                    self.msgbox, '再次確認', '要結束更改比例尺嗎？',
                    buttons=QMessageBox.Ok|QMessageBox.Cancel
                )
                if if_quit == QMessageBox.Ok:
                    break

class FindPath(object):
    """生成最短路徑的相關函式"""

    def __init__(self, GeometryFinder: SearchGeometry, SPathFinder: ShortestPath):
        self.dialog = QInputDialog()
        self.dialog.setGeometry(100, 100, 0, 0)
        self.msgbox = QMessageBox()
        self.msgbox.setGeometry(100, 100, 0, 0)
        self.GeometryFinder = GeometryFinder
        self.SPathFinder = SPathFinder
        self.max_accepted_dist, _ = QInputDialog().getInt(
            None, '想請教一下', '請輸入不分段計算最短路徑的\n' '最大站間直線距離(km)', value=5
        )

    def set_path_midpoint(self, stop_nodes: List[int], bypass_limit: bool):
        current_start_id = 1
        path_passed_nodes = [s for s in stop_nodes]

        OD_dist = self.GeometryFinder.distance(
            node_pair=path_passed_nodes[current_start_id-1:current_start_id+1]
        )
        if bypass_limit or OD_dist > self.max_accepted_dist * 1000:
            while True:
                path_layer = self.GeometryFinder.display_points(
                    nodes_list=path_passed_nodes[current_start_id-1:current_start_id+1], color='cyan'
                )
                if OD_dist > self.max_accepted_dist * 1000:
                    msgbox_title = '距離太大了'
                    msgbox_compare = '大於'
                else:
                    msgbox_title = '距離還OK'
                    msgbox_compare = '小於'
                Option = self.msgbox.information(
                    self.msgbox, msgbox_title, 
                    '站間距離為 {:.3f}公里，「{}」你設定的 {}公里\n'
                    '要手動輸入中間點嗎？'.format(OD_dist / 1000, msgbox_compare, self.max_accepted_dist), 
                    buttons=QMessageBox.Yes|QMessageBox.No
                )
                if Option == QMessageBox.No:
                    QgsProject.instance().removeMapLayer(path_layer)
                    break
                
                while True:
                    new_midpoint, OK = self.dialog.getInt(
                        self.dialog, '手動輸入站間經過點',
                        '請輸入中間點的點號(N)\n'
                        '(插入點前的點: {}\n'
                        ' 插入點後的點: {})'.format(
                            ', '.join(map(str, path_passed_nodes[:current_start_id])),
                            ', '.join(map(str, path_passed_nodes[current_start_id:]))
                        ),
                    )
                    if OK:
                        if self.GeometryFinder.is_in_zone('node', 'N', [new_midpoint]):
                            new_points = self.GeometryFinder.get_point(
                                'node', 'N', [path_passed_nodes[current_start_id-1], new_midpoint]
                            )
                            new_dist = self.GeometryFinder.distance(point_pair=new_points)
                            new_path_layer = self.GeometryFinder.display_points(points_list=new_points, color='cyan')
                            choice = self.msgbox.information(
                                self.msgbox, '確認',
                                '輸入的點({})跟上一點({})距離約 {:.2f} km\n'
                                '確定是這個點嗎？'.format(new_midpoint, path_passed_nodes[current_start_id-1], new_dist / 1000),
                                buttons=QMessageBox.Yes|QMessageBox.No
                            )
                            
                            if choice == QMessageBox.No:
                                QgsProject.instance().removeMapLayer(new_path_layer)
                                continue
                            else:
                                QgsProject.instance().removeMapLayer(new_path_layer)
                                QgsProject.instance().removeMapLayer(path_layer)
                                path_passed_nodes.insert(current_start_id, new_midpoint)
                                current_start_id += 1
                                OD_dist = self.GeometryFinder.distance(node_pair=path_passed_nodes[current_start_id-1:current_start_id+1])
                                break
                        else:
                            self.msgbox.information(self.msgbox, '錯誤', '輸入的點({})不在地圖裡'.format(new_midpoint))
                            continue
                    else:
                        if current_start_id > 1:
                            choice = self.msgbox.information(
                                self.msgbox, '疑問',
                                '是否刪除上一個中間點({})？'.format(path_passed_nodes[current_start_id-1]),
                                buttons=QMessageBox.Yes|QMessageBox.No
                            )
                            if choice == QMessageBox.Yes:
                                path_passed_nodes.pop(current_start_id - 1)
                                current_start_id -= 1
                                break
                        
                        choice = self.msgbox.information(self.msgbox, '疑問', '是否結束編輯？', buttons=QMessageBox.Yes|QMessageBox.No)
                        if choice == QMessageBox.Yes:
                            break

        # set the start and the end of each subpath
        return list(zip(path_passed_nodes, path_passed_nodes[1:]))

    def find_path(self, find_path_todo: list):
        """給定起終點，回傳路徑"""
        all_path_list = []
        for OD_str in find_path_todo:
            OD_node = list(map(int, OD_str))
            passed_node_list, _ = self.SPathFinder.find_shortest_path(OD_node)
            if len(passed_node_list) == 0:
                return [], False
            
            all_path_list.append(passed_node_list)
            
        path_list = [find_path_todo[0][0]]
        for sp in all_path_list:
            for node in sp[1:]:
                path_list.append(node)

        return path_list, True

class ProcessResult(object):
    """確認結果與修改錯誤"""
    @staticmethod
    def manually_input(stop_node: List[int], passed_node_list: List[int], output_dir, path_filename):
        """手動輸入最短路徑"""
        further_check = False
        check_path_dialog = QInputDialog()
        check_path_dialog.setGeometry(100, 100, 0, 0)
        
        while True:
            passed_node_str, result_OK = check_path_dialog.getText(
                check_path_dialog, '手動輸入', 
                '{} -> {}\n'
                '輸入站間路徑\n'
                '請都以正數輸入，程式會自己轉換\n'
                '真的有區間找不出來就填0，之後再校正\n'
                '需要之後再校正就按取消'.format(stop_node[0], stop_node[1]), text=','.join(map(str, passed_node_list))
            )
            if result_OK and (0 not in list(map(int, passed_node_str.split(',')))):
                if ProcessResult.second_check('確定是正確結果並結束修正本路徑嗎？', passed_node_list, output_dir['checked_path'], path_filename):
                    passed_node_list = list(map(int, passed_node_str.split(',')))
                    break
            else:
                if ProcessResult.second_check('要將路徑移至待檢查區嗎？', passed_node_list, output_dir['frthr_inspct'], path_filename):
                    further_check = True
                    break
            
        return passed_node_list, further_check

    @staticmethod
    def second_check(dialog, node_list, dest_dir, filename):
        confirm_dialog = QMessageBox()
        confirm_dialog.setGeometry(100, 100, 0, 0)
        second_check = confirm_dialog.information(confirm_dialog, '再次確認', dialog, buttons=QMessageBox.Yes|QMessageBox.No)
        if second_check == QMessageBox.Yes:
            ProcessPath.save(node_list, dest_dir, filename)
            return True
        return False

def main():
    # 選擇資料夾
    D_drive = 'D:/Users/63707/Documents/python3/bus_route/'
    P_drive = 'P:/09091-中臺區域模式/Working/'

    data_dir = os.path.join(D_drive, 'find_path_test')

    UID2node_path = os.path.join(data_dir, 'C_TWN_bus_stop_distance_matrix.csv')
    io_node_path = os.path.join(data_dir, '進出區域點號.csv')

    output_dir = {
        'route_UID2node': os.path.join(data_dir, '00_route_UID2node'),
        'init_path': os.path.join(data_dir, '01_initial_path_result'),
        'frthr_inspct': os.path.join(data_dir, '02_further_inspect'),
        'checked_path': os.path.join(data_dir, '03_checked_path'),
        'result_route': os.path.join(data_dir, '05_final_result_route'),
    }

    zone2dir = {
        'MIA': 'City/MiaoliCounty/',
        'TXG': 'City/Taichung/',
        'CHA': 'City/ChanghuaCounty/',
        'NAN': 'City/NantouCounty/',
        'YUN': 'City/YunlinCounty/',
        'THB': 'InterCity'
    }
    node_csv_path = 'P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_NET_node.csv'
    road_csv_path = 'P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_NET_link.csv'

    excluded_roadtype = ['RR', 'ZL', 'WL', 'TL']
    node_dict = ImportNetwork.get_node_list(node_csv_path, min_N=5001, max_N=150000)
    road_dict = ImportNetwork.get_road_list(road_csv_path, excluded_roadtype)
    road_tree = ImportNetwork.generate_tree(node_dict, road_dict)

    shortest_path_finder = ShortestPath(node_dict, road_dict, road_tree)

    #選取圖層: 因為有可能有同名圖層，會回傳list回來，所以要挑第一個
    vlayer = {}
    vlayer['road'] = QgsProject.instance().mapLayersByName('C_TWN_ROAD_picked')[0]
    vlayer['node'] = QgsProject.instance().mapLayersByName('C_TWN_ROAD_picked_node')[0]
    
    ptx_data_dir = os.path.join(D_drive, 'PTX_data/CSV_20210407/Bus')

    while True:
        route_spec, OK = PrepareRoute.choose_route(ptx_data_dir, zone2dir)

        if OK:
            vlayer['route'] = PrepareRoute.init_route_layer(route_spec) #建立並顯示route_layer
            iface.mapCanvas().freeze(False) #讓圖面可以隨時更新
            geometry_finder = SearchGeometry(vlayer)

            #####讀取站牌最近節點的屬性資料
            bus_stop_mapper = ProcessUID2node(route_spec, geometry_finder, UID2node_path, output_dir['route_UID2node'], io_node_path)
            bus_stop_mapper.modify()

            if_proceed = QMessageBox().information(None, '詢問', '要繼續尋找站間路徑嗎？', buttons=QMessageBox.Yes|QMessageBox.No)
            if if_proceed == QMessageBox.No:
                continue

            #####找站間最短路徑
            path_finder = FindPath(geometry_finder, shortest_path_finder)
            #(#1, #2), (#2, #3)... 以這樣的順序一組一組把路徑串起來
            node_list = list(map(int, bus_stop_mapper.route_UID2node['TargetID'].tolist()))
            uid_list = bus_stop_mapper.seq_to_UID['StopUID'].tolist()
            stop_pair = list(zip(node_list, node_list[1:]))
            uid_pair = list(zip(uid_list, uid_list[1:]))
            further_check_i = []
            for i, stop_nodes in enumerate(stop_pair):
                stop_uids = uid_pair[i]
                path_filename = '{}({})_{}({})'.format(stop_nodes[0], stop_uids[0], stop_nodes[1], stop_uids[1])
                if stop_nodes[0] != stop_nodes[1]: #如果頭尾不同站才找路徑
                    #讀取已儲存的路徑
                    path_path = os.path.join(output_dir['checked_path'], '{}.txt'.format(path_filename))
                    if not os.path.isfile(path_path):
                        path_list = [stop_nodes[0], 0, stop_nodes[1]]
                        bypass_limit = False
                        while True:
                            # set midpoints
                            find_path_todo = path_finder.set_path_midpoint(stop_nodes, bypass_limit)
                            path_list, result_OK = path_finder.find_path(find_path_todo)
                            
                            if result_OK:
                                ProcessPath.save(path_list, output_dir['init_path'], path_filename)
                                #確認路徑
                                path_layer = geometry_finder.display_points(nodes_list=path_list, color='cyan')
                                option = QMessageBox().information(
                                    None, '疑問', '接受這樣的結果嗎？', 
                                    buttons=QMessageBox.Yes|QMessageBox.No
                                )
                                QgsProject.instance().removeMapLayer(path_layer)
                                if option == QMessageBox.Yes:
                                    ProcessPath.save(path_list, output_dir['checked_path'], path_filename)
                                    break
                                else:
                                    option2 = QMessageBox().information(
                                        None, '疑問', '要設定中間點讓電腦重算嗎？', 
                                        buttons=QMessageBox.Yes|QMessageBox.No
                                    )
                                    if option2 == QMessageBox.Yes:
                                        bypass_limit = True
                                        continue
                                    else:
                                        further_check_i.append(i)
                                        break

                            else:
                                option = QMessageBox().information(
                                    None, '錯誤',
                                    '這樣的組合找不到站間路徑\n'
                                    '要重新輸入中間點嗎？', 
                                    buttons=QMessageBox.Yes|QMessageBox.No
                                )
                                if option == QMessageBox.No:
                                    ProcessPath.save(path_list, output_dir['frthr_inspct'], path_filename)
                                    further_check_i.append(i)
                                    break
                                else:
                                    bypass_limit = True
                                    continue
                else:
                    path_list = [stop_nodes[0]]
                    ProcessPath.save(path_list, output_dir['checked_path'], path_filename) #把找到的路徑存起來
        
            ######校正結果
            further_check = False
            for i in further_check_i:
                stop_nodes = stop_pair[i]
                stop_uids = uid_pair[i]
                path_filename = '{}({})_{}({})'.format(stop_nodes[0], stop_uids[0], stop_nodes[1], stop_uids[1])
                path_layer = geometry_finder.display_points(nodes_list=stop_nodes, color='cyan')
                manual_input = QMessageBox().information(
                    None, '載入失敗', '未有該區間已輸出路徑\n要手動輸入嗎？',
                    buttons=QMessageBox.Yes|QMessageBox.No
                )
                if manual_input == QMessageBox.No:
                    ProcessPath.save(path_list, output_dir['frthr_inspct'], path_filename)
                    QgsProject.instance().removeMapLayer(path_layer)
                    continue

                path_list, further_check = ProcessResult.manually_input(stop_nodes, path_list, output_dir, path_filename)
                QgsProject.instance().removeMapLayer(path_layer)

            if not further_check:
                QMessageBox().information(None, 'OK OK', '完成確認，都沒問題')
                QgsProject.instance().removeMapLayer(vlayer['route'])
            else:
                QMessageBox().information(None, 'Oh Oh', '完成確認，有要進一步確認的地方')

        else:
            second_check = QMessageBox().information(None, '再次確認', '真的要結束嗎？ ｡ﾟヽ(ﾟ´Д`)ﾉﾟ｡', buttons=QMessageBox.Yes|QMessageBox.No)
            if second_check == QMessageBox.Yes:
                break

# if __name__ == '__main__':
#     main()
main()
