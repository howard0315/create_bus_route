# -*- coding: utf-8 -*-

from csv import reader as csv_reader

from PyQt5.QtCore import QTimer

from qgis.analysis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.utils import *


count = id_iter = ID = OD = midpt_vlayer = road_list = None

def get_road_list(road_csv_path: str):
    road_list = {}
    with open(road_csv_path, newline='') as road_csv:
        road_row = csv_reader(road_csv)
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
                road_list[int(r[ID])] = [(int(r[A]), int(r[B])), int(r[DIR1])]
    print('完成道路讀取...')
    return road_list

def get_point():
    """取得特定屬性的幾何資訊"""
    global ID, midpt_vlayer
    feature_list = []
    midpt_vlayer.removeSelection()
    midpt_vlayer.selectByExpression('\"ID\" = {}'.format(ID))
    #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
    #get the geometry of the feature
    selected_point = midpt_vlayer.selectedFeatures()
    if len(selected_point) > 0:
        feature_list = QgsGeometry.asPoint(selected_point[0].geometry())
    return feature_list

def next_point():
    global count, ID, OD, road_list
    count += 1
    ID = next(id_iter)
    OD = road_list[ID][0]
    display_midpoint()

def display_midpoint():
    """在地圖上顯示要修改的那個點"""
    point = get_point()
    if point != []:
        iface.mapCanvas().setCenter(point)
        iface.mapCanvas().zoomScale(500)
        iface.mapCanvas().refresh()
        QTimer.singleShot(1500, exportMap)

# https://gis.stackexchange.com/questions/189735/iterating-over-layers-and-export-them-as-png-images-with-pyqgis-in-a-standalone/189825#189825
def exportMap(): 
    """Save the map as a PNG"""
    global OD
    iface.mapCanvas().saveAsImage('D:/Users/63707/Documents/python3/C_TWN_road_attribute/test/{}_{}.png'.format(OD[0], OD[1]))
    QTimer.singleShot(500, next_point)

def main():
    global count, id_iter, midpt_vlayer, road_list
    midpt_vlayer = QgsProject.instance().mapLayersByName('C_TWN_ROAD_picked_midpoint')[0]
    iface.mapCanvas().freeze(False)
    road_list = get_road_list('P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_ROAD_picked.csv')

    count = 0
    id_iter = iter(list(road_list.keys()))
    next_point()

# if __name__ == '__main__':
#     main()
main()