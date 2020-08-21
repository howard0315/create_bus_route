# -*- coding: utf-8 -*-

import os
from math import atan2, radians, pi
import pandas as pd

from qgis.analysis import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.utils import *

def get_point(layer, attribute_name: str, value_list: list):
    """取得特定屬性的幾何資訊"""
    feature_list = [[] for _ in value_list]
    for i, feature in enumerate(value_list):
        layer.removeSelection()
        layer.selectByExpression('\"{}\" = {}'.format(attribute_name, feature))
        #https://gis.stackexchange.com/questions/332026/getting-position-of-point-in-pyqgis
        #get the geometry of the feature
        selected_point = layer.selectedFeatures()
        if len(selected_point) > 0:
            feature_list[i] = QgsGeometry.asPoint(selected_point[0].geometry())
    return feature_list

def direction(backward_pt, forward_pt):
    x1, y1 = LatLonToTWD().convert(radian(backward_pt.y()), radian(backward_pt.x()))
    x2, y2 = LatLonToTWD().convert(radian(forward_pt.y()), radian(forward_pt.x()))

    return (atan2(x2 - x1, y2 - y1) * 180 / pi) % 360

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
    vlayer = {}
    vlayer['mid'] = QgsProject.instance().mapLayersByName('road_midpoint')[0]
    vlayer['mid_b'] = QgsProject.instance().mapLayersByName('road_midpoint_backward')[0]
    vlayer['mid_f'] = QgsProject.instance().mapLayersByName('road_midpoint_forward')[0]

    road_list = pd.read_csv('road_list.csv')

    road_list['lat'] = 0
    road_list['lon'] = 0
    road_list['heading'] = 0

    for i in range(len(road_list)):
        road_list.loc[i, 'lat'] = get_point(vlayer['mid'], 'ID', [road_list.loc[i, 'ID']])[0].y()
        road_list.loc[i, 'lon'] = get_point(vlayer['mid'], 'ID', [road_list.loc[i, 'ID']])[0].x()
        road_list.loc[i, 'heading'] = direction(
            get_point(vlayer['mid_b'], 'ID', [road_list.loc[i, 'ID']])[0], 
            get_point(vlayer['mid_f'], 'ID', [road_list.loc[i, 'ID']])[0]
        )

    road_list.to_csv('road_list.csv')


main()