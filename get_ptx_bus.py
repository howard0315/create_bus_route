# -*- coding: utf-8 -*-

import os
import shutil
from datetime import datetime, timedelta

from processPTXbus.Schedule import Schedule
from processPTXbus.Headway import Headway
from processPTXbus.ReadPTX import ReadPTX
from processPTXbus.InitializePTXapi import InitializePTXapi, PTXGeoCode


class BusGroup():
    """
    project_zone: 計畫區域\n
    group_type: City or InterCity\n
    city_name: 縣市名稱，公路客運則為''\n
    """
    def __init__(self, ptx_setup: InitializePTXapi, project_zone, group_type, city_name=''):
        self.config = {
            'day_list': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
            'peak_list': ['morning_peak', 'evening_peak'],
            'other_time': ['offpeak', 'all_day'],
            'peak_bound': {
                'morning_peak': [datetime(1900, 1, 1, 5, 30), datetime(1900, 1, 1, 10, 30)],
                'evening_peak': [datetime(1900, 1, 1, 15, 30), datetime(1900, 1, 1, 20, 30)],
                'offpeak': [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)],
                'all_day': [datetime(1900, 1, 1, 23, 59), datetime(1900, 1, 1, 0, 1)],
            },
            'peak_length': timedelta(hours=2),
            'section_length': timedelta(minutes=15),
            'day_group': {
                'weekend': ['all', ['Saturday', 'Sunday']],
                'weekday': ['peak', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']],
                'weekday_2': ['peak', ['Tuesday', 'Wednesday', 'Thursday']]
            },
        }
        self.headway = Headway(self.config)
        self.project_zone = project_zone
        self.update_date = ptx_setup.update_date
        self.drop_route = []
        self.load_Schedule = False
        self.load_Shape = False
        self.data_processed = False
        
        self.set_group_name(group_type, city_name)
        print('\nInitialize {}'.format(self.group_name))
        self.ptx_reader = ReadPTX(ptx_setup, 2, 'Bus', self.group_name)

    def process_data(self, load_Schedule=False, load_Shape=False):
        self.load_Schedule = load_Schedule
        self.load_Shape = load_Shape
        #讀取公車路線資料
        self.Route = self.ptx_reader.load_data('Route')
        #讀取公車站牌資料
        #站牌(stop): 站牌桿實際位置; 站位(station): 同一個站名聚合在一個點位
        self.Stop = self.ptx_reader.load_data('Stop')
        #讀取公車路線站序資料
        self.StopOfRoute = self.ptx_reader.load_data('StopOfRoute')
        self.modify_StopOfRoute()
        #統整不同業者的公路客運路線
        self.aggregate_bus_route()
        #讀取公車路線班表資料
        if self.city_name == 'Taichung' or self.city_name == 'Taoyuan':
            self.load_Schedule = False
        if self.load_Schedule:
            self.schedule = Schedule(self.config, schedule=self.ptx_reader.load_data('Schedule'))
            self.schedule.process_timetable()
            self.StopOfRoute = self.schedule.process_StopOfRoute(self.StopOfRoute)
            self.StopOfRoute = self.headway.process_StopOfRoute(self.StopOfRoute)
        #讀取公車線型資料
        if self.load_Shape:
            self.Shape = self.ptx_reader.load_data('Shape')
            self.shape_to_routes()
        #確認已經完成資料載入
        self.data_processed = True
        
    def set_group_name(self, group_type, city_name):
        """設定網址中的區域名稱: City/{City} or Intercity"""
        self.group_type = group_type
        self.city_name = city_name
        if self.city_name == '':
            self.group_name = self.group_type
        else:
            self.group_name = os.path.join(self.group_type, self.city_name)

    def modify_StopOfRoute(self):
        """修改StopOfRoute的DataFrame，以加上起終點文字"""
        Headsign = ['' for _ in self.StopOfRoute.index]
        for i in self.StopOfRoute.index:
            route = self.Route[self.Route['RouteUID'] == self.StopOfRoute.RouteUID[i]]
            subroute_list = route.SubRoutes.tolist()[0]
            for j in subroute_list:
                if j['SubRouteUID'] == self.StopOfRoute.SubRouteUID[i]: 
                    if 'Headsign' in j:
                        Headsign[i] = j['Headsign']
                    else:
                        Headsign[i] = '{}-{}'.format(route.DepartureStopNameZh, route.DestinationStopNameZh)
                    break
        self.StopOfRoute['Headsign'] = Headsign
        self.StopOfRoute['Schedule'] = [[] for _ in self.StopOfRoute.index]
        self.StopOfRoute['Headway'] = [[] for _ in self.StopOfRoute.index]
        self.StopOfRoute['WithShape'] = 0
        self.StopOfRoute['Shape'] = ['' for _ in self.StopOfRoute.index]

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

    def shape_to_routes(self):
        """把Shape塞進StopOfRoutes裡面"""
        if 'SubRouteUID' in self.Shape.columns:
            compare_field = 'SubRouteUID'
        else:
            compare_field = 'RouteUID'
        
        for r in self.StopOfRoute.index:
            condition = (self.Shape[compare_field] == self.StopOfRoute.loc[r, compare_field])
            if len(self.Shape[condition].index) > 1:
                condition &= (self.Shape['Direction'] == self.StopOfRoute.loc[r, 'Direction'])
            if condition.any():
                self.StopOfRoute.loc[r, 'WithShape'] = 1
                self.StopOfRoute.loc[r, 'Shape'] = self.Shape[condition]['Geometry'].to_list()[0]

    def output_stop_info(self):
        """輸出公車站牌點位"""
        if self.data_processed:
            print('Output stop of {}'.format(self.group_name))
            #判別路線是否經過計畫區域
            self.check_if_stop_in_zone()
            #輸出站牌資料
            stop_file = os.path.join(self.ptx_reader.csv_dir, 'bus_stop.csv')
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
        else:
            print('Data has not been processed.')
            
    def output_route_seq(self):
        """輸出公車路線資訊與站牌序列"""
        if self.data_processed:
            print('Output route of ' + self.group_name)
            #判別路線是否經過計畫區域
            self.check_if_route_pass_zone()

            #生成檔名：route_list.csv
            list_file = os.path.join(self.ptx_reader.csv_dir, 'route_list.csv')
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
                        for on in self.StopOfRoute.Operators[i]:
                            list_out.write('{OperatorName}'.format(OperatorName=on['OperatorName']['Zh_tw']))
                            if on != self.StopOfRoute.Operators[i][-1]:
                                list_out.write('/')
                        list_out.write(
                            ',{Direction},{if_pass_zone}\n'.format(
                                Direction=self.StopOfRoute.Direction[i],
                                if_pass_zone=self.StopOfRoute.if_pass_zone[i]
                            )
                        )

                        #生成檔名：SubRouteUID_路線中文名_路線方向.csv
                        file_name = os.path.join(
                            self.ptx_reader.csv_dir, 
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
        else:
            print('Data has not been processed.')

    def output_schedule(self):
        """輸出公車班表"""
        if self.data_processed:
            if self.load_Schedule:
                print('Output schedule of ' + self.group_name)
                #判別路線是否經過計畫區域
                self.check_if_route_pass_zone()

                #生成檔名：route_list.csv
                headway_file = os.path.join(self.ptx_reader.csv_dir, 'route_headway.csv')
                #寫入路線清單
                with open(headway_file, 'w', encoding='utf-8') as list_out:
                    #寫入停站列表
                    #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,有無經過計畫區域
                    list_out.write('SubRouteUID,SubRouteName,Headsign,Direction,if_pass_zone')
                    for group in self.config['day_group']:
                        for peak in self.config['peak_list'] + self.config['other_time']:
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

                            for group in self.config['day_group']:
                                for peak in self.config['peak_list'] + self.config['other_time']:
                                    list_out.write(',{}'.format(self.StopOfRoute.loc[i, 'Headway'][(group, peak)]))

                            list_out.write('\n')
            else:
                headway_src = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'get_TXG_bus_schedule', 'route_headway_{}'.format(self.update_date)
                )
                headway_file = os.path.join(self.ptx_reader.csv_dir, 'route_headway.csv')
                if os.path.isfile(headway_src):
                    shutil.copy2(headway_src, headway_file)
        else:
            print('Data has not been processed.')

    def output_shape(self):
        if self.load_Shape:
            print('Output shape of ' + self.group_name)
            #生成檔名：route_list.csv
            list_file = os.path.join(self.ptx_reader.csv_dir, 'shape_list.csv')
            #寫入路線清單
            with open(list_file, 'w', encoding='utf-8') as list_out:
                #寫入停站列表
                #各欄位為: 附屬路線唯一識別代碼,附屬路線名稱,車頭描述,營運業者,去返程,線型
                list_out.write(
                    'SubRouteUID,SubRouteName,Headsign,OperatorName,Direction,WithShape,Shape\n'
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
                        for on in self.StopOfRoute.Operators[i]:
                            list_out.write('{OperatorName}'.format(OperatorName=on['OperatorName']['Zh_tw']))
                            if on != self.StopOfRoute.Operators[i][-1]:
                                list_out.write('/')
                        list_out.write(
                            ',{Direction},{WithShape},"{Shape}"\n'.format(
                                Direction=self.StopOfRoute.Direction[i],
                                WithShape=self.StopOfRoute.WithShape[i],
                                Shape=self.StopOfRoute.Shape[i]
                            )
                        )

    def stop_info_str(self, s):
        if self.data_processed:
            return '{StopUID},{Lat},{Lon},{StopName},{LocationCityCode}\n'.format(
                StopUID=self.Stop.StopUID[s],
                Lat=self.Stop.StopPosition[s]['PositionLat'],
                Lon=self.Stop.StopPosition[s]['PositionLon'],
                StopName=self.Stop.StopName[s]['Zh_tw'],
                LocationCityCode=str(self.Stop.LocationCityCode[s]).upper()
            )
        else:
            print('Data has not been processed.')
            return ''
    
    def route_info_str(self, r):
        if self.data_processed:
            output_str = '{SubRouteUID},{SubRouteName},{Headsign},'.format(
                SubRouteUID=self.StopOfRoute.SubRouteUID[r],
                SubRouteName=self.StopOfRoute.SubRouteName[r]['Zh_tw'],
                Headsign=self.StopOfRoute.Headsign[r].replace(' ', '').replace(',', '_')
            )
            for on in self.StopOfRoute.Operators[r]:
                output_str += '{OperatorName}'.format(OperatorName=on['OperatorName']['Zh_tw'])
                if on != self.StopOfRoute.Operators[r][-1]:
                    output_str += '/'
            output_str += ',{Direction}\n'.format(Direction=self.StopOfRoute.Direction[r])
            return output_str
        else:
            print('Data has not been processed.')
            return ''

def main():
    ptx_setup = InitializePTXapi()

    load_schedule = {
        'HSZ': True, 'TXG': False, 'HSQ': True, 'TAO': True, 'MIA': True, 
        'NAN': True, 'CYI': True, 'CYQ': True, 'YUN': True, 'PIF': True, 
        'ILA': True, 'TNN': True, 'CHA': True, 'NWT': True, 'TPE': True, 
        'TTT': True, 'KEE': True, 'HUA': True, 'KHH': False, 'PEN': True, 
        'KIN': True, 'LIE': False,
    }

    if ptx_setup.update_date_dt > datetime(year=2021, month=4, day=1):
        load_shape = {
            'HSZ': True, 'TXG': True, 'HSQ': True, 'TAO': True, 'MIA': True, 
            'NAN': True, 'CYI': True, 'CYQ': True, 'YUN': True, 'PIF': True, 
            'ILA': True, 'TNN': True, 'CHA': True, 'NWT': True, 'TPE': True, 
            'TTT': True, 'KEE': True, 'HUA': True, 'KHH': True, 'PEN': True, 
            'KIN': True, 'LIE': False,
        }
        load_shape_IC = True
    else:
        load_shape = {
            'HSZ': False, 'TXG': False, 'HSQ': False, 'TAO': False, 'MIA': False, 
            'NAN': False, 'CYI': False, 'CYQ': False, 'YUN': False, 'PIF': False, 
            'ILA': False, 'TNN': False, 'CHA': False, 'NWT': False, 'TPE': False, 
            'TTT': False, 'KEE': False, 'HUA': False, 'KHH': False, 'PEN': False, 
            'KIN': False, 'LIE': False,
        }
        load_shape_IC = False

    #計畫區域縣市代碼
    project_zone = ['MIA', 'TXG', 'CHA', 'NAN', 'YUN']

    Bus = {}
    for city in project_zone:
        Bus[city] = BusGroup(ptx_setup, project_zone, 'City', PTXGeoCode.City_map[city]['en'])
        Bus[city].process_data(load_Schedule=load_schedule[city], load_Shape=load_shape[city])
        Bus[city].output_stop_info()
        Bus[city].output_route_seq()
        Bus[city].output_schedule()
        Bus[city].output_shape()

    Bus['IC'] = BusGroup(ptx_setup, project_zone, 'InterCity')
    Bus['IC'].process_data(load_Schedule=True, load_Shape=load_shape_IC)
    Bus['IC'].output_stop_info()
    Bus['IC'].output_route_seq()
    Bus['IC'].output_schedule()
    Bus['IC'].output_shape()

    #輸出全區域車站清單
    c_twn_dir = os.path.join(ptx_setup.ptx_data_dir, 'CSV_{}'.format(ptx_setup.update_date), 'C_TWN')
    os.makedirs(c_twn_dir, exist_ok=True)
    #輸出站牌資料
    print('Output stops in central Taiwan')
    stop_file = os.path.join(c_twn_dir, 'central_taiwan_bus_stop.csv')
    with open(stop_file, 'w', encoding='utf-8') as stop_out:
        stop_out.write('StopUID,PositionLat,PositionLon,StopName,LocationCityCode\n')
        recorded_stop = []
        for city in project_zone + ['IC']:
            for s in Bus[city].Stop.index:
                if Bus[city].Stop.if_pass_zone[s] == 1 and Bus[city].Stop.StopUID[s] not in recorded_stop:
                    recorded_stop.append(Bus[city].Stop.StopUID[s])
                    stop_out.write(Bus[city].stop_info_str(s))
    
    #輸出路線資料
    print('Output routes in central Taiwan')
    route_file = os.path.join(c_twn_dir, 'central_taiwan_bus_routes.csv')
    with open(route_file, 'w', encoding='utf-8') as route_out:
        route_out.write('SubRouteUID,SubRouteName,Headsign,OperatorName,Direction\n')
        for city in project_zone + ['IC']:
            for i in Bus[city].StopOfRoute.index:
                if i not in Bus[city].drop_route and Bus[city].StopOfRoute.if_pass_zone[i] == 1:
                    route_out.write(Bus[city].route_info_str(i))

if __name__ == '__main__':
    main()
