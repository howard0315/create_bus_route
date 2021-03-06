# -*- coding: utf-8 -*-

import base64
import copy
import hmac
import os
import pickle
import shutil
import math
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
        self.other_time = ['offpeak', 'all_day', 'AD_nopeak']
        self.peak_bound = {
            'morning_peak': [datetime(1900, 1, 1, 5, 30), datetime(1900, 1, 1, 9, 30)],
            'evening_peak': [datetime(1900, 1, 1, 15, 30), datetime(1900, 1, 1, 19, 30)]
        }
        self.peak_length = timedelta(hours=2)
        self.section_length = timedelta(minutes=15)
        self.num_peak_section = int(self.peak_length / self.section_length)
        for time in self.other_time:
            self.peak_bound[time] = [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)]
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
            self.schdl = Schedule(
                self.get_PTX_data('Schedule', my_auth), 
                self.day_list, 
                self.peak_list, self.other_time, 
                self.peak_bound,
                self.peak_length,
                self.section_length
            )
            self.process_timetable()
            self.calculate_headway()
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
            self.group_url = os.path.join(self.group_type, self.city_name)

    def get_PTX_data(self, data_name, my_auth):
        """讀取PTX資料"""
        print('\tStart importing {}'.format(data_name))
        local_pickle_name = os.path.join(
            'PTX_data', 'saved_request', self.group_url, '{}.pickle'.format(data_name)
        )
        #如果要載入本地資料，而且本地資料也存在的話，就把本地資料載入而不是去PTX抓
        if os.path.isfile(local_pickle_name) and self.load_local_data:
            print('\tSaved request found: {}'.format(data_name))
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
        self.StopOfRoute['Schedule'] = [[] for _ in self.StopOfRoute.index]
        self.StopOfRoute['Headway'] = [[] for _ in self.StopOfRoute.index]

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
                
                if (self.StopOfRoute.Schedule[checked_route_ID[UID_dir]] != [] and 
                    self.StopOfRoute.Schedule[i] != []):
                    self.StopOfRoute.loc[checked_route_ID[UID_dir], 'Schedule'] = [
                        self.combine_schedule(
                            self.StopOfRoute.Schedule[checked_route_ID[UID_dir]], 
                            self.StopOfRoute.Schedule[i]
                        )
                    ]
                self.drop_route.append(i)

    def calculate_headway(self):
        for i in self.StopOfRoute.index:
            self.StopOfRoute.loc[i, 'Headway'] = [self.get_headway(self.StopOfRoute.loc[i, 'Schedule'])]

    def combine_schedule(self, schedule_main, schedule_other):
        new_schedule = copy.deepcopy(schedule_main)
        if schedule_main != [] and schedule_other != []:
            for day in self.day_list:
                for peak in self.peak_list + self.other_time:
                    new_schedule[(day, peak, 'n')] = (
                        schedule_main[(day, peak, 'n')] + schedule_other[(day, peak, 'n')]
                    )
                    new_schedule[(day, peak, 'st')] = min(
                        schedule_main[(day, peak, 'st')], schedule_other[(day, peak, 'st')]
                    )
                    new_schedule[(day, peak, 'ed')] = max(
                        schedule_main[(day, peak, 'ed')], schedule_other[(day, peak, 'ed')]
                    )
        return new_schedule

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
        for r in self.schdl.Schedule.index:
            self.StopOfRoute.loc[
                (self.StopOfRoute['SubRouteUID'] == 
                    self.schdl.Schedule.loc[r, 'SubRouteUID']) & 
                (self.StopOfRoute['Direction'] == 
                    self.schdl.Schedule.loc[r, 'Direction']),
                'Schedule'
            ] = [copy.deepcopy(self.schdl.Schedule.loc[r, 'bus_schedule'])]

    def get_headway(self, bus_schedule):
        if bus_schedule != []:
            headway = {}
            for group in self.day_group:
                num_day = len(self.day_group[group][1])
                
                for peak in self.peak_list:
                    duration = (
                        sum(
                            (bus_schedule[(day, peak, 'ed')] - 
                            bus_schedule[(day, peak, 'st')]) / timedelta(minutes=1)
                            for day in self.day_group[group][1]
                        )
                    )
                    headway[(group, peak)] = int(duration / 
                        max(sum(bus_schedule[(day, peak, 'n')] 
                            for day in self.day_group[group][1]), num_day)
                    )
                for time in ['all_day', 'AD_nopeak']:
                    duration = (
                        sum(
                            max((bus_schedule[(day, time, 'ed')] - 
                            bus_schedule[(day, time, 'st')]) / timedelta(minutes=1), 240)
                            for day in self.day_group[group][1]
                        )
                    )
                    num_bus = sum(bus_schedule[(day, time, 'n')] for day in self.day_group[group][1])
                    if num_bus < 3 * num_day:
                        headway[(group, time)] = 240
                    else:
                        headway[(group, time)] = int(min(duration / (num_bus - 1), 240))
                    if headway[(group, time)] < 0:
                        headway[(group, time)] = -999
                
                # 離峰處理
                daily_duration = {}
                for day in self.day_list:
                    daily_duration[day] = (
                        bus_schedule[(day, 'offpeak', 'ed')] - 
                        bus_schedule[(day, 'offpeak', 'st')]
                    )
                    for peak in self.peak_list:
                        peak_st = (
                            (bus_schedule[(day, peak, 'id')] - 1) * 
                            self.section_length + datetime(1900, 1, 1, 0, 0)
                        )
                        peak_ed = (
                            (bus_schedule[(day, peak, 'id')] + self.num_peak_section - 1) * 
                            self.section_length + datetime(1900, 1, 1, 0, 0)
                        )
                        if (bus_schedule[(day, 'offpeak', 'ed')] >= peak_ed and
                            bus_schedule[(day, 'offpeak', 'st')] <= peak_st):
                            daily_duration[day] -= (
                                bus_schedule[(day, peak, 'ed')] - 
                                bus_schedule[(day, peak, 'st')]
                            )
                
                duration = sum(
                    max(daily_duration[day] / timedelta(minutes=1), 240)
                    for day in self.day_group[group][1]
                )
                num_bus = sum(bus_schedule[(day, 'offpeak', 'n')] for day in self.day_group[group][1])
                if num_bus < 3 * num_day:
                    headway[(group, 'offpeak')] = 240
                else:
                    headway[(group, 'offpeak')] = int(min(duration / (num_bus - 1), 240))
                if headway[(group, 'offpeak')] < 0:
                    headway[(group, 'offpeak')] = 999
        
        else:
            headway = {}
            for group in self.day_group:
                for peak in self.peak_list + self.other_time:
                    headway[(group, peak)] = 999
        
        return headway

    def output_stop_info(self):
        """輸出公車站牌點位"""
        print('Output stop of {}'.format(self.group_url))
        #判別路線是否經過計畫區域
        self.check_if_stop_in_zone()
        os.makedirs(self.group_url, exist_ok=True)
        #輸出站牌資料
        stop_file = os.path.join('PTX_data', self.group_url, 'bus_stop.csv')
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
        os.makedirs(os.path.join('PTX_data', self.group_url), exist_ok=True)

        #生成檔名：route_list.csv
        list_file = os.path.join('PTX_data', self.group_url, 'route_list.csv')
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
                            '{OperatorName}'.format(OperatorName=ON['OperatorName']['Zh_tw'])
                        )
                        if ON != self.StopOfRoute.Operators[i][-1]:
                            list_out.write('/')
                    list_out.write(',{Direction},{if_pass_zone}\n'.format(
                            Direction=self.StopOfRoute.Direction[i],
                            if_pass_zone=self.StopOfRoute.if_pass_zone[i]
                        )
                    )

                    #生成檔名：SubRouteUID_路線中文名_路線方向.csv
                    file_name = os.path.join(
                        'PTX_data', self.group_url, 
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
        if self.city_name != 'Taichung':
            print('Output schedule of ' + self.group_url)
            #判別路線是否經過計畫區域
            self.check_if_route_pass_zone()
            #建立資料夾
            os.makedirs(os.path.join('PTX_data', self.group_url), exist_ok=True)

            #生成檔名：route_list.csv
            headway_file = os.path.join('PTX_data', self.group_url, 'route_headway.csv')
            #寫入路線清單
            with open(headway_file, 'w', encoding='utf-8') as list_out:
                #寫入停站列表
                #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,有無經過計畫區域
                list_out.write('SubRouteUID,SubRouteName,Headsign,Direction,if_pass_zone')
                for group in self.day_group:
                    for peak in self.peak_list + self.other_time:
                        list_out.write(',{}_{}'.format(group, peak))
                list_out.write('\n')
                for i in self.StopOfRoute.index:
                    if i not in self.drop_route:
                        list_out.write(
                            '{SubRouteUID},{SubRouteName},{Headsign},{Direction},{if_pass_zone}'.format(
                                SubRouteUID=self.StopOfRoute.SubRouteUID[i],
                                SubRouteName=self.StopOfRoute.SubRouteName[i]['Zh_tw'],
                                Headsign=self.StopOfRoute.Headsign[i].replace(' ', '').replace(',', '_'),
                                Direction=self.StopOfRoute.Direction[i],
                                if_pass_zone=self.StopOfRoute.if_pass_zone[i]
                            )
                        )

                        for group in self.day_group:
                            for peak in self.peak_list + self.other_time:
                                list_out.write(',{}'.format(self.StopOfRoute.loc[i, 'Headway'][(group, peak)]))

                        list_out.write('\n')

    def stop_info_str(self, s):
        return '{StopUID},{Lat},{Lon},{StopName},{LocationCityCode}\n'.format(
            StopUID=self.Stop.StopUID[s],
            Lat=self.Stop.StopPosition[s]['PositionLat'],
            Lon=self.Stop.StopPosition[s]['PositionLon'],
            StopName=self.Stop.StopName[s]['Zh_tw'],
            LocationCityCode=str(self.Stop.LocationCityCode[s]).upper()
        )

class Schedule(object):
    """班表處理"""
    def __init__(self, schedule, day_list, peak_list, other_time, peak_bound, peak_length, section_length):
        self.day_list = day_list
        self.peak_list = peak_list
        self.other_time = other_time
        self.peak_bound = peak_bound
        self.peak_length = peak_length

        self.section_length = section_length
        self.num_peak_section = int(self.peak_length / self.section_length)

        self.Schedule = schedule
        self.process_timetable()

    def process_timetable(self):
        self.Schedule['bus_schedule'] = [
            self.new_bus_schedule() for _ in self.Schedule.index
        ]
        for r in self.Schedule.index:
            bus_schedule = {}
            if 'Timetables' in self.Schedule:
                bus_schedule = self.manage_bus_timetable(self.Schedule.Timetables[r])
            elif 'Frequencys' in self.Schedule:
                bus_schedule = self.manage_bus_frequency(self.Schedule.Frequencys[r])

            self.Schedule.loc[r, 'bus_schedule'] = [copy.deepcopy(bus_schedule)]

    def new_bus_schedule(self):
        bus_schedule = {}
        for day in self.day_list:
            bus_schedule[day] = [0 for _ in range(24 * 4)]
            for peak in self.peak_list + self.other_time:
                bus_schedule[(day, peak, 'n')] = 0
                bus_schedule[(day, peak, 'id')] = 0
                bus_schedule[(day, peak, 'st')] = self.peak_bound[peak][0]
                bus_schedule[(day, peak, 'ed')] = self.peak_bound[peak][1]
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

    def calculate_peak(self, bustime_list: list, peak_type: str):
        """在公車班表中(bustime_list)從給定範圍內(self.peak_bound)找最尖峰(peak_type)的一段時間(peak_length)"""
        st_index = int((self.peak_bound[peak_type][0] - datetime(1900, 1, 1, 0, 0)) / self.section_length) + 1
        ed_index = int((self.peak_bound[peak_type][1] - datetime(1900, 1, 1, 0, 0)) / self.section_length) + 1

        bus_sum = [sum(bustime_list[i : i + self.num_peak_section]) for i in range(st_index, ed_index - self.num_peak_section)]
        
        #找最大值位置
        peak_index = 0
        peak_value = 0
        for (i, n) in enumerate(bus_sum):
            if n >= peak_value:
                peak_value = n
                peak_index = i
        
        return st_index + peak_index, peak_value

    def manage_bus_timetable(self, Timetables):
        """檢查班表式資料的班距"""
        bus_schedule = self.new_bus_schedule()
        for BusStopTime in Timetables:
            if 'ServiceDay' in BusStopTime:
                for StopTime in BusStopTime['StopTimes']:
                    for day in self.day_list:
                        if BusStopTime['ServiceDay'][day] != 0:
                            bus_time = (datetime.strptime(StopTime['DepartureTime'], '%H:%M'))
                            bus_schedule[day][int((bus_time - datetime(1900, 1, 1, 0, 0)) / self.section_length)] += 1
                            bus_schedule[(day, 'AD_nopeak', 'st')] = min(
                                bus_schedule[(day, 'AD_nopeak', 'st')], bus_time
                            ) # 首班
                            bus_schedule[(day, 'AD_nopeak', 'ed')] = max(
                                bus_schedule[(day, 'AD_nopeak', 'ed')], bus_time
                            ) # 末班
        #找晨昏峰時間
        for day in self.day_list:
            for peak in self.peak_list:
                bus_schedule[(day, peak, 'id')], bus_schedule[(day, peak, 'n')] = \
                    self.calculate_peak(bus_schedule[day], peak)

        return self.fill_in_st_ed(bus_schedule)

    def manage_bus_frequency(self, Frequencies):
        """檢查班距式資料的班距"""
        bus_schedule = self.new_bus_schedule()
        for BusFrequency in Frequencies:
            if 'ServiceDay' in BusFrequency:
                headway = (
                    (BusFrequency['MinHeadwayMins'] + 
                    BusFrequency['MaxHeadwayMins']) / 2
                )
                start_time = datetime.strptime(BusFrequency['StartTime'], '%H:%M')
                end_time = datetime.strptime(BusFrequency['EndTime'], '%H:%M')

                for day in self.day_list:
                    if BusFrequency['ServiceDay'][day] != 0:
                        #完全包含的區間
                        start_index = math.ceil((start_time - datetime(1900, 1, 1, 0, 0)) / self.section_length)
                        end_index = math.floor((end_time - datetime(1900, 1, 1, 0, 0)) / self.section_length)

                        for i in range(start_index, end_index + 1):
                            bus_schedule[day][i] += round(self.section_length / headway)

                        #剩下的頭尾區間
                        bus_schedule[day][start_index - 1] += round(
                            ((start_index * self.section_legth + datetime(1900, 1, 1, 0, 0)) - start_time) / headway
                        )
                        bus_schedule[day][end_index + 1] += round(
                            (end_time - (end_index * self.section_legth + datetime(1900, 1, 1, 0, 0))) / headway
                        )

                        bus_schedule[(day, 'AD_nopeak', 'st')] = min(
                            bus_schedule[(day, 'AD_nopeak', 'st')], start_time
                        )
                        bus_schedule[(day, 'AD_nopeak', 'ed')] = max(
                            bus_schedule[(day, 'AD_nopeak', 'ed')], end_time
                        )
        #找晨昏峰時間
        for day in self.day_list:
            for peak in self.peak_list:
                bus_schedule[(day, peak, 'id')], bus_schedule[(day, peak, 'n')] = \
                    self.calculate_peak(bus_schedule[day], peak, self.peak_length)

        return self.fill_in_st_ed(bus_schedule)

    def fill_in_st_ed(self, bus_schedule):
        """首末班車在晨昏峰區間內的處理，順便加總班次"""
        for day in self.day_list:
            bus_schedule[(day, 'AD_nopeak', 'n')] = sum(bus_schedule[day])
            bus_schedule[(day, 'offpeak', 'n')] = (
                bus_schedule[(day, 'AD_nopeak', 'n')] -
                bus_schedule[(day, 'morning_peak', 'n')] -
                bus_schedule[(day, 'evening_peak', 'n')]
            )
            bus_schedule[(day, 'all_day', 'n')] = bus_schedule[(day, 'AD_nopeak', 'n')]
            for se in ['st', 'ed']:
                checked = False
                for peak in self.peak_list:
                    peak_st = (
                        (bus_schedule[(day, peak, 'id')] - 1) * 
                        self.section_length + datetime(1900, 1, 1, 0, 0)
                    )
                    peak_ed = (
                        (bus_schedule[(day, peak, 'id')] + self.num_peak_section - 1) * 
                        self.section_length + datetime(1900, 1, 1, 0, 0)
                    )
                    if (bus_schedule[(day, 'AD_nopeak', se)] > peak_st and 
                        bus_schedule[(day, 'AD_nopeak', se)] <= peak_ed and 
                        not checked):
                        bus_schedule[(day, 'all_day', se)] = bus_schedule[(day, peak, se)]
                        bus_schedule[(day, 'offpeak', se)] = bus_schedule[(day, peak, se)]
                        checked = True
                if not checked:
                    bus_schedule[(day, 'all_day', se)] = bus_schedule[(day, 'AD_nopeak', se)]
                    bus_schedule[(day, 'offpeak', se)] = bus_schedule[(day, 'AD_nopeak', se)]
        return bus_schedule

def main():
    app_id = input('Input app_id: ')
    app_key = input('Input app_key: ')
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
        Bus[city].output_schedule()

    Bus['IC'] = BusGroup(
        project_zone, 'InterCity', 
        load_local_data=True, my_auth=a
    )
    Bus['IC'].output_stop_info()
    Bus['IC'].output_route_seq()
    Bus['IC'].output_schedule()

    #輸出全區域車站清單
    print('Output stops in central Taiwan')
    #輸出站牌資料
    stop_file = 'PTX_data/C_TWN/central_taiwan_bus_stop.csv'
    with open(stop_file, 'w', encoding='utf-8') as stop_out:
        stop_out.write('StopUID,PositionLat,PositionLon,StopName,LocationCityCode\n')
        recorded_stop = []
        for city in project_zone + ['IC']:
            for s in Bus[city].Stop.index:
                if Bus[city].Stop.if_pass_zone[s] == 1 and Bus[city].Stop.StopUID[s] not in recorded_stop:
                    recorded_stop.append(Bus[city].Stop.StopUID[s])
                    stop_out.write(Bus[city].stop_info_str(s))
            
    print('Output routes in central Taiwan')
    #輸出路線資料
    stop_file = 'PTX_data/C_TWN/central_taiwan_bus_routes.csv'
    with open(stop_file, 'w', encoding='utf-8') as route_out:
        route_out.write('SubRouteUID,SubRouteName,Headsign,OperatorName,Direction\n')
        for city in project_zone + ['IC']:
            for i in Bus[city].StopOfRoute.index:
                if i not in Bus[city].drop_route and Bus[city].StopOfRoute.if_pass_zone[i] == 1:
                    route_out.write(
                        '{SubRouteUID},{SubRouteName},{Headsign},'.format(
                            SubRouteUID=Bus[city].StopOfRoute.SubRouteUID[i],
                            SubRouteName=Bus[city].StopOfRoute.SubRouteName[i]['Zh_tw'],
                            Headsign=Bus[city].StopOfRoute.Headsign[i].replace(' ', '').replace(',', '_')
                        )
                    )
                    for ON in Bus[city].StopOfRoute.Operators[i]:
                        route_out.write(
                            '{OperatorName}'.format(OperatorName=ON['OperatorName']['Zh_tw'])
                        )
                        if ON != Bus[city].StopOfRoute.Operators[i][-1]:
                            route_out.write('/')
                    route_out.write(',{Direction}\n'.format(
                            Direction=Bus[city].StopOfRoute.Direction[i]
                        )
                    )

if __name__ == '__main__':
    main()
