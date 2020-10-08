# -*- coding: utf-8 -*-

import base64
import copy
import hmac
import os
import pickle
import shutil
from datetime import datetime, timedelta
from hashlib import sha1
from pprint import pprint
from time import mktime
from wsgiref.handlers import format_date_time

import pandas as pd
from pandas.tseries.offsets import Second
from requests import request


class BusGroup():
    """
    project_zone: 計畫區域\n
    group_type: City or InterCity\n
    city_name: 縣市名稱，公路客運則為''\n
    load_local_data: 是否要載入本地儲存的公車資料
    """
    def __init__(self):
        self.day_list = ['weekday', 'weekend']
        self.peak_list = ['morning_peak', 'evening_peak']
        self.other_time = ['offpeak', 'all_day', 'AD_nopeak']
        self.peak_bound = {
            'morning_peak': [datetime(1900, 1, 1, 6, 0), datetime(1900, 1, 1, 8, 0)],
            'evening_peak': [datetime(1900, 1, 1, 16, 0), datetime(1900, 1, 1, 18, 0)]
        }
        for time in self.other_time:
            self.peak_bound[time] = [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)]
        self.day_group = {
            'weekend': ['all', ['weekend']],
            'weekday': ['peak', ['weekday']],
            'weekday_2': ['peak', ['weekday']]
        }

        #讀取公車路線班表資料
        self.StopOfRoute = pd.read_csv(os.path.join(
            r'D:\Users\63707\Documents\python3',
            r'bus_route\PTX_data\City\Taichung', 
            'route_list.csv'
        ))
        self.Schedule = None
        self.schdl = Schedule(self.StopOfRoute, self.day_list, self.peak_list, self.other_time, self.peak_bound)
        self.process_timetable()
        self.calculate_headway()

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
                        #班次數要減一...
                        headway[(group, time)] = int(min(duration / (num_bus - 1), 240))
                    if headway[(group, time)] < 0:
                        headway[(group, time)] = 999
                
                # 離峰處理
                daily_duration = {}
                for day in self.day_list:
                    daily_duration[day] = (
                        bus_schedule[(day, 'offpeak', 'ed')] - bus_schedule[(day, 'offpeak', 'st')]
                    )
                    for peak in self.peak_list:
                        if (bus_schedule[(day, 'offpeak', 'ed')] >= bus_schedule[(day, peak, 'ed')] and
                            bus_schedule[(day, 'offpeak', 'st')] <= bus_schedule[(day, peak, 'st')]):
                            daily_duration[day] -= (
                                bus_schedule[(day, peak, 'ed')] - bus_schedule[(day, peak, 'st')]
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

    def output_schedule(self):
        """輸出公車班表"""
        print('Output schedule')

        #生成檔名：route_headway.csv
        headway_file = 'route_headway.csv'
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
                list_out.write(
                    '{SubRouteUID},{SubRouteName},{Headsign},{Direction},{if_pass_zone}'.format(
                        SubRouteUID=self.StopOfRoute.loc[i, 'SubRouteUID'],
                        SubRouteName=self.StopOfRoute.loc[i, 'SubRouteName'],
                        Headsign=self.StopOfRoute.loc[i, 'Headsign'],
                        Direction=self.StopOfRoute.loc[i, 'Direction'],
                        if_pass_zone=self.StopOfRoute.loc[i, 'if_pass_zone']
                    )
                )
                for group in self.day_group:
                    for peak in self.peak_list + self.other_time:
                        list_out.write(',{}'.format(self.StopOfRoute.loc[i, 'Headway'][(group, peak)]))

                list_out.write('\n')

class Schedule(object):
    """班表處理"""
    def __init__(self, StopOfRoute: pd.DataFrame, day_list, peak_list, other_time, peak_bound):
        self.day_list = day_list
        self.peak_list = peak_list
        self.other_time = other_time
        self.peak_bound = peak_bound

        self.Schedule = copy.deepcopy(StopOfRoute)
        self.Schedule['Timetables'] = [{day: '' for day in self.day_list} for _ in self.Schedule.index]
        
        for i in self.Schedule.index:
            route_name = '{}_{}_{}'.format(
                self.Schedule.loc[i, 'SubRouteUID'], 
                self.Schedule.loc[i, 'SubRouteName'], 
                self.Schedule.loc[i, 'Direction']
            )
            for tt_day in self.day_list:
                self.Schedule.loc[i, 'Timetables'][tt_day] = self.read_timetable_text(tt_day, route_name)

        self.process_timetable()

    def read_timetable_text(self, tt_day, route_name):
        weekend_filename = 'TXG_bus_timetable_{}/{}.txt'.format(tt_day, route_name)
        with open(weekend_filename, 'r') as tt:
            timetable = tt.read()
        timetable = timetable.replace(' ', '')
        return timetable.split(',')

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
            for peak in self.peak_list + self.other_time:
                bus_schedule[(day, peak, 'n')] = 0
                bus_schedule[(day, peak, 'st')] = self.peak_bound[peak][0]
                bus_schedule[(day, peak, 'ed')] = self.peak_bound[peak][1]
        return bus_schedule

    def check_bus_peak(self, stop_time):
        """檢查公車是晨峰昏峰還是離峰"""
        bus_time = datetime.strptime(stop_time, '%H:%M')
        if bus_time > self.peak_bound['morning_peak'][0] and bus_time < self.peak_bound['morning_peak'][1]:
            return 'morning_peak'
        elif bus_time > self.peak_bound['evening_peak'][0] and bus_time < self.peak_bound['evening_peak'][1]:
            return 'evening_peak'
        else:
            return 'offpeak'

    def manage_bus_timetable(self, Timetables):
        """檢查班表式資料的班距"""
        bus_schedule = self.new_bus_schedule()
        for day in self.day_list:
            for stop_time in Timetables[day]:
                if stop_time != '':
                    bus_schedule[(day, self.check_bus_peak(stop_time), 'n')] += 1
                    bus_schedule[(day, 'AD_nopeak', 'st')] = min(
                        bus_schedule[(day, 'AD_nopeak', 'st')], 
                        datetime.strptime(stop_time, '%H:%M')
                    ) # 首班
                    bus_schedule[(day, 'AD_nopeak', 'ed')] = max(
                        bus_schedule[(day, 'AD_nopeak', 'ed')], 
                        datetime.strptime(stop_time, '%H:%M')
                    ) # 末班
        
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

                duration = {}
                for peak in self.peak_list:
                    duration[peak] = max(
                        0, 
                        min(self.peak_bound[peak][1], end_time) - 
                        max(self.peak_bound[peak][0], start_time)
                    )
                duration['offpeak'] = (
                    end_time - start_time - 
                    sum(duration[peak] for peak in self.peak_list)
                )

                for day in self.day_list:
                    if BusFrequency['ServiceDay'][day] != 0:
                        for peak in self.peak_list + ['offpeak']:
                            bus_schedule[(day, peak, 'n')] += (
                                (duration[peak] / timedelta(minutes=1)) / headway
                            )
                        bus_schedule[(day, 'AD_nopeak', 'st')] = min(
                            bus_schedule[(day, 'AD_nopeak', 'st')], start_time
                        )
                        bus_schedule[(day, 'AD_nopeak', 'ed')] = max(
                            bus_schedule[(day, 'AD_nopeak', 'ed')], end_time
                        )

        return self.fill_in_st_ed(bus_schedule)

    def fill_in_st_ed(self, bus_schedule):
        """首末班車在晨昏峰區間內的處理，順便加總班次"""
        for day in self.day_list:
            bus_schedule[(day, 'AD_nopeak', 'n')] = (
                bus_schedule[(day, 'morning_peak', 'n')] +
                bus_schedule[(day, 'evening_peak', 'n')] +
                bus_schedule[(day, 'offpeak', 'n')]
            )
            bus_schedule[(day, 'all_day', 'n')] = bus_schedule[(day, 'AD_nopeak', 'n')]
            for se in ['st', 'ed']:
                checked = False
                for peak in self.peak_list:
                    if (bus_schedule[(day, 'AD_nopeak', se)] >= bus_schedule[(day, peak, 'st')] and 
                        bus_schedule[(day, 'AD_nopeak', se)] <= bus_schedule[(day, peak, 'ed')] and 
                        not checked):
                        bus_schedule[(day, 'all_day', se)] = bus_schedule[(day, peak, se)]
                        bus_schedule[(day, 'offpeak', se)] = bus_schedule[(day, peak, se)]
                        checked = True
                if not checked:
                    bus_schedule[(day, 'all_day', se)] = bus_schedule[(day, 'AD_nopeak', se)]
                    bus_schedule[(day, 'offpeak', se)] = bus_schedule[(day, 'AD_nopeak', se)]
        return bus_schedule

def main():
    TXG_bus = BusGroup()
    TXG_bus.output_schedule()

if __name__ == '__main__':
    main()
