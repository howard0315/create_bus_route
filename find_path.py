# -*- coding: utf-8 -*-

import os
import urllib.parse
import math
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
        path_path = os.path.join(save_dir, '{}_{}.txt'.format(path_list[0], path_list[-1])) #路徑的路徑
        path_file = open(path_path, 'w')
        path_file.write(path_str)
        path_file.close()

    def save_outlier(self, ori_UID: str, des_UID: str, save_dir: str):
        """儲存有界外點的區間"""
        path_str = 'to be filled...'
        path_path = os.path.join(save_dir, '{}_{}.txt'.format(ori_UID, des_UID)) #路徑的路徑
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

    def move(self,  ori_node: int, des_node: int, ori_dir: str, des_dir: str):
        sucess = False
        ori_file = os.path.join(ori_dir, '{}_{}.txt'.format(ori_node, des_node))
        if os.path.isfile(ori_file):
            copy2(ori_file, des_dir)
            sucess = True
        return sucess

class PrepareRoute(object):
    """匯入公車路線相關"""
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

    def __init__(self, route_spec: List[str], StopUID2node_path: str, route_UID2node_dir: str):
        self.dialog = QInputDialog()
        self.dialog.setGeometry(100, 100, 0, 0)
        self.route_spec = route_spec
        self.read_StopUID2node(StopUID2node_path)
        self.read_route(route_UID2node_dir)

    def read_StopUID2node(self, file_path: str):
        """讀取UID到點號的對應"""
        self.StopUID2node = pd.read_csv(file_path)
        self.StopUID2node.set_index('InputID', inplace=True)

    def read_route(self, file_dir: str):
        """讀取UID到點號的對應"""
        route_chart_path = os.path.join(file_dir, '{}.csv'.format('_'.join(self.route_spec[0:3])))
        self.saved_exist = os.path.isfile(route_chart_path)
        if self.saved_exist:
            self.route_UID2node = pd.read_csv(route_chart_path)
            self.route_UID2node.set_index('InputID', inplace=True)
        else:
            self.route_UID2node = []
        
    def ask_use_saved(self):
        """詢問是否使用既有成果"""
        if self.saved_exist:
            answer = QMessageBox().information(None, '確認', 
                '找到已經校正過的點號對應\n'
                '要沿用既有的點號對應校正成果嗎？', 
                buttons=QMessageBox.Yes|QMessageBox.No)
            if answer == QMessageBox.Yes:
                return True
        else:
            return False

    def modify(self, route_layer):
        """修正UID與點號的對應"""
        self.use_saved = self.ask_use_saved()
        if not self.saved_exist or not self.use_saved:
            #讀取站序與UID對應
            self.read_seq_to_UID()
            self.fill_route_df()

            #人工確認點號正確性
            if_fix = QMessageBox().information(None, '開始修正站牌', '是否修改站牌對應？', \
                buttons=QMessageBox.Ok|QMessageBox.Cancel)
            if if_fix == QMessageBox.Ok:

                #進入逐站修正前的確認
                # self.check_outbound_stop()

                in_zone_seq = []
                
                stop_number = self.seq_to_UID.index.tolist()[0]
                while True:
                    stop_number, if_continue = self.choose_stop(stop_number)
                    #先確認該站存在
                    if if_continue:
                        picked_UID = self.seq_to_UID.StopUID[stop_number] #要修改的UID

                        #先確認該站存在
                        # if picked_UID not in self.StopUID2node.index:
                        #     QMessageBox().information(None, '提示', '本點不在區域內')
                        #     self.route_UID2node[picked_UID] = 0
                        # else:
                        current_scale = 3000
                        self.display_stop(route_layer, stop_number, current_scale)
                        self.get_newID(stop_number, picked_UID)
                        route_layer.removeSelection()
                        
                        #next stop_number: next stop or the last stop
                        stop_number = self.seq_to_UID.index.tolist()[
                            min(self.seq_to_UID.shape[0] - 1, self.seq_to_UID.index.get_loc(stop_number) + 1)
                        ]
                    else:
                        second_check = QMessageBox().information(None, '再次確認', '要結束修正點號嗎？', \
                            buttons=QMessageBox.Ok|QMessageBox.Cancel)
                        if second_check == QMessageBox.Ok:
                            break

    def read_seq_to_UID(self):
        """讀取站序與UID的對應"""
        self.seq_to_UID = pd.read_csv(
            os.path.join(
                self.route_spec[3], 
                '{}.csv'.format('_'.join(self.route_spec[0:3]))
            )
        )
        self.seq_to_UID.set_index('StopSequence', inplace=True)
    
    def save_modified_route(self, file_dir: str):
        """回存該路線修正後的UID與點號對應"""
        if not self.saved_exist or not self.use_saved:
            self.route_UID2node.to_csv(
                os.path.join(
                    file_dir, 
                    '{}.csv'.format('_'.join(self.route_spec[0:3]))
                )
            )

    def choose_stop(self, default_choice):
        """選擇站牌"""
        stop_list = [
            '{} ({}): {}'.format(
                seq, row['StopUID'], 
                self.route_UID2node.loc[[row['StopUID']], 'TargetID'].tolist()[0])
            for seq, row in self.seq_to_UID.iterrows()
        ]
        
        stop_str, choose_OK = self.dialog.getItem(
            self.dialog, '選擇站牌', 
            '選擇要編輯的站牌\n要跳出則按取消', stop_list, 
            current=self.seq_to_UID.index.get_loc(default_choice), 
            editable=False
        )
        chosen_stop = int(stop_str.split(' ')[0])
        return chosen_stop, choose_OK

    def check_outbound_stop(self):
        strange_route = False
        route_StopUID = self.seq_to_UID['StopUID'].tolist()
        io_bound = [s in self.StopUID2node.index for s in route_StopUID]

        in_UID = in_iloc = out_UID = out_iloc = 0
        
        #進來區內
        num_in = 0
        for i in range(len(io_bound) - 2, -1, -1):
            if not io_bound[i] and io_bound[i] != io_bound[i+1]:
                num_in += 1
                in_UID = route_StopUID[i]
                in_iloc = i
        if num_in > 1:
            strange_route = True

        #跑到區外
        num_out = 0
        for i in range(1, len(io_bound)):
            if not io_bound[i] and io_bound[i] != io_bound[i-1]:
                num_out += 1
                out_UID = route_StopUID[i]
                out_iloc = i
        if num_out > 1:
            strange_route = True
        
        #只能處理中間在區內，所以要排除中間在區外
        if out_iloc < in_iloc:
            strange_route = True

        return in_UID, in_iloc, out_UID, out_iloc, strange_route

    def display_stop(self, route_layer, stop_number: int, current_scale: int):
        """在地圖上顯示要修改的那個點"""
        route_layer.removeSelection()
        route_layer.selectByExpression('\"StopSequence\" = {}'.format(stop_number))
        point = QgsGeometry.asPoint(route_layer.selectedFeatures()[0].geometry())
        iface.mapCanvas().setCenter(point)
        
        iface.mapCanvas().zoomScale(current_scale)
        iface.mapCanvas().refresh()

    def fill_route_df(self):
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
            self.route_UID2node.set_index('InputID', inplace=True)

    def get_newID(self, stop_number, picked_UID):
        """設定ID對應"""
        while True:
            newID, newID_OK = self.dialog.getInt(
                self.dialog, '新的ID', 
                '{} ({}): {} ({}/{})\n'
                '請輸入新的ID\n'
                '按取消來更改比例尺'.format(
                    stop_number, picked_UID, 
                    self.route_UID2node.TargetID[picked_UID],
                    self.seq_to_UID.index.get_loc(stop_number) + 1, 
                    self.seq_to_UID.shape[0]
                ), 
                value=self.route_UID2node.TargetID[picked_UID]
            )
            if newID_OK:
                break
            else:
                self.set_scale(current_scale)
        self.route_UID2node.TargetID[picked_UID] = newID
    
    def set_scale(self, current_scale):
        """設定比例尺"""
        while True:
            iface.mapCanvas().zoomScale(current_scale)
            iface.mapCanvas().refresh()
            set_scale_dialog = QInputDialog()
            new_scale, scale_change_OK = QInputDialog().getInt(set_scale_dialog, '更改比例尺', \
                '輸入新的比例尺', value=current_scale)
            if scale_change_OK:
                if new_scale > 0:
                    if new_scale != current_scale:
                        current_scale = new_scale
                    else:
                        if_quit = QMessageBox().information(None, '是否跳出', '輸入相同比例尺，要結束更改比例尺嗎？', \
                            buttons=QMessageBox.Ok|QMessageBox.Cancel)
                        if if_quit == QMessageBox.Ok:
                            break
                else:
                    QMessageBox().information(None, '錯誤', '請輸入正整數')
            else:
                if_quit = QMessageBox().information(None, '再次確認', '要結束更改比例尺嗎？', \
                    buttons=QMessageBox.Ok|QMessageBox.Cancel)
                if if_quit == QMessageBox.Ok:
                    break

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

    def create_shp_filename(self, data_dir, OD_info):
        """產生檔名，暫時沒人用"""
        clipped_road_path = os.path.join(data_dir, 'temp', \
            'clipped_road_{}_{}.shp'.format(str(OD_info[3][0]), str(OD_info[3][1])))
        shortest_path_path = os.path.join(data_dir, 'temp', \
            'shortest_path_{}_{}.shp'.format(str(OD_info[3][0]), str(OD_info[3][1])))
        intersection_path = os.path.join(data_dir, 'temp', \
            'intersection_{}_{}.shp'.format(str(OD_info[3][0]), str(OD_info[3][1])))
        return clipped_road_path, shortest_path_path, intersection_path

class FindPath(object):
    """生成最短路徑的相關函式"""

    def __init__(self, layer_dict: dict, UID_table: dict):
        self.node_layer = layer_dict['node']
        self.road_layer = layer_dict['road']
        self.route_layer = layer_dict['route']
        self.UID_table = UID_table

    def pairwise(self, iterable):
        """參考https://stackoverflow.com/questions/5764782/iterate-through-pairs-of-items-in-a-python-list?lq=1\n
        s -> (s0, s1), (s1, s2), (s2, s3), ..."""
        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)
    
    def get_node(self, OD_node):
        """取得路徑起終點的座標"""
        self.node_layer.removeSelection()

        start_node = OD_node[0]
        end_node = OD_node[1]

        stop_mapped = False
        dist = 1e10
        startPoint = endPoint = []

        #起點
        if start_node != 0:
            stop_mapped = True
            self.node_layer.selectByExpression('\"N\" = {}'.format(start_node))
            #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
            #get the geometry of the feature
            startPoint = QgsGeometry.asPoint(self.node_layer.selectedFeatures()[0].geometry())
            self.node_layer.removeSelection()
            
        #終點
        if end_node != 0:
            stop_mapped = True
            self.node_layer.selectByExpression('\"N\" = {}'.format(end_node))
            #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
            #get the geometry of the feature
            endPoint = QgsGeometry.asPoint(self.node_layer.selectedFeatures()[0].geometry())
            self.node_layer.removeSelection()
        
        #距離
        if stop_mapped:
            dist = self.distance(startPoint, endPoint)

        return [startPoint, endPoint, dist, [start_node, end_node]], stop_mapped

    def find_path(self, OD_point, OD_node, init_path_dir):
        """給定起終點(OD_info, self.get_node的結果)，回傳路徑"""
        passed_node_list = []
        result_OK = False
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

    def distance(self, point1, point2):
        """算距離"""
        if point1.x() < 1000:
            x1, y1 = LatLonToTWD97().convert(point1.y(), point1.x())
            x2, y2 = LatLonToTWD97().convert(point2.y(), point2.x())
        else:
            x1 = point1.x()
            y1 = point1.y()
            x2 = point2.x()
            y2 = point2.y()

        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        return distance

    def draw_frame(self, OD_info):
        """框出路網的框框\n
        https://gis.stackexchange.com/questions/86812/how-to-draw-polygons-from-the-python-console
        """
        frame_layer = QgsVectorLayer('Polygon', 'frame' , "memory")
        pr = frame_layer.dataProvider() 
        poly = QgsFeature()
        points = self.set_boundary(OD_info) #設定框框
        poly.setGeometry(QgsGeometry.fromPolygonXY([points]))
        pr.addFeatures([poly])
        frame_layer.updateExtents()
        QgsProject.instance().addMapLayers([frame_layer])
        
        #zoom to frame
        # frame_layer = iface.activeLayer()
        canvas = iface.mapCanvas()
        extent = frame_layer.extent()
        canvas.setExtent(extent)

        self.route_layer = iface.activeLayer()

        return frame_layer

    def set_boundary(self, OD_info):
        """設定框框邊界"""
        canvas_dist = QgsDistanceArea().measureLine(OD_info[0], OD_info[1])
        x_min = min(OD_info[0].x(), OD_info[1].x()) - min(0.05, canvas_dist)
        x_max = max(OD_info[0].x(), OD_info[1].x()) + min(0.05, canvas_dist)
        y_min = min(OD_info[0].y(), OD_info[1].y()) - min(0.05, canvas_dist)
        y_max = max(OD_info[0].y(), OD_info[1].y()) + min(0.05, canvas_dist)
        return [
            QgsPointXY(x_min, y_min), QgsPointXY(x_min, y_max), 
            QgsPointXY(x_max, y_max), QgsPointXY(x_max, y_min)
        ]

    def clip_road(self, frame_lyr, good_result: bool):
        """切出路網，降低最短路徑運算量"""
        clp_rd_lyr = []
        if good_result:
            clipping_road_parameters = {
                'INPUT': self.road_layer,
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

    def shortest_path(self, OD_info, clp_rd_lyr, good_result: bool):
        """尋找最短路徑"""
        shortest_path_lyr = []
        if good_result:
            shortest_path_parameters = {
                'DEFAULT_DIRECTION' : 2, 
                'DEFAULT_SPEED' : 40, 
                'DIRECTION_FIELD' : 'DIR1', 
                'START_POINT' : '{},{} [EPSG:4326]'.format(OD_info[0].x(), OD_info[0].y()),
                'END_POINT' : '{},{} [EPSG:4326]'.format(OD_info[1].x(), OD_info[1].y()), 
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

    def find_passed_nodes(self, intersection_layer, OD_nodeID, good_result: bool):
        """尋找通過的路網點"""
        passed_node = [OD_nodeID[0]] #用來裝通過節點的list
        result_OK = good_result

        if result_OK:
            #獲取節線列表
            intersection_features = intersection_layer.getFeatures()
            AB_node = []
            for i in intersection_features:
                if i.attributes()[27] == 0: #如果是雙向節線(DIR==0)，就把反向節線加入
                    AB_node.append((i.attributes()[3], i.attributes()[4]))
                    AB_node.append((i.attributes()[4], i.attributes()[3]))
                elif i.attributes()[27] == 1:
                    AB_node.append((i.attributes()[3], i.attributes()[4]))
                else:
                    AB_node.append((i.attributes()[4], i.attributes()[3]))
            
            #搜尋節線
            while passed_node[-1] != OD_nodeID[1]:
                if len(AB_node) == 0:
                    #節線列表被刪光而還沒找到路徑就提示錯誤
                    QMessageBox().information(None, '錯誤', '節線列表被刪光但還沒找到路徑') 
                    result_OK = False
                    break

                candidate_link = [link for link in AB_node if link[0] == passed_node[-1]] #候選節線
                if len(candidate_link) > 0:
                    passed_node.append(int(candidate_link[0][1])) #加入第一條候選節線的終點
                    AB_node.remove(candidate_link[0]) #刪掉被用掉的候選節線
                    if candidate_link[0][::-1] in AB_node: #刪掉候選節線的反向節線
                        AB_node.remove(candidate_link[0][::-1])
                else:
                    QMessageBox().information(None, '錯誤', '節線列表未刪光但找不到下一個點') 
                    result_OK = False
                    break
        
        if not result_OK:
            passed_node = [OD_nodeID[0], 0, OD_nodeID[1]] #用0表示錯誤
        
        return passed_node, result_OK

class ProcessResult(object):
    """確認結果與修改錯誤"""
    def display_path(self, node_layer, passed_node_list: List[int]):
        """把最短路徑通過的節點選取出來\n
        https://gis.stackexchange.com/questions/86812/how-to-draw-polygons-from-the-python-console
        """
        # create a memory layer with two points
        path_layer = QgsVectorLayer('Point', 'path', "memory")
        pr = path_layer.dataProvider()
        pr.addAttributes([QgsField('n_ID', QVariant.String)])
        for i, node in enumerate(passed_node_list):
            if node != 0:
                node_layer.removeSelection()
                #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
                #get the geometry of the feature
                node_layer.selectByExpression( '\"N\" = {}'.format(node))
                point = QgsGeometry.asPoint(node_layer.selectedFeatures()[0].geometry())
                # add the first point
                pt = QgsFeature()
                pt.setGeometry(QgsGeometry.fromPointXY(point))
                pt.setAttributes(['{}_{}'.format(i, node)])
                pr.addFeatures([pt])
                # update extent of the layer
                path_layer.updateExtents()
        path_layer.renderer().symbol().setColor(QColor('yellow'))
        # add the layer to the canvas
        QgsProject.instance().addMapLayers([path_layer])

        #zoom to frame
        extent = path_layer.extent()
        iface.mapCanvas().setExtent(extent)

        #zoom out a little bit
        iface.mapCanvas().setWheelFactor(1.5)
        iface.mapCanvas().zoomOut()

        return path_layer

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
                ('{} -> {}\n'
                 '輸入站間路徑\n'
                 '請都以正數輸入，程式會自己轉換\n'
                 '真的有區間找不出來就填0，之後再校正\n'
                 '需要之後再校正就按取消').format(stop_node[0], stop_node[1]), \
                text=','.join(map(str, passed_node_list))
                )
            if result_OK:
                passed_node_list = list(map(int, passed_node_str.split(',')))
                if 0 in passed_node_list:
                    second_check = confirm_dialog.information(
                        confirm_dialog, '再次確認', '要將路徑移至待檢查區嗎？', \
                        buttons=QMessageBox.Ok|QMessageBox.Cancel)
                    if second_check == QMessageBox.Ok:
                        ProcessPath().save(passed_node_list, frthr_inspct_dir)
                        further_check = True
                        break
                else:
                    second_check = confirm_dialog.information(
                        confirm_dialog, '再次確認', '確定是正確結果並結束修正本路徑嗎？', \
                        buttons=QMessageBox.Ok|QMessageBox.Cancel)
                    if second_check == QMessageBox.Ok:
                        ProcessPath().save(passed_node_list, checked_path_dir)
                        break
            else:
                second_check = confirm_dialog.information(
                    confirm_dialog, '再次確認', '要將路徑移至待檢查區嗎？', \
                    buttons=QMessageBox.Ok|QMessageBox.Cancel)
                if second_check == QMessageBox.Ok:
                    ProcessPath().save(passed_node_list, frthr_inspct_dir)
                    further_check = True
                    break
            
        return passed_node_list, further_check
    
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
    
    def save(self, node_list: List[int], route_spec: List[str]):
        """把最終結果儲存成文字檔"""
        route_str = ','.join(map(str, node_list))
        route_path = os.path.join(save_dir, '{}.txt'.format('_'.join(route_spec))) #路徑的路徑
        route_file = open(path_path, 'w')
        route_file.write(route_str)
        route_file.close()

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

    init_path_dir = os.path.join(result_dir, '01_initial_path_result')
    frthr_inspct_dir = os.path.join(result_dir, '02_further_inspect')
    checked_path_dir = os.path.join(result_dir, '03_checked_path')
    outbnd_path_dir = os.path.join(result_dir, '04_path_with_outbound_stops')
    result_route_dir = os.path.join(result_dir, '05_final_result_route')

    route_UID2node_dir = os.path.join(data_dir, '00_route_UID2node')
    UID2node_path = os.path.join(data_dir, 'C_TWN_bus_stop_distance_matrix.csv')

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

            #####讀取站牌最近節點的屬性資料
            RouteStopMapping = ProcessUID2node(route_spec, UID2node_path, route_UID2node_dir)
            
            RouteStopMapping.modify(vlayer['route'])
            RouteStopMapping.save_modified_route(route_UID2node_dir)

            route_UID2node = RouteStopMapping.route_UID2node

            #####找站間最短路徑
            PathFinder = FindPath(vlayer, route_UID2node)
            #(#1, #2), (#2, #3)... 以這樣的順序一組一組把路徑串起來
            node_list = route_UID2node['TargetID'].tolist()
            stop_pair = list(zip(node_list, node_list[1:]))
            for stop_node in stop_pair:
                good_result = True

                #計算起終點對應的ID
                OD_info, in_zone = PathFinder.get_node(stop_node)

                passed_node_list = []
                if in_zone: #如果兩站都在區域內才找路徑
                    if stop_node[0] != stop_node[1]: #如果頭尾不同站才找路徑
                        #讀取已儲存的路徑
                        passed_node_list, no_saved_path = ProcessPath().load(stop_node[0], stop_node[1], checked_path_dir)
                        
                        if no_saved_path:
                            if OD_info[2] < 100000:
                                passed_node_list, result_OK = PathFinder.find_path(OD_info[0:2], stop_node)
                            
                                if result_OK:
                                    ProcessPath().save(passed_node_list, init_path_dir) #把找到的路徑存起來
                    else:
                        passed_node_list = [stop_node[0]]
            
            ######校正結果
            further_check = False
            node_list = route_UID2node['TargetID'].tolist()
            stop_pair = list(zip(node_list, node_list[1:]))
            for stop_node in stop_pair:
                #計算起終點對應的ID
                OD_info, in_zone = PathFinder.get_node(stop_node)

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
                                passed_node_list, further_check = ProcessResult().manually_input(
                                    stop_node, passed_node_list, init_path_dir, frthr_inspct_dir, checked_path_dir)
                                QgsProject.instance().removeMapLayer(path_layer)
                            else:
                                passed_node_list = [OD_info[3][0], 0, OD_info[3][1]]
                                manual_input = QMessageBox().information(
                                    None, '載入失敗', '未有該區間已輸出路徑\n要手動輸入嗎？', \
                                    buttons=QMessageBox.Yes|QMessageBox.No)
                                if manual_input == QMessageBox.Yes:
                                    path_layer = ProcessResult().display_path(vlayer['node'], passed_node_list)
                                    passed_node_list, further_check = ProcessResult().manually_input(
                                        stop_node, passed_node_list, init_path_dir, frthr_inspct_dir, checked_path_dir)
                                    QgsProject.instance().removeMapLayer(path_layer)
                        else:
                            path_layer = ProcessResult().display_path(vlayer['node'], passed_node_list)
                            QMessageBox().information(None, '恭喜', '這個區間已經確認過囉')
                            QgsProject.instance().removeMapLayer(path_layer)
                    else:
                        QMessageBox().information(None, \
                            '點號相同', '{} -> {}\n兩站同點'.format(str(OD_info[3][0]), str(OD_info[3][1])))
                else:
                    QMessageBox().information(
                        None, '站點對應有問題', '其中一站不在計畫區域'
                    )

            if not further_check:        
                QgsProject.instance().removeMapLayer(vlayer['route'])

        else:
            second_check = QMessageBox().information(None, '再次確認', '真的要結束嗎？ ｡ﾟヽ(ﾟ´Д`)ﾉﾟ｡', \
                    buttons=QMessageBox.Yes|QMessageBox.No)
            if second_check == QMessageBox.Yes:
                break

# if __name__ == '__main__':
#     main()
main()