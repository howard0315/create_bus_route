# -*- coding: utf-8 -*-

import csv
import ctypes
import os
import urllib.parse
from itertools import tee
from math import cos, radians, sin, sqrt, tan
from pathlib import Path
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

user32 = ctypes.windll.user32

screen_width = user32.GetSystemMetrics(0)
screen_height = user32.GetSystemMetrics(1)

PC_name = os.environ['COMPUTERNAME']

def initialize_lane(lane_csv, lane_editing):
    while os.path.isfile(lane_editing):
        QMessageBox().information(None, '請稍候', '有人在編輯車道數檔案', buttons=QMessageBox.Ok)
    
    Path(lane_csv).rename(lane_editing)

    lane_data = pd.read_csv(lane_editing)
    lane_data.set_index('ID', inplace=True)
    if 'editing' not in lane_data:
        lane_data['editing'] = 'initial'
    lane_data.to_csv(lane_editing)

    Path(lane_editing).rename(lane_csv)

def preoccupy_rows(lane_csv, lane_editing):
    global PC_name
    while os.path.isfile(lane_editing):
        QMessageBox().information(None, '請稍候', '有人在編輯車道數檔案', buttons=QMessageBox.Ok)
    
    while True:
        row_number, OK = QInputDialog().getInt(None, '輸入','本批次要處理幾條道路節線的資料？', value=1000)
        if OK:
            break
        else:
            answer = QMessageBox().information(
                None, '詢問', '是否跳出？', buttons=QMessageBox.Yes|QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                return None, None

    Path(lane_csv).rename(lane_editing)

    lane_data = pd.read_csv(lane_editing)
    lane_data.set_index('ID', inplace=True)
    idx = lane_data.loc[lane_data['editing'] == 'initial', 'editing'].head(row_number).index
    lane_data.loc[idx, 'editing'] = PC_name
    lane_data.to_csv(lane_editing)

    Path(lane_editing).rename(lane_csv)

    return lane_data, idx

def apply_result(new_lane_data, idx, lane_csv, lane_editing):
    global PC_name
    while os.path.isfile(lane_editing):
        QMessageBox().information(None, '請稍候', '有人在編輯車道數檔案', buttons=QMessageBox.Ok)

    Path(lane_csv).rename(lane_editing)

    lane_data = pd.read_csv(lane_editing)
    lane_data.set_index('ID', inplace=True)
    for current_id in idx:
        if ((lane_data.loc[current_id, 'editing'] == PC_name) and 
            (new_lane_data.loc[current_id, 'editing'] == PC_name + '_edited')):
            lane_data.loc[current_id, 'editing'] = 'edited'
            lane_data.loc[current_id, 'LANE'] = new_lane_data.loc[current_id, 'LANE']
            lane_data.loc[current_id, 'LANE_REV'] = new_lane_data.loc[current_id, 'LANE_REV']
        elif lane_data.loc[current_id, 'editing'] == PC_name:
            lane_data.loc[current_id, 'editing'] = 'initial'
    lane_data.to_csv(lane_editing)

    Path(lane_editing).rename(lane_csv)

def get_road_list(road_csv_path: str):
    road_list = {}
    with open(road_csv_path, newline='') as road_csv:
        road_row = csv.reader(road_csv)
        first = True
        for r in road_row:
            if first:
                ID = r.index('ID')
                LENGTH = r.index('LENGTH')
                A = r.index('A')
                B = r.index('B')
                DIR1 = r.index('DIR1')
                WIDTH = r.index('WIDTH')
                first = False
            else:
                road_list[int(r[ID])] = [(int(r[A]), int(r[B])), int(r[DIR1]), int(r[WIDTH])]
    print('完成道路讀取...')
    return road_list

def get_point(ID, midpt_vlayer):
    """取得特定屬性的幾何資訊"""
    feature_list = None
    midpt_vlayer.removeSelection()
    midpt_vlayer.selectByExpression('\"ID\" = {}'.format(ID))
    #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
    #get the geometry of the feature
    selected_point = midpt_vlayer.selectedFeatures()
    if len(selected_point) > 0:
        feature_list = QgsGeometry.asPoint(selected_point[0].geometry())
    return feature_list

def display_midpoint(point):
    """在地圖上顯示要修改的那個點"""
    if point is not None:
        iface.mapCanvas().setCenter(point)
        iface.mapCanvas().zoomScale(500)
        iface.mapCanvas().refresh()

def input_lane(default_lane, direction, current_n, num_road, previous_result):
    global screen_height, screen_width
    dialog = QInputDialog()
    dialog.setGeometry(screen_width - 300, screen_height - 300, 0, 0)

    while True:
        if direction == 0:
            title = '({}/{}) 順向車道數'.format(current_n, num_road)
            text = '前次輸入結果：{}\n輸入「深紅」到「橘」方向的車道數\n(-1代表後續再確認)'.format(previous_result)
        else:
            title = '({}/{}) 車道數'.format(current_n, num_road)
            text = '前次輸入結果：{}\n輸入沿箭頭方向的車道數\n(-1代表後續再確認)'.format(previous_result)
        
        lane_number, OK = dialog.getInt(
            dialog, title, text, value=default_lane,
            min=-1, max=10, step=1
        )

        if OK:
            if direction == 0:
                while True:
                    lane_number_rev, OK = dialog.getInt(
                        dialog, '({}/{})反向車道數'.format(current_n, num_road),
                        '輸入「橘」到「深紅」方向的車道數\n(-1代表後續再確認)',
                        value=lane_number, min=-1, max=10, step=1
                    )
                    if OK:
                        result = '順向 {} 車道/反向 {} 車道'.format(lane_number, lane_number_rev)
                        break
            else:
                lane_number_rev = 0
                result = '順向 {} 車道'.format(lane_number)
            
            break

        else:
            confirm = QMessageBox().information(
                None, '確認', '回上一條？', buttons=QMessageBox.Yes|QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                return None, 1, previous_result
            else:
                confirm = QMessageBox().information(
                    None, '確認', '結束輸入？', buttons=QMessageBox.Yes|QMessageBox.No
                )
                if confirm == QMessageBox.Yes:
                    return None, 2, ''

    return [lane_number, lane_number_rev], 0, result

def main():
    global PC_name
    midpoint_layer = QgsProject.instance().mapLayersByName('C_TWN_ROAD_midpt_OTHER')[0]
    iface.mapCanvas().freeze(False) #讓圖面可以隨時更新

    map_dir = 'P:/09091-中臺區域模式/Working/98_GIS/road'

    road_csv = os.path.join(map_dir, 'CSV', 'C_TWN_ROAD_OTHER.csv')
    lane_csv = os.path.join(map_dir, 'CSV', 'C_TWN_ROAD_OTHER_lane.csv')

    lane_editing = os.path.join(map_dir, 'CSV', 'C_TWN_ROAD_OTHER_lane_editing.csv')

    road_list = get_road_list(road_csv)

    initialize_lane(lane_csv, lane_editing)

    while True:
        lane_data, idx_todo = preoccupy_rows(lane_csv, lane_editing)

        if lane_data is not None:
            idx_todo_wide = []
            for current_id in idx_todo:
                if lane_data.loc[current_id, 'LANE'] == 0:
                    idx_todo_wide.append(current_id)
                else:
                    lane_data.loc[current_id, 'editing'] = PC_name + '_edited'

            current_n = 0
            num_road = len(idx_todo_wide)
            result_text = ''
            while num_road > 0:
                current_id = idx_todo_wide[current_n]
                current_point = get_point(current_id, midpoint_layer)
                display_midpoint(current_point)
                result, state, result_text = input_lane(
                    lane_data.loc[current_id, 'LANE'], road_list[current_id][1],
                    current_n, num_road, result_text
                )
                if state == 0:
                    lane_data.loc[current_id, 'LANE'] = result[0]
                    lane_data.loc[current_id, 'LANE_REV'] = result[1]
                    lane_data.loc[current_id, 'editing'] = PC_name + '_edited'
                    if current_n == num_road - 1:
                        break
                    else:
                        current_n += 1
                elif state == 1:
                    current_n = max(current_n - 1, 0)
                    continue
                else:
                    break
            
            QMessageBox().information(None, '嗯哼', '已完成本批次編輯')

            apply_result(lane_data, idx_todo, lane_csv, lane_editing)
        
        else:
            confirm = QMessageBox().information(
                None, '確認', '確定要結束編輯嗎？',
                buttons=QMessageBox.Yes|QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                break
            else:
                continue

main()
