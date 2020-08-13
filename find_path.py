# -*- coding: utf-8 -*-

import os
import urllib.parse
from math import cos, radians, sin, sqrt, tan
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

    def save(self, path_list: List[int], save_dir: str):
        """把站牌間路徑儲存成文字檔"""
        path_str = ','.join(map(str, path_list))
        if len(path_list) == 1:
            path_path = os.path.join(
                save_dir, '{}_{}.txt'.format(path_list[0], path_list[0])
            ) #路徑的路徑
        else:
            path_path = os.path.join(
                save_dir, '{}_{}.txt'.format(path_list[0], path_list[-1])
            ) #路徑的路徑
        path_file = open(path_path, 'w')
        path_file.write(path_str)
        path_file.close()

    def load(self, OD_node: List[int], load_dir: str):
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

    def move(self, ori_node: int, des_node: int, ori_dir: str, des_dir: str):
        sucess = False
        ori_file = os.path.join(ori_dir, '{}_{}.txt'.format(ori_node, des_node))
        if os.path.isfile(ori_file):
            copy2(ori_file, des_dir)
            sucess = True
        return sucess

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
                x0, y0 = LatLonToTWD97().convert(
                    radians(point_pair[0].y()), radians(point_pair[0].x())
                )
                x1, y1 = LatLonToTWD97().convert(
                    radians(point_pair[1].y()), radians(point_pair[1].x())
                )
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

    def is_in_layer(self, layer_name: str, attribute_name: str, value_list: list):
        """確認點號存在且不是0，有一個錯就是全錯，拿不到分數啦"""
        in_layer = True
        point_list = self.get_point(layer_name, attribute_name, value_list)
        for p in point_list:
            in_layer = p != [] and in_layer
        return in_layer
    
    def layer(self, layer_name):
        if layer_name in self.vlayer:
            return self.vlayer[layer_name]
        else:
            return None

    def display_points(self, nodes_list=None, points_list=None):
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

            nodes_layer.renderer().symbol().setColor(QColor('yellow'))
            # add the layer to the canvas
            QgsProject.instance().addMapLayers([nodes_layer])

            #zoom to frame
            extent = nodes_layer.extent()
            iface.mapCanvas().setExtent(extent)

            #zoom out a little bit
            iface.mapCanvas().setWheelFactor(1.5)
            iface.mapCanvas().zoomOut()

        return nodes_layer

class PrepareRoute(object):
    """匯入公車路線相關"""

    def choose_route(self, data_dir, zone2dir):
        """選擇路線"""
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
                break

        return route_spec, OK

    def init_route_layer(self, route_spec):
        """初始化route_layer"""
        route_layer = self.import_csv_to_layer(route_spec) #匯入並建立layer物件
        QgsProject.instance().addMapLayer(route_layer) #把站牌序列圖層加到圖面上
        route_layer.setLabelsEnabled(True) #打開圖層的標籤
        label = self.set_label('StopSequence') #設定標籤
        route_layer.setLabeling(label) #設定圖層的標籤
        route_layer.renderer().symbol().setColor(QColor('red'))
        route_layer.triggerRepaint() #更新圖面

        #zoom to layer
        route_layer = iface.activeLayer()
        canvas = iface.mapCanvas()
        extent = route_layer.extent()
        canvas.setExtent(extent)
        return route_layer

    def import_csv_to_layer(self, route_spec):
        """匯入CSV進圖層"""
        file_name = '{}.csv'.format('_'.join(route_spec[0:3])) #站牌序列檔名生成
        
        #匯入站牌序列的csv到圖面上
        url = 'file:///%s?type=csv&detectTypes=yes&xField=%s&yField=%s&crs=EPSG:3824&spatialIndex=no&subsetIndex=no&watchFile=no' % \
            (urllib.parse.quote(os.path.join(route_spec[3], file_name).replace('\\', '/')), 'PositionLon', 'PositionLat') #設定路徑、X、Y
        
        #參考https://gis.stackexchange.com/questions/358682/using-the-labeling-engine-api-vs-the-simple-labeling-interface-api-in-qgis-3
        route_layer = QgsVectorLayer(url, '{}_{}'.format(route_spec[0], route_spec[2]), 'delimitedtext') #建立layer物件
        return route_layer

    def set_label(self, field_name):
        """設定標籤樣式\n
        參考https://gis.stackexchange.com/questions/358682/using-the-labeling-engine-api-vs-the-simple-labeling-interface-api-in-qgis-3
        """
        label = QgsPalLayerSettings() #建立標籤設定物件
        label.fieldName = field_name #指定作為標籤的欄位
        label_txt_format = QgsTextFormat() #建立字型設定的欄位
        label_txt_format.setFont(QFont('華康中圓體')) #設定字型
        label_txt_format.setSize(18) #設定大小
        label.setFormat(label_txt_format) #設定標籤設定裡的字型設定
        label = QgsVectorLayerSimpleLabeling(label) #用"label"設定SimpleLabeling(QGIS其中一種標籤形式)
        return label

class ProcessUID2node(object):
    """處理UID與點號對應相關"""

    def __init__(
        self, route_spec: List[str], 
        GeometryFinder: SearchGeometry, StopUID2node_path: str, route_UID2node_dir: str, io_node_path: str
    ):
        self.dialog = QInputDialog()
        self.dialog.setGeometry(100, 100, 0, 0)
        self.msgbox = QMessageBox()
        self.msgbox.setGeometry(100, 100, 0, 0)
        self.route_spec = route_spec
        self.read_seq_to_UID()

        self.StopUID2node = pd.read_csv(StopUID2node_path)
        self.StopUID2node.set_index('InputID', inplace=True)

        self.io_node = pd.read_csv(io_node_path)
        self.io_node.set_index('point', inplace=True)

        self.read_route(route_UID2node_dir)

        self.GeometryFinder = GeometryFinder

    def read_seq_to_UID(self):
        """讀取站序與UID的對應"""
        self.seq_to_UID = pd.read_csv(
            os.path.join(self.route_spec[3], '{}.csv'.format('_'.join(self.route_spec[0:3])))
        )

    def read_route(self, file_dir: str):
        """讀取UID到點號的對應"""
        route_chart_path = os.path.join(file_dir, '{}.csv'.format('_'.join(self.route_spec[0:3])))
        self.saved_exist = os.path.isfile(route_chart_path)
        if self.saved_exist:
            self.route_UID2node = pd.read_csv(route_chart_path)
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
                        seq_index = unconfirmed_stops[
                            (unconfirmed_stops.index(seq_index) + 1) % len(unconfirmed_stops)
                        ]
                    else:
                        second_check = QMessageBox().information(
                            None, '再次確認', '要結束修正點號嗎？', 
                            buttons=QMessageBox.Yes|QMessageBox.No
                        )
                        if second_check == QMessageBox.Yes:
                            break

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

    def save_modified_route(self, file_dir: str):
        """回存該路線修正後的UID與點號對應"""
        if not self.saved_exist or not self.use_saved:
            self.route_UID2node.to_csv(
                os.path.join(
                    file_dir, '{}.csv'.format('_'.join(self.route_spec[0:3]))
                ),
                index=False
            )

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
                path_layer = self.GeometryFinder.display_points(nodes_list=[chosen_node])
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
                '按取消來更改比例尺'.format(
                    this_seq, this_UID, old_ID,
                    seq_index + 1, self.seq_to_UID.shape[0]
                ), 
                value=old_ID
            )
            if OK:
                if new_ID != old_ID:
                    self.display_point('node', 'N', new_ID, scale)
                    SN_dist = self.stop_to_node_distance(seq_index, new_ID)
                    if SN_dist > 100:
                        option = self.msgbox.information(
                            self.msgbox, '新的節點有點遠',
                            '新輸入的節點({})與站牌距離約{:.2f}m\n'
                            '這樣有點遠，確定是這個點嗎？'.format(new_ID, SN_dist),
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
        stop_point = self.GeometryFinder.get_point(
            'route', 'StopSequence', [self.seq_to_UID.loc[stop, 'StopSequence']]
        )[0]
        node_point = self.GeometryFinder.get_point('node', 'N', [node])[0]
        distance = self.GeometryFinder.distance(point_pair=[stop_point, node_point])
        return distance

    def set_scale(self, current_scale):
        """設定比例尺"""
        while True:
            iface.mapCanvas().zoomScale(current_scale)
            iface.mapCanvas().refresh()
            new_scale, scale_change_OK = self.dialog.getInt(self.dialog, '更改比例尺', \
                '輸入新的比例尺', value=current_scale)
            if scale_change_OK:
                if new_scale > 0:
                    if new_scale != current_scale:
                        current_scale = new_scale
                    else:
                        if_quit = self.msgbox.information(
                            self.msgbox, '是否跳出', 
                            '輸入相同比例尺，要結束更改比例尺嗎？', \
                            buttons=QMessageBox.Yes|QMessageBox.No
                        )
                        if if_quit == QMessageBox.Yes:
                            break
                else:
                    self.dialog.information(self.dialog, '錯誤', '請輸入正整數')
            else:
                if_quit = self.msgbox.information(self.msgbox, '再次確認', '要結束更改比例尺嗎？', \
                    buttons=QMessageBox.Ok|QMessageBox.Cancel)
                if if_quit == QMessageBox.Ok:
                    break

    def get_node_list(self):
        return self.route_UID2node['TargetID'].tolist()

class FindPathUtils(object):
    """找最短路徑會用到的瑣碎函式"""

    def load_shapefile(self, shp_path, layer_name):
        """加入SHP檔案到圖面上，現在沒人用"""
        vlayer = QgsVectorLayer(shp_path, layer_name, "ogr")
        if not vlayer.isValid():
            print(layer_name + ' failed to load!')
        else:
            print('success to load ' + layer_name)
            QgsProject.instance().addMapLayers([vlayer])
        return vlayer

    def pairwise(self, iterable):
        """參考https://stackoverflow.com/questions/5764782/iterate-through-pairs-of-items-in-a-python-list?lq=1\n
        s -> (s0, s1), (s1, s2), (s2, s3), ..."""
        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)

class FindPath(object):
    """生成最短路徑的相關函式"""

    def __init__(self, GeometryFinder: SearchGeometry):
        self.dialog = QInputDialog()
        self.dialog.setGeometry(100, 100, 0, 0)
        self.msgbox = QMessageBox()
        self.msgbox.setGeometry(100, 100, 0, 0)
        self.GeometryFinder = GeometryFinder
        self.max_accepted_dist, _ = QInputDialog().getInt(
            None, '想請教一下',
            '請輸入不分段計算最短路徑的\n'
            '最大站間直線距離(km)',
            value=5
        )

    def set_path_midpoint(self, stop_nodes: List[int]):
        current_start_id = 1
        path_passed_nodes = [s for s in stop_nodes]

        OD_dist = self.GeometryFinder.distance(
            node_pair=path_passed_nodes[current_start_id-1:current_start_id+1]
        )
        if OD_dist > self.max_accepted_dist * 1000:
            while True:
                path_layer = self.GeometryFinder.display_points(
                    nodes_list=path_passed_nodes[current_start_id-1:current_start_id+1]
                )
                if OD_dist > self.max_accepted_dist * 1000:
                    msgbox_title = '距離太大了'
                    msgbox_compare = '大於'
                else:
                    msgbox_title = '距離還OK'
                    msgbox_compare = '小於'
                Option = self.msgbox.information(
                    self.msgbox, msgbox_title, 
                    '站間距離為 {:.3f}公里\n'
                    '「{}」你設定的 {}公里\n'
                    '要手動輸入中間點嗎？'.format(
                        OD_dist / 1000, msgbox_compare, self.max_accepted_dist
                    ), 
                    buttons=QMessageBox.Yes|QMessageBox.No
                )
                if Option == QMessageBox.No:
                    QgsProject.instance().removeMapLayer(path_layer)
                    break
                
                while True:
                    new_midpoint, OK = self.dialog.getInt(
                        self.dialog, '手動輸入站間經過點',
                        '請輸入中間點的點號(N)\n'
                        '按Ok確認，按Cancel刪除上一個輸入結果\n'
                        '不過抱歉，我還不知道要怎麼寫\n'
                        '所以請開另外一個QGIS來找點號\n'
                        '(插入點前的點: {}\n'
                        ' 插入點後的點: {})'.format(
                            ', '.join(map(str, path_passed_nodes[:current_start_id])),
                            ', '.join(map(str, path_passed_nodes[current_start_id:]))
                        )
                    )
                    if OK:
                        if self.GeometryFinder.is_in_layer('node', 'N', [new_midpoint]):
                            new_points = self.GeometryFinder.get_point(
                                'node', 'N', 
                                [path_passed_nodes[current_start_id-1], new_midpoint]
                            )
                            new_dist = self.GeometryFinder.distance(point_pair=new_points)
                            if new_dist > self.max_accepted_dist * 1000:
                                new_path_layer = self.GeometryFinder.display_points(
                                    points_list=new_points
                                )
                                choice = self.msgbox.information(
                                    self.msgbox, '疑問',
                                    '輸入的點({})跟上一點({})距離還是太遠\n'
                                    '(距離約 {:.2f} km)\n'
                                    '確定是這個點嗎？'.format(
                                        new_midpoint, 
                                        path_passed_nodes[current_start_id-1],
                                        new_dist / 1000
                                    ),
                                    buttons=QMessageBox.Yes|QMessageBox.No
                                )
                                QgsProject.instance().removeMapLayer(new_path_layer)
                                if choice == QMessageBox.No:
                                    continue
                            
                            QgsProject.instance().removeMapLayer(path_layer)
                            path_passed_nodes.insert(current_start_id, new_midpoint)
                            current_start_id += 1
                            OD_dist = self.GeometryFinder.distance(
                                node_pair=path_passed_nodes[current_start_id-1:current_start_id+1]
                            )
                            break
                        else:
                            self.msgbox.information(
                                self.msgbox, '錯誤',
                                '輸入的點({})不在地圖裡'.format(new_midpoint)
                            )
                            continue
                    else:
                        if current_start_id > 1:
                            choice = self.msgbox.information(
                                self.msgbox, '疑問',
                                '是否刪除上一個中間點({})？'.format(
                                    path_passed_nodes[current_start_id-1]
                                ),
                                buttons=QMessageBox.Yes|QMessageBox.No
                            )
                            if choice == QMessageBox.Yes:
                                path_passed_nodes.pop(current_start_id-1)
                                current_start_id -= 1
                                break
                            else:
                                continue

        return path_passed_nodes

    def find_path(self, OD_node: list):
        """給定起終點，回傳路徑"""
        passed_node_list = []
        good_result = True
        OD_point = self.GeometryFinder.get_point('node', 'N', OD_node)
        #框出路網的框框
        frame_layer = self.draw_frame(
            OD_point
        )
        #裁切路網
        clp_rd_lyr, good_result = self.clip_road(
            frame_layer, good_result
        )
        #尋找最短路徑
        shortest_path_lyr, good_result = self.shortest_path(
            OD_point, clp_rd_lyr, good_result
        )
        #取交集
        intrsctn_lyr, good_result = self.intersection(
            clp_rd_lyr, shortest_path_lyr, good_result
        ) 
        #取得路徑序列
        passed_node_list, result_OK = self.find_passed_nodes(
            intrsctn_lyr, OD_node, good_result
        ) 
        
        #刪除臨時產生的圖層
        QgsProject.instance().removeMapLayer(frame_layer)
        if clp_rd_lyr != []:
            QgsProject.instance().removeMapLayer(clp_rd_lyr)
        if shortest_path_lyr != []:
            QgsProject.instance().removeMapLayer(shortest_path_lyr)
        if intrsctn_lyr != []:
            QgsProject.instance().removeMapLayer(intrsctn_lyr)

        return passed_node_list, result_OK

    def draw_frame(self, OD_point: list):
        """框出路網的框框\n
        https://gis.stackexchange.com/questions/86812/how-to-draw-polygons-from-the-python-console
        """
        frame_layer = QgsVectorLayer('Polygon', 'frame' , "memory")
        pr = frame_layer.dataProvider() 
        poly = QgsFeature()
        points = self.set_boundary(OD_point) #設定框框
        poly.setGeometry(QgsGeometry.fromPolygonXY([points]))
        pr.addFeatures([poly])
        frame_layer.updateExtents()
        QgsProject.instance().addMapLayers([frame_layer])
        
        #zoom to frame
        canvas = iface.mapCanvas()
        extent = frame_layer.extent()
        canvas.setExtent(extent)

        return frame_layer

    def set_boundary(self, OD_point: list):
        """設定框框邊界"""
        canvas_dist = QgsDistanceArea().measureLine(OD_point[0], OD_point[1])
        x_min = min(OD_point[0].x(), OD_point[1].x()) - min(0.01, canvas_dist)
        x_max = max(OD_point[0].x(), OD_point[1].x()) + min(0.01, canvas_dist)
        y_min = min(OD_point[0].y(), OD_point[1].y()) - min(0.01, canvas_dist)
        y_max = max(OD_point[0].y(), OD_point[1].y()) + min(0.01, canvas_dist)
        return [
            QgsPointXY(x_min, y_min), QgsPointXY(x_min, y_max), 
            QgsPointXY(x_max, y_max), QgsPointXY(x_max, y_min)
        ]

    def clip_road(self, frame_lyr, good_result: bool):
        """切出路網，降低最短路徑運算量"""
        clp_rd_lyr = []
        if good_result:
            clipping_road_parameters = {
                'INPUT': self.GeometryFinder.layer('road'),
                'OVERLAY': frame_lyr,
                'OUTPUT': 'memory:'
            }
            try:
                output = processing.run("native:clip", clipping_road_parameters)
                clp_rd_lyr = output['OUTPUT']
            except:
                QMessageBox().information(None, '失敗', '切路網失敗\n按OK繼續下一條')
                good_result = False
                
        return clp_rd_lyr, good_result

    def shortest_path(self, OD_point, clp_rd_lyr, good_result: bool):
        """尋找最短路徑"""
        shortest_path_lyr = []
        if good_result:
            shortest_path_parameters = {
                'DEFAULT_DIRECTION' : 2, 
                'DEFAULT_SPEED' : 40, 
                'DIRECTION_FIELD' : 'DIR1', 
                'START_POINT' : '{},{} [EPSG:4326]'.format(OD_point[0].x(), OD_point[0].y()),
                'END_POINT' : '{},{} [EPSG:4326]'.format(OD_point[1].x(), OD_point[1].y()), 
                'INPUT' : clp_rd_lyr, 
                'OUTPUT' : 'memory:', 
                'SPEED_FIELD' : 'SPEED', 
                'STRATEGY' : 0, 
                'TOLERANCE' : 0, 
                'VALUE_BACKWARD' : '2', 
                'VALUE_BOTH' : '0', 
                'VALUE_FORWARD' : '1'
                }
            try:
                output = processing.run("native:shortestpathpointtopoint", shortest_path_parameters)
                shortest_path_lyr = output['OUTPUT']
            except:
                QMessageBox().information(None, '失敗', '沒找到路徑\n按OK繼續下一條')
                good_result = False
                
        return shortest_path_lyr, good_result

    def intersection(self, clp_rd_lyr, shortest_path_lyr, good_result: bool):
        """透過交集對照到現實的路網節線"""
        intrsct_lyr = []
        if good_result:
            intersection_parameters = {
                'INPUT': clp_rd_lyr,
                'OVERLAY': shortest_path_lyr, 
                'INPUT_FIELDS': [], 
                'OVERLAY_FIELDS': [], 
                'OVERLAY_FIELDS_PREFIX': '', 
                'OUTPUT': 'memory:'
            }
            try:
                output = processing.run("native:intersection", intersection_parameters)
                intrsct_lyr = output['OUTPUT']
            except:
                QMessageBox().information(None, '失敗', '找到路徑，但找不到對應的節線\n按OK繼續下一條')
                good_result = False
                
        return intrsct_lyr, good_result

    def find_passed_nodes(self, intersection_layer, OD_node: List[int], result_OK: bool):
        """尋找通過的路網點"""
        if result_OK:
            #獲取節線列表
            intersection_features = intersection_layer.getFeatures()
            link_dict = {}
            for i in intersection_features:
                if i.attributes()[3] not in link_dict:
                    link_dict[i.attributes()[3]] = []
                if i.attributes()[4] not in link_dict:
                    link_dict[i.attributes()[4]] = []
                if i.attributes()[27] != 2: #如果不是反向節線(DIR==2)，就把順向節線加入
                    link_dict[i.attributes()[3]].append(i.attributes()[4])
                if i.attributes()[27] != 1:
                    link_dict[i.attributes()[4]].append(i.attributes()[3])

            #串接節線
            passed_node = [OD_node[0]]
            while passed_node[-1] != OD_node[1] and result_OK:
                not_found = True
                candidate_node = link_dict[passed_node[-1]]
                for n in candidate_node:
                    if n not in passed_node:
                        not_found = False
                        passed_node.append(n)
                        break
                if not_found:
                    result_OK = False
        
            if not result_OK:
                QMessageBox().information(None, '錯誤', '在找點序時，程式迷路了')
                passed_node = [OD_node[0], 0, OD_node[1]] #用0表示錯誤
        
        else:
            passed_node = [OD_node[0], 0, OD_node[1]] #用0表示錯誤
        
        return passed_node, result_OK

class ProcessResult(object):
    """確認結果與修改錯誤"""
    def manually_input(self, stop_node: List[int], passed_node_list: List[int], init_path_dir, frthr_inspct_dir, checked_path_dir):
        """手動輸入最短路徑"""
        further_check = False
        check_path_dialog = QInputDialog()
        check_path_dialog.setGeometry(100, 100, 0, 0)
        confirm_dialog = QMessageBox()
        confirm_dialog.setGeometry(100, 100, 0, 0)
        while True:
            passed_node_str, result_OK = check_path_dialog.getText(
                check_path_dialog, 
                '手動輸入', 
                '{} -> {}\n'
                '輸入站間路徑\n'
                '請都以正數輸入，程式會自己轉換\n'
                '真的有區間找不出來就填0，之後再校正\n'
                '需要之後再校正就按取消'.format(stop_node[0], stop_node[1]), \
                text=','.join(map(str, passed_node_list))
                )
            if result_OK:
                passed_node_list = list(map(int, passed_node_str.split(',')))
                if 0 in passed_node_list:
                    second_check = confirm_dialog.information(
                        confirm_dialog, '再次確認', '要將路徑移至待檢查區嗎？', \
                        buttons=QMessageBox.Yes|QMessageBox.No)
                    if second_check == QMessageBox.Yes:
                        ProcessPath().save(passed_node_list, frthr_inspct_dir)
                        further_check = True
                        break
                else:
                    second_check = confirm_dialog.information(
                        confirm_dialog, '再次確認', '確定是正確結果並結束修正本路徑嗎？', \
                        buttons=QMessageBox.Yes|QMessageBox.No)
                    if second_check == QMessageBox.Yes:
                        ProcessPath().save(passed_node_list, checked_path_dir)
                        break
            else:
                second_check = confirm_dialog.information(
                    confirm_dialog, '再次確認', '要將路徑移至待檢查區嗎？', \
                    buttons=QMessageBox.Yes|QMessageBox.No)
                if second_check == QMessageBox.Yes:
                    ProcessPath().save(passed_node_list, frthr_inspct_dir)
                    further_check = True
                    break
            
        return passed_node_list, further_check

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
    P_drive = 'P:/09091-中臺區域模式/Working/'
    data_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')
    result_dir = os.path.join(P_drive, '04_交通資料/公車站牌/new/')

    route_UID2node_dir = os.path.join(data_dir, '00_route_UID2node')
    UID2node_path = os.path.join(data_dir, 'C_TWN_bus_stop_distance_matrix.csv')
    io_node_path = os.path.join(data_dir, '進出區域點號.csv')

    init_path_dir = os.path.join(result_dir, '01_initial_path_result')
    frthr_inspct_dir = os.path.join(result_dir, '02_further_inspect')
    checked_path_dir = os.path.join(result_dir, '03_checked_path')
    outbnd_path_dir = os.path.join(result_dir, '04_path_with_outbound_stops')
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

    #選取圖層: 因為有可能有同名圖層，會回傳list回來，所以要挑第一個
    vlayer['road'] = QgsProject.instance().mapLayersByName('C_TWN_ROAD_picked')[0]
    vlayer['node'] = QgsProject.instance().mapLayersByName('C_TWN_ROAD_picked_node')[0]
    

    while True:
        route_spec, OK = PrepareRoute().choose_route(data_dir, zone2dir)

        if OK:
            vlayer['route'] = PrepareRoute().init_route_layer(route_spec) #建立並顯示route_layer
            iface.mapCanvas().freeze(False) #讓圖面可以隨時更新
            GeometryFinder = SearchGeometry(vlayer)

            #####讀取站牌最近節點的屬性資料
            RouteStopMapping = ProcessUID2node(
                route_spec, GeometryFinder, UID2node_path, route_UID2node_dir, io_node_path
            )
            RouteStopMapping.modify()
            RouteStopMapping.save_modified_route(route_UID2node_dir)

            #####找站間最短路徑
            PathFinder = FindPath(GeometryFinder)
            #(#1, #2), (#2, #3)... 以這樣的順序一組一組把路徑串起來
            node_list = RouteStopMapping.get_node_list()
            stop_pair = list(zip(node_list, node_list[1:]))
            for s1, s2 in stop_pair:
                stop_nodes = [s1, s2]
                if GeometryFinder.is_in_layer('node', 'N', stop_nodes): #如果兩站都在區域內才找路徑
                    if stop_nodes[0] != stop_nodes[1]: #如果頭尾不同站才找路徑
                        #讀取已儲存的路徑
                        path_list, no_saved_path = ProcessPath().load(
                            stop_nodes, checked_path_dir
                        )
                        if no_saved_path:
                            while True:
                                # set midpoints
                                path_passed_nodes = PathFinder.set_path_midpoint(stop_nodes)
                                # set the start and the end of each subpath
                                find_path_todo = list(zip(path_passed_nodes, path_passed_nodes[1:]))
                                all_path_list = []
                                for OD_node in find_path_todo:
                                    subpath_list, result_OK = PathFinder.find_path(OD_node)
                                    if result_OK:
                                        all_path_list.append(subpath_list)
                                    else:
                                        break
                                        
                                if result_OK:
                                    path_list = [path_passed_nodes[0]]
                                    for sp in all_path_list:
                                        for node in sp[1:]:
                                            path_list.append(node)
                                    ProcessPath().save(path_list, init_path_dir)
                                    break
                                else:
                                    option = QMessageBox().information(
                                        None, '錯誤',
                                        '這樣的起終點與中間點組合找不到站間路徑\n'
                                        '要重新輸入中間點嗎？', 
                                        buttons=QMessageBox.Yes|QMessageBox.No
                                    )
                                    if option == QMessageBox.No:
                                        ProcessPath().save(path_list, frthr_inspct_dir)
                                        break
                                    else:
                                        continue
                    else:
                        path_list = [stop_nodes[0]]
                        ProcessPath().save(path_list, checked_path_dir) #把找到的路徑存起來
            
            ######校正結果
            further_check = False
            for stop_nodes in stop_pair:
                #計算起終點對應的ID
                if GeometryFinder.is_in_layer('node', 'N', stop_nodes):
                    if stop_nodes[0] != stop_nodes[1]:
                        #讀取已確認的路徑
                        path_list, no_checked_path = ProcessPath().load(stop_nodes, checked_path_dir)
                        if no_checked_path:
                            #讀取已輸出的路徑
                            path_list, no_saved_path = ProcessPath().load(stop_nodes, init_path_dir)
                            if no_saved_path:
                                path_layer = GeometryFinder.display_points(nodes_list=stop_nodes)
                                manual_input = QMessageBox().information(
                                    None, '載入失敗', '未有該區間已輸出路徑\n要手動輸入嗎？',
                                    buttons=QMessageBox.Yes|QMessageBox.No
                                )
                                if manual_input == QMessageBox.No:
                                    ProcessPath().save(path_list, frthr_inspct_dir)
                                    continue
                            else:
                                path_layer = GeometryFinder.display_points(nodes_list=path_list)
                            path_list, further_check = ProcessResult().manually_input(
                                stop_nodes, path_list, init_path_dir, frthr_inspct_dir, checked_path_dir)
                            QgsProject.instance().removeMapLayer(path_layer)

                else:
                    QMessageBox().information(None, '站點對應有問題', '其中一站不在計畫區域')

            if not further_check:
                QMessageBox().information(None, 'OK OK', '完成確認，都沒問題')
                QgsProject.instance().removeMapLayer(vlayer['route'])
            else:
                QMessageBox().information(None, 'Oh Oh', '完成確認，有要進一步確認的地方')

        else:
            second_check = QMessageBox().information(
                None, '再次確認', '真的要結束嗎？ ｡ﾟヽ(ﾟ´Д`)ﾉﾟ｡', 
                buttons=QMessageBox.Yes|QMessageBox.No
            )
            if second_check == QMessageBox.Yes:
                break

# if __name__ == '__main__':
#     main()
main()