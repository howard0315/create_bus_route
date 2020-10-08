# -*- coding: utf-8 -*-

import base64
import copy
import hmac
import json
import os
import pickle
import re
import shutil
from datetime import datetime, timedelta
from hashlib import sha1
from pprint import pprint
import time
from typing import List
from wsgiref.handlers import format_date_time

from bs4 import BeautifulSoup
from lxml import html
from selenium import webdriver
import pandas as pd
from requests import request
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys


def initialize_webdriver():
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("window-size=1600,800")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    #打開網頁
    chrome = webdriver.Chrome('./chromedriver', options=options)
    chrome.get("https://citybus.taichung.gov.tw/ebus/driving-map")

    return chrome

def query_timetable(route_name: str, chrome: webdriver.Chrome, weekday: str, weekend: str):
    #按下選擇路線的按鈕
    chrome.find_element_by_xpath("//body").click()
    choose_line_button = chrome.find_element_by_xpath(
        '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/div[2]/div/button'
    )
    choose_line_button.click()

    time.sleep(0.5)

    #輸入路線(只有數字，支線要到下一層去選)
    line_field = chrome.find_element_by_xpath(
        '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/div[2]/div/div/div[1]/div[1]/div/div/input'
    )
    line_field.send_keys(Keys.CONTROL, 'a')
    parent_route = re.findall('^[A黃]?\d+', route_name)
    if len(parent_route) == 0:
        print('這不是路線')
        return None, None
    line_field.send_keys(parent_route[0])
    
    time.sleep(0.5)

    #點選找到的路線
    try:
        current_html = chrome.page_source
        tree = html.fromstring(current_html)
        routes = tree.xpath('//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/div[2]/div/div/div[1]/div[2]/div')
        n_route = 0
        if len(routes) > 0:
            for i in range(1, len(routes) + 1):
                route_dscrp = tree.xpath(
                    '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/div[2]/div/div/div[1]/div[2]/div[{}]'
                    '/div[1]/div/span/text()'.format(i)
                )[0]
                if len(re.findall(r'^\[{}\]'.format(parent_route[0]), route_dscrp)) > 0:
                    n_route = i
                    break

            if n_route > 0:
                route_button = chrome.find_element_by_xpath(
                    '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/div[2]/div/div/div[1]/div[2]/div[{}]'.format(n_route)
                )
                route_button.click()
            else:
                print('不在網站找到的路線裡面')
                return None, None
        else:
            print('沒有路線')
            return None, None
    
    except:
        print('沒找到路線')
        return None, None
    
    time.sleep(0.5)
    
    #取得支線列表
    if route_name != parent_route[0]:
        current_html = chrome.page_source
        tree = html.fromstring(current_html)
        subroutes = tree.xpath('//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/ul/div')
        n_subroute = 0
        if len(subroutes) > 0:
            for i in range(1, len(subroutes) + 1):
                if route_name == tree.xpath(
                    '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/ul/div[{}]'
                    '/div/div[1]/div/span/text()'.format(i)
                )[0]:
                    n_subroute = i
                    break

            if n_subroute > 0:
                subroute_button = chrome.find_element_by_xpath(
                    '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[1]/ul/div[{}]'.format(n_subroute)
                )
                subroute_button.click()
            else:
                print('沒找到子路線')
                return None, None
        else:
            print('沒有子路線')
            return None, None

    #等到資料跑出來再繼續讀取
    time.sleep(1)
    while True:
        current_html = chrome.page_source
        tree = html.fromstring(current_html)
        if len(tree.xpath(
            '//*[@id="root"]/div[1]/div/div[1]/div/div[2]/div[4]'
        )) != 0:
            break
        else:
            time.sleep(1)

    time.sleep(1)

    #按下顯示時刻表的按鈕
    get_timetable = chrome.find_element_by_xpath(
        '//*[@id="root"]/div[1]/div/div[2]/div/div[1]/div[2]/div[2]/div/div/div[2]/button'
    )
    get_timetable.click()
    
    time.sleep(0.5)

    #讀取時刻表
    weekday_timetable = convert_timetable(weekday, chrome)
    weekend_timetable = convert_timetable(weekend, chrome)
    
    #再按一次
    get_timetable.click()

    return weekday_timetable, weekend_timetable

def convert_timetable(timetable_date: str, chrome: webdriver.Chrome):
    """讀取指定日期的時刻表"""
    #輸入日期
    chrome.find_element_by_xpath(
        '//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/form/div/div/input'
    ).send_keys('00{}'.format(timetable_date))
    time.sleep(1)

    #擷取現在的原始碼
    current_html = chrome.page_source
    tree = html.fromstring(current_html)
    timetable_type = tree.xpath(
        '//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/div/div[1]/div/div/p/text()'
    )[0]

    #去程
    timetable1 = read_time(tree, timetable_type, 1)
    #返程
    if len(tree.xpath('//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/div/div[2]')) == 0:
        print('沒有返程')
        timetable2 = []
    else:
        timetable2 = read_time(tree, timetable_type, 2)

    return timetable1, timetable2

def read_time(tree, timetable_type: str, direction: int):
    """讀取畫面中的時刻表數字"""
    timetable = []
    if timetable_type == '時刻發車':
        if len(tree.xpath(
            '//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/div/div[{}]'
            '/div/div/div/p'.format(direction)
        )) == 0:
            bus_time_list = tree.xpath(
                '//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/div/div[{}]'
                '/div/div/div'.format(direction)
            )
            for i in range(1, len(bus_time_list) + 1):
                timetable.append(
                    tree.xpath(
                        '//*[@id="root"]/div[1]/div/div[2]/div/div[2]/div/div/div[{}]'
                        '/div/div/div[{}]/span/text()'.format(direction, i)
                    )[0]
                )
    return timetable

def output_file(
    timetable_pack: list, output_folder: str, 
    routeUID: str, route_name: str, direction: int
):
    if timetable_pack != None and timetable_pack[0] != None:
        timetable_filename = os.path.join(
            output_folder, '{}_{}_{}.txt'.format(routeUID, route_name, direction)
        )
        with open(timetable_filename, 'w') as output_file:
            output_file.write(', '.join(timetable_pack[0]))
    
    else:
        timetable_filename = os.path.join(
            output_folder, '{}_{}_{}.txt'.format(routeUID, route_name, direction)
        )
        with open(timetable_filename, 'w') as output_file:
            output_file.write('')

    if timetable_pack != None and direction == 0 and timetable_pack[1] != None:
        timetable_filename = os.path.join(
            output_folder, '{}_{}_{}.txt'.format(routeUID, route_name, 1)
        )
        with open(timetable_filename, 'w') as output_file:
            output_file.write(', '.join(timetable_pack[1]))

def main():
    weekday_timetable_folder = 'TXG_bus_timetable_weekday'
    weekend_timetable_folder = 'TXG_bus_timetable_weekend'
    route_record = 'route_record.csv'
    weekday = '2020-09-29'
    weekend = '2020-09-20'

    if not os.path.isfile(route_record):
        route_csv = os.path.join(
            r'D:\Users\63707\Documents\python3',
            r'bus_route\PTX_data\City\Taichung',
            'route_list.csv'
        )
        route_df = pd.read_csv(route_csv)
        route_df['done'] = 0
    else:
        route_df = pd.read_csv(route_record)

    chrome = initialize_webdriver()
    time.sleep(1)
    
    while min(route_df['done']) == 0:
        routeUID = route_df[route_df['done']==0].iloc[0].loc['SubRouteUID']
        direction = route_df[route_df['done']==0].iloc[0].loc['Direction']
        route_name = route_df[route_df['done']==0].iloc[0].loc['SubRouteName']

        print(route_name)
        weekday_timetable, weekend_timetable = query_timetable(
            route_name, chrome, weekday, weekend
        )

        if weekday_timetable != None:
            route_df.loc[
                (route_df['SubRouteUID']==routeUID)&(route_df['Direction']==direction), 'done'
            ] = 1
            
            if direction == 0 and len(weekday_timetable[1]) > 0:
                route_df.loc[
                    (route_df['SubRouteUID']==routeUID)&(route_df['Direction']==1), 'done'
                ] = 1
        else:
            route_df.loc[
                (route_df['SubRouteUID']==routeUID)&(route_df['Direction']==direction), 'done'
            ] = 2
        
        output_file(weekday_timetable, weekday_timetable_folder, routeUID, route_name, direction)
        output_file(weekend_timetable, weekend_timetable_folder, routeUID, route_name, direction)

        route_df.to_csv(route_record)

    print('完成')

if __name__ == '__main__':
     main()