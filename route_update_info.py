# -*- coding: utf-8 -*-

import os
import pickle

import pandas as pd

class BusRoute(object):
    def __init__(self, routeUID, route_name, if_pass_zone, zone_dir, file_name) -> None:
        self.routeUID = routeUID
        self.route_name = route_name
        self.if_pass_zone = if_pass_zone
        self.file_name = file_name
        self.read_stop_df(zone_dir)
        self.similar_route = None

    def read_stop_df(self, zone_dir):
        # read the stop list of the bus route
        self.stop_df = pd.read_csv(os.path.join(zone_dir, '{}.csv'.format(self.file_name)))
        self.stop_df['stop_seq'] = self.stop_df.apply(lambda row: (row['PositionLat'], row['PositionLon']), axis=1)
        self.stop_count = len(self.stop_df.index)

    def check_similarity(self, other_route: object) -> bool:
        if self.if_pass_zone == 1:
            check_type = {
                '狹義相同站序': False,
                '廣義相同站序': False,
                '相同UID': False,
                '相同路線名': False,
                '站數相同': False,
                '站牌差異個數': self.stop_count,
            }
            check_type['狹義相同站序'] = self.stop_df['stop_seq'].to_list() == other_route.stop_df['stop_seq'].to_list()
            check_type['廣義相同站序'] = check_type['狹義相同站序']
            check_type['相同UID'] = self.routeUID == other_route.routeUID
            check_type['相同路線名'] = self.route_name == other_route.route_name
            check_type['站數相同'] = self.stop_count == other_route.stop_count

            if check_type['狹義相同站序']:
                check_type['站牌差異個數'] = 0
                self.similar_route = {
                    'check_result': check_type, 
                    'check_message': self.result_message(check_type, ''), 
                    'similar_route': other_route
                }
                return True
            
            elif check_type['相同UID'] or check_type['相同路線名']:
                further_result, generally_identical, different_stop_count = self.compare_stop_seq(other_route)
                check_type['廣義相同站序'] = generally_identical
                check_type['站牌差異個數'] = different_stop_count
                
                if (self.similar_route is None or 
                    check_type['站牌差異個數'] < self.similar_route['check_result']['站牌差異個數']):
                    self.similar_route = {
                        'check_result': check_type, 
                        'check_message': self.result_message(check_type, further_result), 
                        'similar_route': other_route
                    }
                
        return False

    def result_message(self, check_type, further_msg):
        msg = '  ['
        for i, m in enumerate(check_type):
            if type(check_type[m]) is bool:
                msg += '{message} {result} '.format(message=m, result='O' if check_type[m] else 'X')
            else:
                msg += '{message} {result} '.format(message=m, result=check_type[m])
            if i < len(check_type) - 1:
                msg += '/'
        msg += ']' + further_msg
        return msg

    def compare_stop_seq(self, other_route: object):
        """compare the difference between two sets of stop sequence"""
        # find the corresponding stop
        new2old = [_ for _ in range(self.stop_count)]
        for i in range(self.stop_count):
            no_result = True
            if i < other_route.stop_count and self.check_proximity(i, other_route, i):
                new2old[i] = i
                no_result = False
            else:
                for j in range(other_route.stop_count):
                    if self.check_proximity(i, other_route, j):
                        new2old[i] = j
                        no_result = False
                        break
            if no_result:
                new2old[i] = -100
        
        # find changed sections
        changed_section = []
        if new2old[0] != 0:
            start_index = -1
        else:
            start_index = 0
        
        for end_index in range(1, self.stop_count):
            if new2old[end_index] - new2old[end_index - 1] == 1:
                if (end_index - 1) - start_index > 1:
                    changed_section.append((max(0, start_index), end_index - 1))
                start_index = end_index
        
        # 延駛、縮短、最後有變動都要另外處理
        if new2old[-1] != other_route.stop_count - 1 or new2old[-1] == -100 or start_index != self.stop_count - 1:
            changed_section.append((max(0, start_index), self.stop_count - 1))
        
        # re-check changed_section
        changed_section = self.check_changed_section(changed_section, new2old, other_route)

        # output message
        output_str = ''
        generally_identical = True
        different_stop_count = 0

        if len(changed_section) > 0:
            generally_identical = False
            # output_str += '\n  新的站序: '
            # output_str += ', '.join(['{:>4d}'.format(i + 1) for i in range(self.stop_count)])
            # output_str += '\n  舊的站序: '
            # output_str += ', '.join(['{:>4d}'.format(i + 1) for i in new2old])

            for i, sec in enumerate(changed_section):
                different_stop_count += sec[1] + 1 - sec[0]
                # 舊區間文字
                output_str += '\n{:>4d})舊區間: '.format(i + 1)
                start_old_stop, end_old_stop = self.get_old_stop_range(new2old[sec[0]], new2old[sec[1]], other_route)
                for old_stop in range(start_old_stop, end_old_stop):
                    output_str += '({StopSequence}/{stop_count}){StopName}[{LocationCityCode}]'.format(
                        StopSequence=other_route.stop_df.loc[old_stop, 'StopSequence'], 
                        stop_count=other_route.stop_count,
                        StopName=other_route.stop_df.loc[old_stop, 'StopName'], 
                        LocationCityCode=other_route.stop_df.loc[old_stop, 'LocationCityCode']
                    )
                    if old_stop != end_old_stop - 1:
                        output_str += ' → '
                
                # 新區間文字
                output_str += '\n{:>4d})新區間: '.format(i + 1)
                for old_stop in range(sec[0], sec[1] + 1):
                    output_str += '({StopSequence}/{stop_count}){StopName}[{LocationCityCode}]'.format(
                        StopSequence=self.stop_df.loc[old_stop, 'StopSequence'], 
                        stop_count=self.stop_count,
                        StopName=self.stop_df.loc[old_stop, 'StopName'], 
                        LocationCityCode=self.stop_df.loc[old_stop, 'LocationCityCode']
                    )
                    if old_stop != sec[1]:
                        output_str += ' → '

        return output_str, generally_identical, different_stop_count

    def get_old_stop_range(self, start_stop, end_stop, other_route: object):
        """return the old stop numbers coresponding to the new stop numbers"""
        if start_stop == -100:
            start_old_stop = 0
        else:
            start_old_stop = start_stop

        if end_stop == -100:
            end_old_stop = other_route.stop_count
        elif end_stop == self.stop_count:
            end_old_stop = other_route.stop_count
        else:
            end_old_stop = end_stop + 1
        
        return start_old_stop, end_old_stop

    def check_changed_section(self, changed_section, new2old, other_route: object):
        """re-check changed_section"""
        new_changed_section = []
        for sec in changed_section:
            start_old_stop, end_old_stop = self.get_old_stop_range(new2old[sec[0]], new2old[sec[1]], other_route)
            
            if (end_old_stop - start_old_stop) == (sec[1] + 1 - sec[0]):
                remove_section = True
                for idx in range(sec[1] + 1 - sec[0]):
                    remove_section &= self.check_proximity(sec[0] + idx, other_route, start_old_stop + idx)
                if not remove_section:
                    new_changed_section.append(sec)
            else:
                new_changed_section.append(sec)
        return new_changed_section
    
    def check_proximity(self, i: int, other_route: object, j: int) -> bool:
        """Two stops with same coordinates, StopUID are declared to be the same."""
        return (
            self.stop_df.loc[i, 'stop_seq'] == other_route.stop_df.loc[j, 'stop_seq'] or
            self.stop_df.loc[i, 'StopUID'] == other_route.stop_df.loc[j, 'StopUID'] or
            self.stop_df.loc[i, 'StopName'] == other_route.stop_df.loc[j, 'StopName']
        )

def progress_bar(bar_name: str, current_num: int, total_num: int):
    """ Display the progress bar if the result is printed to the text file. """
    print(
        '\r[{:<50}] {}: {}/{}'.format(
            '=' * int(current_num / (2 * total_num) * 100), 
            bar_name, current_num, total_num
        ), 
            end=''
    )
    if current_num == total_num:
        print()

def main():
    #拼音 -> 中文
    City_zhtw2en = {
        'Taipei': '臺北市', 'NewTaipei': '新北市', 'Taoyuan': '桃園市', 'Taichung': '臺中市', \
        'Tainan': '臺南市', 'Kaohsiung': '高雄市', 'Keelung': '基隆市', 'Hsinchu': '新竹市', \
        'HsinchuCounty': '新竹縣', 'MiaoliCounty': '苗栗縣', 'ChanghuaCounty': '彰化縣', \
        'NantouCounty': '南投縣', 'YunlinCounty': '雲林縣', 'ChiayiCounty': '嘉義縣', \
        'Chiayi': '嘉義市', 'PingtungCounty': '屏東縣', 'YilanCounty': '宜蘭縣', \
        'HualienCounty': '花蓮縣', 'TaitungCounty': '臺東縣', 'KinmenCounty': '金門縣', \
        'PenghuCounty': '澎湖縣', 'LienchiangCounty': '連江縣'
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
        'TNN': {'zhtw': '臺南市', 'en': 'Tainan'}, 
        'CHA': {'zhtw': '彰化縣', 'en': 'ChanghuaCounty'}, 
        'NWT': {'zhtw': '新北市', 'en': 'NewTaipei'}, 
        'TPE': {'zhtw': '臺北市', 'en': 'Taipei'}, 
        'TTT': {'zhtw': '臺東縣', 'en': 'TaitungCounty'}, 
        'KEE': {'zhtw': '基隆市', 'en': 'Keelung'}, 
        'HUA': {'zhtw': '花蓮縣', 'en': 'HualienCounty'}, 
        'KHH': {'zhtw': '高雄市', 'en': 'Kaohsiung'}, 
        'PEN': {'zhtw': '澎湖縣', 'en': 'PenghuCounty'}, 
        'KIN': {'zhtw': '金門縣', 'en': 'KinmenCounty'}, 
        'LIE': {'zhtw': '連江縣', 'en': 'LienchiangCounty'},
    }
    project_zone = ['MIA', 'TXG', 'CHA', 'NAN', 'YUN']

    data_type = ['outdated', 'latest']
    data_date = {}
    data_dir = {}
    routes_list = {}
    for d in data_type:
        while True:
            data_date[d] = input('Input download date of the {} data: '.format(d))
            data_dir[d] = os.path.join('PTX_data', 'CSV_{}'.format(data_date[d]))
            if os.path.isdir(data_dir[d]):
                break
            else:
                print('This date is not valid.')
        
        routes_list[d] = {'City': {}, 'InterCity': []}
    
    # city
    for zone in project_zone:
        zone_name = City_map[zone]['en']
        for d in data_type:
            routes_list[d]['City'][zone_name] = []
            route_df = pd.read_csv(os.path.join(data_dir[d], 'City', zone_name, 'route_list.csv'))
            for i in route_df.index:
                routeUID = '{SubRouteUID}_{Direction}'.format(
                    SubRouteUID=route_df.loc[i, 'SubRouteUID'],
                    Direction=route_df.loc[i, 'Direction']
                )
                route_name = '{SubRouteName}_{Direction}'.format(
                    SubRouteName=route_df.loc[i, 'SubRouteName'],
                    Direction=route_df.loc[i, 'Direction']
                )
                file_name = '{SubRouteUID}_{SubRouteName}_{Direction}'.format(
                    SubRouteUID=route_df.loc[i, 'SubRouteUID'],
                    SubRouteName=route_df.loc[i, 'SubRouteName'],
                    Direction=route_df.loc[i, 'Direction']
                )
                if_pass_zone = route_df.loc[i, 'if_pass_zone']
                routes_list[d]['City'][zone_name].append(
                    BusRoute(
                        routeUID,
                        route_name,
                        if_pass_zone, 
                        os.path.join(data_dir[d], 'City', zone_name),
                        file_name
                    )
                )
                progress_bar('[Import] {} data: City/{}'.format(d, zone_name), i + 1, len(route_df.index))

    # intercity
    for d in data_type:
        routes_list[d]['InterCity'] = []
        route_df = pd.read_csv(os.path.join(data_dir[d], 'InterCity', 'route_list.csv'))
        for i in route_df.index:
            routeUID = '{SubRouteUID}_{Direction}'.format(
                SubRouteUID=route_df.loc[i, 'SubRouteUID'],
                Direction=route_df.loc[i, 'Direction']
            )
            route_name = '{SubRouteName}_{Direction}'.format(
                SubRouteName=route_df.loc[i, 'SubRouteName'],
                Direction=route_df.loc[i, 'Direction']
            )
            file_name = '{SubRouteUID}_{SubRouteName}_{Direction}'.format(
                SubRouteUID=route_df.loc[i, 'SubRouteUID'],
                SubRouteName=route_df.loc[i, 'SubRouteName'],
                Direction=route_df.loc[i, 'Direction']
            )
            if_pass_zone = route_df.loc[i, 'if_pass_zone']
            routes_list[d]['InterCity'].append(
                BusRoute(
                    routeUID,
                    route_name,
                    if_pass_zone, 
                    os.path.join(data_dir[d], 'InterCity'),
                    file_name
                )
            )
            progress_bar('[Import] {} data: InterCity'.format(d), i + 1, len(route_df.index))
    
    # compare
    # city
    new_routes = {'City': {}, 'InterCity': []}
    for zone in project_zone:
        zone_name = City_map[zone]['en']
        new_routes['City'][zone_name] = []
        i = 0
        for route in routes_list['latest']['City'][zone_name]:
            i += 1
            for old_route in routes_list['outdated']['City'][zone_name]:
                result = route.check_similarity(old_route)
                if result:
                    break
            progress_bar('[Process] City/{}'.format(zone_name), i, len(routes_list['latest']['City'][zone_name]))
    
    # intercity
    i = 0
    for route in routes_list['latest']['InterCity']:
        i += 1
        for old_route in routes_list['outdated']['InterCity']:
            result = route.check_similarity(old_route)
            if result:
                break
        progress_bar('[Process] InterCity', i, len(routes_list['latest']['InterCity']))

    # summarize comparing result
    summarize = {
        'file_name': [], 'other_file_name': [], '狹義相同站序': [], '廣義相同站序': [], 
        '相同UID': [], '相同路線名': [], '站數相同': [], '站牌差異個數': []
    }
    result_fields = [
        '狹義相同站序', '廣義相同站序', '相同UID', '相同路線名', '站數相同', '站牌差異個數'
    ]
    for zone in project_zone:
        for r in routes_list['latest']['City'][City_map[zone]['en']]:
            if r.similar_route is not None:
                summarize['file_name'].append(r.file_name)
                summarize['other_file_name'].append(r.similar_route['similar_route'].file_name)
                for f in result_fields:
                    if type(r.similar_route['check_result'][f]) is bool:
                        summarize[f].append(1 if r.similar_route['check_result'][f] else 0)
                    else:
                        summarize[f].append(r.similar_route['check_result'][f])
            elif r.if_pass_zone == 1:
                summarize['file_name'].append(r.file_name)
                summarize['other_file_name'].append('無對應路線')
                for f in result_fields:
                    summarize[f].append(-1)
    
    for r in routes_list['latest']['InterCity']:
        if r.similar_route is not None:
            summarize['file_name'].append(r.file_name)
            summarize['other_file_name'].append(r.similar_route['similar_route'].file_name)
            for f in result_fields:
                if type(r.similar_route['check_result'][f]) is bool:
                    summarize[f].append(1 if r.similar_route['check_result'][f] else 0)
                else:
                    summarize[f].append(r.similar_route['check_result'][f])
        elif r.if_pass_zone == 1:
            summarize['file_name'].append(r.file_name)
            summarize['other_file_name'].append('無對應路線')
            for f in result_fields:
                summarize[f].append(-1)

    summarize_df = pd.DataFrame.from_dict(summarize)
    summarize_df.to_csv('PTX_data_comparison.csv')

    # output detailed information of the difference
    result_file = 'check_difference.txt'
    with open(result_file, 'w', encoding='utf-8') as result_out:
        for zone in project_zone:
            for r in routes_list['latest']['City'][City_map[zone]['en']]:
                if r.similar_route is not None:
                    if not r.similar_route['check_result']['廣義相同站序']:
                        result_out.write('[{}公車] {} ← {}\n{}\n\n'.format(
                            City_map[zone]['zhtw'], r.routeUID, r.similar_route['similar_route'].routeUID, r.similar_route['check_message']
                        ))
                elif r.if_pass_zone == 1:
                    result_out.write('[{}公車] {} ← 無對應路線\n\n'.format(City_map[zone]['zhtw'], r.routeUID))
        
        for r in routes_list['latest']['InterCity']:
            if r.similar_route is not None:
                if not r.similar_route['check_result']['廣義相同站序']:
                    result_out.write('[公路客運] {} ← {}\n{}\n\n'.format(
                        r.routeUID, r.similar_route['similar_route'].routeUID, r.similar_route['check_message']
                    ))
            elif r.if_pass_zone == 1:
                result_out.write('[公路客運] {} ← 無對應路線\n\n'.format(r.routeUID))

if __name__ == '__main__':
     main()