# -*- coding: utf-8 -*-

import base64
import hmac
import os
import pickle
import shutil
from datetime import datetime, timedelta
from hashlib import sha1
from pprint import pprint
from time import mktime
from wsgiref.handlers import format_date_time

import pandas
from requests import request


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

class BusGroup():
    """
    project_zone: 計畫區域\n
    group_type: City or InterCity\n
    city_name: 縣市名稱，公路客運則為''\n
    load_local_data: 是否要載入本地儲存的公車資料
    """
    def __init__(self, project_zone, group_type, city_name='', load_local_data=False, my_auth=None):
        self.day_list = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        self.peak_list = ['morning_peak', 'evening_peak']
        self.other_time = ['offpeak', 'all_day']
        self.peak_bound = {
            'morning_peak': [datetime(1900, 1, 1, 7, 0), datetime(1900, 1, 1, 9, 0)],
            'evening_peak': [datetime(1900, 1, 1, 17, 0), datetime(1900, 1, 1, 19, 0)],
            'offpeak': [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)],
            'all_day': [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)],
        }
        self.day_group = {
            'weekend': ['all', ['Saturday', 'Sunday']],
            'weekday': ['peak', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']],
            'weekday_2': ['peak', ['Tuesday', 'Wednesday', 'Thursday']]
        }

        self.project_zone = project_zone
        self.group_type = group_type
        self.city_name = city_name
        self.load_local_data = load_local_data
        
        self.set_group_url()
        print('\nInitialize {}'.format(self.group_url))
        #建立儲存PTX資料的路徑
        os.makedirs(os.path.join('saved_request', self.group_url), exist_ok=True)
        #讀取公車路線資料
        self.Route = self.get_PTX_data('Route', my_auth)
        #讀取公車站牌資料
        #站牌(stop): 站牌桿實際位置; 站位(station): 同一個站名聚合在一個點位
        self.Stop = self.get_PTX_data('Stop', my_auth)
        #讀取公車路線站序資料
        self.StopOfRoute = self.get_PTX_data('StopOfRoute', my_auth)
        self.modify_StopOfRoute()
        #讀取公車路線班表資料
        if self.city_name != 'Taichung':
            self.Schedule = self.get_PTX_data('Schedule', my_auth)
            self.process_timetable()
        #統整不同業者的公路客運路線
        self.drop_route = []
        self.aggregate_bus_route()
        #清除前次輸出
        if os.path.exists(self.group_url):
            shutil.rmtree(self.group_url)
    
    def set_group_url(self):
        """設定網址中的區域名稱: City/{City} or Intercity"""
        if self.city_name == '':
            self.group_url = self.group_type
        else:
            self.group_url =  '{}/{}'.format(self.group_type, self.city_name)

    def get_PTX_data(self, data_name, my_auth):
        """讀取PTX資料"""
        print('\tStart importing {}'.format(data_name))
        local_pickle_name = os.path.join(
            'saved_request', self.group_url, '{}.pickle'.format(data_name)
        )
        #如果要載入本地資料，而且本地資料也存在的話，就把本地資料載入而不是去PTX抓
        if os.path.isfile(local_pickle_name) and self.load_local_data:
            with open(local_pickle_name, 'rb') as local_file:
                PTX_data = pickle.load(local_file)
        else:
            raw_PTX = request(
                'get', 'https://ptx.transportdata.tw/MOTC/v2/Bus/{}/{}?$format=JSON'.format(
                    data_name, self.group_url
                ), 
                headers= my_auth.get_auth_header()
            )
            if raw_PTX.status_code == 200:
                PTX_data = pandas.read_json(raw_PTX.content)
                P = open(local_pickle_name, 'wb')
                pickle.dump(PTX_data, P)
                P.close()
            else:
                PTX_data = []
        
        print('\tComplete importing {}'.format(data_name))
        return PTX_data

    def modify_StopOfRoute(self):
        """修改StopOfRoute的DataFrame，以加上起終點文字"""
        Headsign = ['' for _ in self.StopOfRoute.index]
        for i in self.StopOfRoute.index:
            subroute_list = self.Route[self.Route['RouteUID'] == self.StopOfRoute.RouteUID[i]].SubRoutes.tolist()[0]
            for j in subroute_list:
                if j['SubRouteUID'] == self.StopOfRoute.SubRouteUID[i]:
                    Headsign[i] = j['Headsign']
                    break
        self.StopOfRoute['Headsign'] = Headsign
        self.StopOfRoute['Schedule'] = [{} for _ in self.StopOfRoute.index]

    def check_if_stop_in_zone(self):
        """
        檢查公車站牌是否於計畫區域內：\n
        使用LocationCityCode判斷站牌是否在區域內\n
        再使用站牌ID對應各路線各站點所在縣市\n
        """
        if self.group_type == 'InterCity':
            #記錄有無經過計畫區域，0=無，1=有
            if_pass_zone = [0 for _ in self.Stop.index]
            #依序檢查每一條線
            for s in self.Stop.index:
                #遇到是計畫區域內的點就記錄為1
                if self.Stop.LocationCityCode[s] in self.project_zone:
                    if_pass_zone[s] = 1
            self.Stop['if_pass_zone'] = if_pass_zone
        else:
            self.Stop['if_pass_zone'] = 1

    def aggregate_bus_route(self):
        """整合不同營運單位的公路客運"""
        checked_route_ID = {}
        for i in self.StopOfRoute.index:
            UID_dir = '{}_{}'.format(
                self.StopOfRoute.SubRouteUID[i], 
                self.StopOfRoute.Direction[i]
            )
            if UID_dir not in checked_route_ID:
                checked_route_ID[UID_dir] = i
            else:
                self.StopOfRoute.Operators[checked_route_ID[UID_dir]].append(
                    self.StopOfRoute.Operators[i][0]
                )
                self.drop_route.append(i)

    def combine_schedule(self, schedule_main, schedule_other):
        for day in self.day_list:
            for peak in self.peak_list + self.other_time:
                schedule_main[day][peak]['n'] += schedule_other[day][peak]['n']
                schedule_main[day][peak]['st'] = min(schedule_main[day][peak]['st'], schedule_other[day][peak]['st'])
                schedule_main[day][peak]['ed'] = min(schedule_main[day][peak]['ed'], schedule_other[day][peak]['ed'])
        return schedule_main

    def check_if_route_pass_zone(self):
        """
        檢查公路客運路線是否經過計畫區域：\n
        使用LocationCityCode判斷站牌是否在區域內\n
        再使用站牌ID對應各路線各站點所在縣市
        """
        if self.group_type == 'InterCity':
            #記錄有無經過計畫區域，0=無，1=有
            if_pass_zone = [0 for _ in self.StopOfRoute.index]
            #依序檢查每一條線
            for i in self.StopOfRoute.index:
                #依序檢查線上的每一個站
                for stop in self.StopOfRoute.Stops[i]:
                    #遇到是計畫區域內的點就記錄為1，並跳出迴圈
                    if stop['LocationCityCode'] in self.project_zone:
                        if_pass_zone[i] = 1
                        break
            
            self.StopOfRoute['if_pass_zone'] = if_pass_zone
        else:
            #市區公車就都記錄為都有在區域內
            self.StopOfRoute['if_pass_zone'] = 1

    def process_timetable(self):
        if self.city_name != 'Taichung':
            for r in self.Schedule.index:
                bus_schedule = self.new_bus_schedule()
                print(self.Schedule.SubRouteName[r]['Zh_tw'])

                if 'Timetables' in self.Schedule:
                    bus_schedule = self.manage_bus_timetable(self.Schedule.Timetables[r], bus_schedule)
                elif 'Frequencys' in self.Schedule:
                    bus_schedule = self.manage_bus_frequency(self.Schedule.Frequencys[r], bus_schedule)

    def new_bus_schedule(self):
        bus_schedule = {}
        for day in self.day_list:
            bus_schedule[day] = {}
            for peak in self.peak_list + self.other_time:
                bus_schedule[day][peak] = {
                    'n': 0, 
                    'st': self.peak_bound[peak][0], 
                    'ed': self.peak_bound[peak][1]
                }
        return bus_schedule

    def check_bus_peak(self, BusStopTime):
        """檢查公車是晨峰昏峰還是離峰"""
        bus_time = datetime.strptime(BusStopTime['DepartureTime'], '%H:%M')
        if bus_time > self.peak_bound['morning_peak'][0] and bus_time < self.peak_bound['morning_peak'][1]:
            return 'morning_peak'
        elif bus_time > self.peak_bound['evening_peak'][0] and bus_time < self.peak_bound['evening_peak'][1]:
            return 'evening_peak'
        else:
            return 'offpeak'

    def manage_bus_timetable(self, Timetables, bus_schedule):
        """檢查班表式資料的班距"""
        for BusStopTime in Timetables:
            if 'ServiceDay' in BusStopTime:
                for StopTime in BusStopTime['StopTimes']:
                    for day in self.day_list:
                        if BusStopTime['ServiceDay'][day] != 0:
                            bus_schedule[day][self.check_bus_peak(StopTime)]['n'] += 1
                            bus_schedule[day]['all_day']['n'] += 1
                            bus_schedule[day]['all_day']['st'] = min(
                                bus_schedule[day]['all_day']['st'], 
                                datetime.strptime(StopTime['DepartureTime'], '%H:%M')
                            )
                            bus_schedule[day]['all_day']['ed'] = max(
                                bus_schedule[day]['all_day']['ed'], 
                                datetime.strptime(StopTime['DepartureTime'], '%H:%M')
                            )
                            bus_schedule[day]['offpeak']['st'] = bus_schedule[day]['all_day']['st']
                            bus_schedule[day]['offpeak']['ed'] = bus_schedule[day]['all_day']['ed']
        
        return bus_schedule

    def manage_bus_frequency(self, Frequencys, bus_schedule):
        """檢查班距式資料的班距"""
        for BusFrequency in Frequencys:
            if 'ServiceDay' in BusFrequency:
                headway = (BusFrequency['MinHeadwayMins'] + BusFrequency['MaxHeadwayMins']) / 2
                start_time = datetime.strptime(BusFrequency['StartTime'], '%H:%M')
                end_time = datetime.strptime(BusFrequency['EndTime'], '%H:%M')

                duration = {}
                for peak in self.peak_list:
                    duration[peak] = max(0, 
                        min(self.peak_bound[peak][1], end_time) - 
                        max(self.peak_bound[peak][0], start_time))
                duration['all_day'] = end_time - start_time
                duration['offpeak'] = duration['all_day'] - sum(duration[peak] for peak in self.peak_list)

                for day in self.day_list:
                    if BusFrequency['ServiceDay'][day] != 0:
                        for peak in self.peak_list + self.other_time:
                            bus_schedule[day][peak]['n'] += (duration[peak] / timedelta(minutes=1)) / headway
                        bus_schedule[day]['all_day']['st'] = min(bus_schedule[day]['all_day']['st'], start_time)
                        bus_schedule[day]['all_day']['ed'] = max(bus_schedule[day]['all_day']['ed'], end_time)
                        
        for day in self.day_list:
            bus_schedule[day]['offpeak']['st'] = bus_schedule[day]['all_day']['st']
            bus_schedule[day]['offpeak']['ed'] = bus_schedule[day]['all_day']['ed']
        
        return bus_schedule

    def get_headway(self, bus_schedule):
        headway = {}
        for group in self.day_group:
            num_day = len(self.day_group[group][1])

            headway[group] = {}
            for peak in self.peak_list:
                duration = (
                    sum((bus_schedule[day][peak]['ed'] - bus_schedule[day][peak]['st']) / timedelta(minutes=1)
                        for day in self.day_group[group][1])
                )
                headway[group][peak] = int(duration / 
                    max(sum(bus_schedule[day][peak]['n'] for day in self.day_group[group][1]), num_day)
                )
            for time in self.other_time:
                duration = (
                    sum(max((bus_schedule[day][time]['ed'] - bus_schedule[day][time]['st']) / timedelta(minutes=1), 240)
                        for day in self.day_group[group][1])
                )
                num_bus = sum(bus_schedule[day][time]['n'] for day in self.day_group[group][1])
                if num_bus < 3 * num_day:
                    headway[group][time] = 240
                else:
                    headway[group][time] = int(min(duration / num_bus, 240))
        return headway

    def output_stop_info(self):
        """輸出公車站牌點位"""
        print('Output stop of {}'.format(self.group_url))
        #判別路線是否經過計畫區域
        self.check_if_stop_in_zone()
        os.makedirs(self.group_url, exist_ok=True)
        #輸出站牌資料
        stop_file = os.path.join(self.group_url, 'bus_stop.csv')
        with open(stop_file, 'w', encoding='utf-8') as stop_out:
            stop_out.write(
                'StopUID,PositionLat,PositionLon,StopName,'
                'LocationCityCode,if_pass_zone\n'
            )
            for s in self.Stop.index:
                stop_out.write(
                    '{StopUID},{PositionLat},{PositionLon},{StopName},'
                    '{LocationCityCode},{if_pass_zone}\n'.format(
                        StopUID=self.Stop.StopUID[s],
                        PositionLon=self.Stop.StopPosition[s]['PositionLat'],
                        PositionLat=self.Stop.StopPosition[s]['PositionLon'],
                        StopName=self.Stop.StopName[s]['Zh_tw'],
                        LocationCityCode=str(self.Stop.LocationCityCode[s]).upper(),
                        if_pass_zone=self.Stop.if_pass_zone[s]
                    )
                )
            
    def output_route_seq(self):
        """輸出公車路線資訊與站牌序列"""
        print('Output route of ' + self.group_url)
        #判別路線是否經過計畫區域
        self.check_if_route_pass_zone()
        #建立資料夾
        os.makedirs(self.group_url, exist_ok=True)

        #生成檔名：route_list.csv
        list_file = os.path.join(self.group_url, 'route_list.csv')
        #寫入路線清單
        with open(list_file, 'w', encoding='utf-8') as list_out:
            #寫入停站列表
            #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,有無經過計畫區域
            list_out.write(
                'SubRouteUID,SubRouteName,Headsign,OperatorName,Direction,if_pass_zone\n'
            )
            for i in self.StopOfRoute.index:
                if i not in self.drop_route:
                    list_out.write(
                        '{SubRouteUID},{SubRouteName},{Headsign},'.format(
                            SubRouteUID=self.StopOfRoute.SubRouteUID[i],
                            SubRouteName=self.StopOfRoute.SubRouteName[i]['Zh_tw'],
                            Headsign=self.StopOfRoute.Headsign[i].replace(' ', '').replace(',', '_')
                        )
                    )
                    for ON in self.StopOfRoute.Operators[i]:
                        list_out.write(
                            '{OperatorName}/'.format(OperatorName=ON['OperatorName']['Zh_tw'])
                        )
                    list_out.write(',{Direction},{if_pass_zone}\n'.format(
                            Direction=self.StopOfRoute.Direction[i],
                            if_pass_zone=self.StopOfRoute.if_pass_zone[i]
                        )
                    )

                    #生成檔名：SubRouteUID_路線中文名_路線方向.csv
                    file_name = os.path.join(
                        self.group_url, 
                        '{SubRouteUID}_{SubRouteName}_{Direction}.csv'.format(
                            SubRouteUID=self.StopOfRoute.SubRouteUID[i],
                            SubRouteName=self.StopOfRoute.SubRouteName[i]['Zh_tw'],
                            Direction=self.StopOfRoute.Direction[i]
                        )
                    )
                    with open(file_name, 'w', encoding='utf-8') as out:
                        #寫入站牌列表
                        #各欄位為: 路線經過站牌之順序,站牌ID,緯度,經度,上下車站別,站牌名稱,站牌位置縣市之代碼
                        out.write(
                            'StopSequence,StopUID,PositionLat,PositionLon,'
                            'StopBoarding,StopName,LocationCityCode\n'
                        )
                        for stop in self.StopOfRoute.Stops[i]:
                            out.write(
                                '{StopSequence},{StopUID},{PositionLat},{PositionLon},'
                                '{StopBoarding},{StopName},{LocationCityCode}\n'.format(
                                    StopSequence=stop['StopSequence'],
                                    StopUID=stop['StopUID'],
                                    PositionLat=stop['StopPosition']['PositionLat'],
                                    PositionLon=stop['StopPosition']['PositionLon'],
                                    StopBoarding=stop['StopBoarding'],
                                    StopName=stop['StopName']['Zh_tw'],
                                    LocationCityCode=stop['LocationCityCode']
                                )
                            )

    def output_schedule(self):
        """輸出公車班表"""
        print('Output schedule of ' + self.group_url)
        #判別路線是否經過計畫區域
        self.check_if_route_pass_zone()
        #建立資料夾
        os.makedirs(self.group_url, exist_ok=True)

        #生成檔名：route_list.csv
        headway_file = os.path.join(self.group_url, 'route_headway.csv')
        #寫入路線清單
        with open(headway_file, 'w', encoding='utf-8') as list_out:
            #寫入停站列表
            #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,有無經過計畫區域
            list_out.write(
                'SubRouteUID,SubRouteName,Headsign,Direction,if_pass_zone,'
                'weekend_AD,weekday_AM,weekday_PM,weekday_non,weekday2_AM,weekday2_PM,weekday2_non\n'
            )
            for i in self.StopOfRoute.index:
                if i not in self.drop_route:
                    list_out.write(
                        '{SubRouteUID},{SubRouteName},{Headsign},{Direction},{if_pass_zone}\n'.format(
                            SubRouteUID=self.StopOfRoute.SubRouteUID[i],
                            SubRouteName=self.StopOfRoute.SubRouteName[i]['Zh_tw'],
                            Headsign=self.StopOfRoute.Headsign[i].replace(' ', '').replace(',', '_'),
                            Direction=self.StopOfRoute.Direction[i],
                            if_pass_zone=self.StopOfRoute.if_pass_zone[i]
                        )
                    )

    def stop_info_str(self, s):
        return '{StopUID},{Lat},{Lon},{StopName},{LocationCityCode}\n'.format(
            StopUID=self.Stop.StopUID[s],
            Lat=self.Stop.StopPosition[s]['PositionLat'],
            Lon=self.Stop.StopPosition[s]['PositionLon'],
            StopName=self.Stop.StopName[s]['Zh_tw'],
            LocationCityCode=str(self.Stop.LocationCityCode[s]).upper()
        )

def main():

    a = Auth(app_id, app_key)

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
    #代號 -> 英文
    City_map = {
        'HSZ': {'zhtw': '新竹市', 'en': 'Hsinchu'}, 
        'TXG': {'zhtw': '臺中市', 'en': 'Taichung'}, 
        'HSQ': {'zhtw': '新竹縣', 'en': 'HsinchuCounty'}, 
        'TAO': {'zhtw': '桃園市', 'en': 'Taoyuan'}, 
        'MIA': {'zhtw': '苗栗縣', 'en': 'MiaoliCounty'}, 
        'NAN': {'zhtw': '南投縣', 'en': 'NantouCounty'}, 
        'CYI': {'zhtw': '嘉義市', 'en': 'Chiayi'}, 
        'CYQ': {'zhtw': '嘉義縣', 'en': 'ChiayiCounty'}, 
        'YUN': {'zhtw': '雲林縣', 'en': 'YunlinCounty'}, 
        'PIF': {'zhtw': '屏東縣', 'en': 'PingtungCounty'}, 
        'ILA': {'zhtw': '宜蘭縣', 'en': 'YilanCounty'}, 
        'TNN': {'zhtw': '彰化縣', 'en': 'Tainan'}, 
        'CHA': {'zhtw': '新北市', 'en': 'ChanghuaCounty'}, 
        'NWT': {'zhtw': '臺南市', 'en': 'NewTaipei'}, 
        'TPE': {'zhtw': '臺北市', 'en': 'Taipei'}, 
        'TTT': {'zhtw': '臺東縣', 'en': 'TaitungCounty'}, 
        'KEE': {'zhtw': '基隆市', 'en': 'Keelung'}, 
        'HUA': {'zhtw': '花蓮縣', 'en': 'HualienCounty'}, 
        'KHH': {'zhtw': '高雄市', 'en': 'Kaohsiung'}, 
        'PEN': {'zhtw': '澎湖縣', 'en': 'PenghuCounty'}, 
        'KIN': {'zhtw': '金門縣', 'en': 'KinmenCounty'}, 
        'LIE': {'zhtw': '連江縣', 'en': 'LienchiangCounty'},
    }

    #計畫區域縣市代碼
    project_zone = ['MIA', 'TXG', 'CHA', 'NAN', 'YUN']

    Bus = {}
    for city in project_zone:
        Bus[city] = BusGroup(
            project_zone, 'City', City_map[city]['en'], 
            load_local_data=True, my_auth=a
        )
        Bus[city].output_stop_info()
        Bus[city].output_route_seq()

    raise IOError

    Bus['IC'] = BusGroup(
        project_zone, 'InterCity', 
        load_local_data=True, my_auth=a
    )
    Bus['IC'].output_stop_info()
    Bus['IC'].output_route_seq()

    #輸出全區域車站清單
    print('Output stop in central Taiwan')
    #輸出站牌資料
    stop_file = 'central_taiwan_bus_stop.csv'
    with open(stop_file, 'w', encoding='utf-8') as stop_out:
        stop_out.write('StopUID,PositionLat,PositionLon,StopName,LocationCityCode\n')
        for city in project_zone:
            for s in Bus[city].Stop.index:
                if Bus[city].Stop.if_pass_zone[s] == 1:
                    stop_out.write(Bus[city].stop_info_str(s))
        
        for s in Bus['IC'].Stop.index:
            if Bus['IC'].Stop.if_pass_zone[s] == 1:
                stop_out.write(Bus['IC'].stop_info_str(s))

if __name__ == '__main__':
    main()
