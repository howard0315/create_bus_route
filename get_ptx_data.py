# -*- coding: utf-8 -*-

import base64
import hmac
import os
import pickle
import shutil
from datetime import datetime
from hashlib import sha1
from pprint import pprint
from time import mktime
from wsgiref.handlers import format_date_time

import pandas
from requests import request

app_id = '79a340b8c2e7499bbedaf110c172f6f3'
app_key = 'Rt8k1rc5QhLO7kyj6Aw_pfid6X4'

class Auth():

    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key

    def get_auth_header(self):
        xdate = format_date_time(mktime(datetime.now().timetuple()))
        hashed = hmac.new(self.app_key.encode('utf8'), ('x-date: ' + xdate).encode('utf8'), sha1)
        signature = base64.b64encode(hashed.digest()).decode()

        authorization = 'hmac username="' + self.app_id + '", ' + \
                        'algorithm="hmac-sha1", ' + \
                        'headers="x-date", ' + \
                        'signature="' + signature + '"'
        return {
            'Authorization': authorization,
            'x-date': format_date_time(mktime(datetime.now().timetuple())),
            'Accept - Encoding': 'gzip'
        }

a = Auth(app_id, app_key)

class BusGroup():
    
    #project_zone: 計畫區域
    #group_type: City or InterCity
    #city_name: 縣市名稱，公路客運則為''
    #load_local_data: 是否要載入本地儲存的公車資料
    def __init__(self, project_zone, group_type, city_name='', load_local_data=False):
        self.project_zone = project_zone
        self.group_type = group_type
        self.city_name = city_name
        #設定網址中的區域名稱: City/{City} or Intercity
        if self.city_name == '':
            self.bus_group_url = self.group_type
        else:
            self.bus_group_url = self.group_type + '/' + self.city_name
        self.load_local_data = load_local_data
        print('\nInitialize ' + self.bus_group_url)
        #建立儲存PTX資料的路徑
        os.makedirs('saved_request/' + self.bus_group_url, exist_ok=True)
        #讀取公車路線資料
        self.bus_Route = self.get_PTX_data('Route')
        #讀取公車站牌資料
        #站牌(stop): 站牌桿實際位置; 站位(station): 同一個站名聚合在一個點位
        self.bus_Stop = self.get_PTX_data('Stop')
        #讀取公車路線站序資料
        self.bus_StopOfRoute = self.get_PTX_data('StopOfRoute')
        self.modify_StopOfRoute()
        #統整不同業者的公路客運路線
        self.drop_route = []
        self.aggregate_bus_route()
        #清除前次輸出
        if os.path.exists(self.bus_group_url):
            shutil.rmtree(self.bus_group_url)
    
    #讀取PTX資料
    def get_PTX_data(self, data_name):
        print('\tStart importing ' + data_name)
        local_pickle_name = 'saved_request/' + self.bus_group_url + \
            '/' + data_name + '.pickle'
        #如果要載入本地資料，而且本地資料也存在的話，就把本地資料載入而不是去PTX抓
        if os.path.isfile(local_pickle_name) and self.load_local_data:
            with open(local_pickle_name, 'rb') as local_file:
                PTX_data = pickle.load(local_file)
        else:
            raw_PTX = request('get', 'https://ptx.transportdata.tw/MOTC/v2/Bus/' + \
                                data_name + '/' + self.bus_group_url + '?$format=JSON', 
                                headers= a.get_auth_header())
            if raw_PTX.status_code == 200:
                PTX_data = pandas.read_json(raw_PTX.content)
                P = open(local_pickle_name, 'wb')
                pickle.dump(PTX_data, P)
                P.close()
            else:
                PTX_data = []
        
        print('\tComplete importing ' + data_name)
        return PTX_data

    #修改StopOfRoute的DataFrame，以加上起終點文字
    def modify_StopOfRoute(self):
        Headsign = ['' for _ in self.bus_StopOfRoute.index]
        DestinationStopNameZh = ['' for _ in self.bus_StopOfRoute.index]
        for i in self.bus_StopOfRoute.index:
            subroute_list = self.bus_Route[self.bus_Route['RouteUID'] == \
                self.bus_StopOfRoute.RouteUID[i]].SubRoutes.tolist()[0]
            for j in subroute_list:
                if j['SubRouteUID'] == self.bus_StopOfRoute.SubRouteUID[i]:
                    Headsign[i] = j['Headsign']
                    break
        self.bus_StopOfRoute.insert(len(self.bus_StopOfRoute.columns), \
            'Headsign', Headsign)

    #檢查公車站牌是否於計畫區域內
    def check_if_stop_pass_zone(self):
        #使用LocationCityCode判斷站牌是否在區域內
        #再使用站牌ID對應各路線各站點所在縣市
        if self.group_type == 'InterCity':
            #記錄有無經過計畫區域，0=無，1=有
            if_pass_zone = [0 for _ in self.bus_Stop.index]
            #依序檢查每一條線
            for s in self.bus_Stop.index:
                #遇到是計畫區域內的點就記錄為1
                if self.bus_Stop.LocationCityCode[s] in self.project_zone:
                    if_pass_zone[s] = 1
            if 'if_pass_zone' in self.bus_Stop.columns:
                self.bus_Stop.if_pass_zone = if_pass_zone
            else:
                self.bus_Stop.insert(len(self.bus_Stop.columns), \
                    'if_pass_zone', if_pass_zone)
        else:
            #市區公車就都記錄為都有在區域內
            if 'if_pass_zone' in self.bus_Stop.columns:
                self.bus_Stop.if_pass_zone = 1
            else:
                self.bus_Stop.insert(len(self.bus_Stop.columns), \
                    'if_pass_zone', 1)

    #整合不同營運單位的公路客運
    def aggregate_bus_route(self):
        checked_route_ID = {}
        for i in self.bus_StopOfRoute.index:
            UID_dir = self.bus_StopOfRoute.SubRouteUID[i] + '_' + str(self.bus_StopOfRoute.Direction[i])
            if UID_dir not in checked_route_ID:
                checked_route_ID[UID_dir] = i
            else:
                self.bus_StopOfRoute.Operators[checked_route_ID[UID_dir]].append(self.bus_StopOfRoute.Operators[i][0])
                self.drop_route.append(i)

    #檢查公路客運路線是否經過計畫區域
    def check_if_route_pass_zone(self):
        #使用LocationCityCode判斷站牌是否在區域內
        #再使用站牌ID對應各路線各站點所在縣市
        if self.group_type == 'InterCity':
            #記錄有無經過計畫區域，0=無，1=有
            if_pass_zone = [0 for _ in self.bus_StopOfRoute.index]
            #依序檢查每一條線
            for i in self.bus_StopOfRoute.index:
                #依序檢查線上的每一個站
                for stop in self.bus_StopOfRoute.Stops[i]:
                    #遇到是計畫區域內的點就記錄為1，並跳出迴圈
                    if stop['LocationCityCode'] in self.project_zone:
                        if_pass_zone[i] = 1
                        break
            if 'if_pass_zone' in self.bus_StopOfRoute.columns:
                self.bus_StopOfRoute.if_pass_zone = if_pass_zone
            else:
                self.bus_StopOfRoute.insert(len(self.bus_StopOfRoute.columns), \
                    'if_pass_zone', if_pass_zone)
        else:
            #市區公車就都記錄為都有在區域內
            if 'if_pass_zone' in self.bus_StopOfRoute.columns:
                self.bus_StopOfRoute.if_pass_zone = 1
            else:
                self.bus_StopOfRoute.insert(len(self.bus_StopOfRoute.columns), \
                    'if_pass_zone', 1)

    #輸出公車站牌點位
    def output_stop_info(self):
        print('Output stop of ' + self.bus_group_url)
        #判別路線是否經過計畫區域
        self.check_if_stop_pass_zone()
        #建立資料夾
        os.makedirs(self.bus_group_url, exist_ok=True)
        #輸出站牌資料
        stop_file = self.bus_group_url + '/bus_stop.csv'
        with open(stop_file, 'w', encoding='utf-8') as stop_out:
            stop_out.write('StopUID,PositionLat,PositionLon,' + \
                'StopName,LocationCityCode,if_pass_zone\n')
            for s in self.bus_Stop.index:
                stop_out.write(self.bus_Stop.StopUID[s] + ',' + \
                    str(self.bus_Stop.StopPosition[s]['PositionLat']) + ',' + \
                    str(self.bus_Stop.StopPosition[s]['PositionLon']) + ',' + \
                    self.bus_Stop.StopName[s]['Zh_tw'] + ',' + \
                    str(self.bus_Stop.LocationCityCode[s]).upper() + ',' + \
                    str(self.bus_Stop.if_pass_zone[s]) + '\n')
            
    #輸出公車路線資訊與站牌序列
    def output_route_seq(self):
        print('Output route of ' + self.bus_group_url)
        #判別路線是否經過計畫區域
        self.check_if_route_pass_zone()
        #建立資料夾
        os.makedirs(self.bus_group_url, exist_ok=True)

        #生成檔名：route_list.csv
        list_file = self.bus_group_url + '/route_list.csv'
        #寫入路線清單
        with open(list_file, 'w', encoding='utf-8') as list_out:
            #寫入停站列表
            #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,有無經過計畫區域
            list_out.write('SubRouteUID,SubRouteName,' + \
                'Headsign,OperatorName,Direction,if_pass_zone\n')
            for i in self.bus_StopOfRoute.index:
                if i not in self.drop_route:
                    list_out.write(self.bus_StopOfRoute.SubRouteUID[i] + ',' + \
                        self.bus_StopOfRoute.SubRouteName[i]['Zh_tw'] + ',' + \
                        self.bus_StopOfRoute.Headsign[i].replace(' ', '').replace(',', '_') + ',')
                    for ON in self.bus_StopOfRoute.Operators[i]:
                        list_out.write(ON['OperatorName']['Zh_tw'] + '/')
                    list_out.write(',' + \
                        str(self.bus_StopOfRoute.Direction[i]) + ',' + \
                        str(self.bus_StopOfRoute.if_pass_zone[i]) + '\n')

                    #生成檔名：SubRouteUID_路線中文名_路線方向.csv
                    route_ID = self.bus_StopOfRoute.SubRouteUID[i] + '_' + \
                        self.bus_StopOfRoute.SubRouteName[i]['Zh_tw'] + '_' + \
                        str(self.bus_StopOfRoute.Direction[i])
                    file_name = self.bus_group_url + '/' + route_ID + '.csv'
                    with open(file_name, 'w', encoding='utf-8') as out:
                        #寫入站牌列表
                        #各欄位為: 路線經過站牌之順序,站牌ID,緯度,經度,上下車站別,站牌名稱,站牌位置縣市之代碼
                        out.write('StopSequence,StopUID,PositionLat,PositionLon,' + \
                            'StopBoarding,StopName,LocationCityCode' + '\n')
                        for stop in self.bus_StopOfRoute.Stops[i]:
                            out.write(str(stop['StopSequence']) + ',' + \
                                str(stop['StopUID']) + ',' + \
                                str(stop['StopPosition']['PositionLat']) + ',' + \
                                str(stop['StopPosition']['PositionLon']) + ',' + \
                                str(stop['StopBoarding']) + ',' + \
                                stop['StopName']['Zh_tw'] + ',' + \
                                stop['LocationCityCode'] + '\n')

#縣市名稱列舉
#中文 -> 拼音
City_zhtw2en = {
    '臺北市': 'Taipei', '新北市': 'NewTaipei', '桃園市': 'Taoyuan', '臺中市': 'Taichung', \
    '臺南市': 'Tainan', '高雄市': 'Kaohsiung', '基隆市': 'Keelung', '新竹市': 'Hsinchu', \
    '新竹縣': 'HsinchuCounty', '苗栗縣': 'MiaoliCounty', '彰化縣': 'ChanghuaCounty', \
    '南投縣': 'NantouCounty', '雲林縣': 'YunlinCounty', '嘉義縣': 'ChiayiCounty', \
    '嘉義市': 'Chiayi', '屏東縣': 'PingtungCounty', '宜蘭縣': 'YilanCounty', \
    '花蓮縣': 'HualienCounty', '臺東縣': 'TaitungCounty', '金門縣': 'KinmenCounty', \
    '澎湖縣': 'PenghuCounty', '連江縣': 'LienchiangCounty'
}
#代號 -> 中文
City_code2zhtw = {
    'HSZ': '新竹市', 'TXG': '臺中市', 'HSQ': '新竹縣', 'TAO': '桃園市', 
    'MIA': '苗栗縣', 'NAN': '南投縣', 'CYI': '嘉義市', 'CYQ': '嘉義縣', 
    'YUN': '雲林縣', 'PIF': '屏東縣', 'ILA': '宜蘭縣', 'CHA': '彰化縣', 
    'NWT': '新北市', 'TNN': '臺南市', 'TPE': '臺北市', 'TTT': '臺東縣', 
    'KEE': '基隆市', 'HUA': '花蓮縣', 'KHH': '高雄市', 'PEN': '澎湖縣',
    'KIN': '金門縣', 'LIE': '連江縣'
}
#代號 -> 英文
City_code2en = {
    'HSZ': 'Hsinchu', 'TXG': 'Taichung', 'HSQ': 'HsinchuCounty', 
    'TAO': 'Taoyuan', 'MIA': 'MiaoliCounty', 'NAN': 'NantouCounty', 
    'CYI': 'Chiayi', 'CYQ': 'ChiayiCounty', 'YUN': 'YunlinCounty', 
    'PIF': 'PingtungCounty', 'ILA': 'YilanCounty', 'TNN': 'Tainan', 
    'CHA': 'ChanghuaCounty', 'NWT': 'NewTaipei', 'TPE': 'Taipei', 
    'TTT': 'TaitungCounty', 'KEE': 'Keelung', 'HUA': 'HualienCounty', 
    'KHH': 'Kaohsiung', 'PEN': 'PenghuCounty', 'KIN': 'KinmenCounty', 
    'LIE': 'LienchiangCounty'
}

#計畫區域縣市代碼
project_zone = ['MIA', 'TXG', 'CHA', 'NAN', 'YUN']

Bus = {}
Bus['City'] = {}

for city in project_zone:
    Bus['City'][city] = BusGroup(project_zone, 'City', City_code2en[city], load_local_data=True)
    Bus['City'][city].output_stop_info()
    Bus['City'][city].output_route_seq()

Bus['InterCity'] = BusGroup(project_zone, 'InterCity', load_local_data=True)
Bus['InterCity'].output_stop_info()
Bus['InterCity'].output_route_seq()

#輸出全區域車站清單
print('Output stop in central Taiwan')
#輸出站牌資料
stop_file = 'central_taiwan_bus_stop.csv'
with open(stop_file, 'w', encoding='utf-8') as stop_out:
    stop_out.write('StopUID,PositionLat,PositionLon,' + \
        'StopName,LocationCityCode\n')
    for city in project_zone:
        for s in Bus['City'][city].bus_Stop.index:
            if Bus['City'][city].bus_Stop.if_pass_zone[s] == 1:
                stop_out.write(Bus['City'][city].bus_Stop.StopUID[s] + ',' + \
                    str(Bus['City'][city].bus_Stop.StopPosition[s]['PositionLat']) + ',' + \
                    str(Bus['City'][city].bus_Stop.StopPosition[s]['PositionLon']) + ',' + \
                    Bus['City'][city].bus_Stop.StopName[s]['Zh_tw'] + ',' + \
                    str(Bus['City'][city].bus_Stop.LocationCityCode[s]).upper() + '\n')
    
    for s in Bus['InterCity'].bus_Stop.index:
        if Bus['InterCity'].bus_Stop.if_pass_zone[s] == 1:
            stop_out.write(Bus['InterCity'].bus_Stop.StopUID[s] + ',' + \
                str(Bus['InterCity'].bus_Stop.StopPosition[s]['PositionLat']) + ',' + \
                str(Bus['InterCity'].bus_Stop.StopPosition[s]['PositionLon']) + ',' + \
                Bus['InterCity'].bus_Stop.StopName[s]['Zh_tw'] + ',' + \
                str(Bus['InterCity'].bus_Stop.LocationCityCode[s]).upper() + '\n')
