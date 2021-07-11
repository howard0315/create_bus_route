# -*- coding: utf-8 -*-

import os
from pathlib import Path

import pandas as pd

zone_text = {
    'TXG': '臺中公車',
    'MIA': '苗栗公車',
    'CHA': '彰化公車',
    'NAN': '南投公車',
    'YUN': '雲林公車',
    'THB': '公路&國道客運'
}

def get_line_Ns(use_setting='N', folder_option=None, folder_name=None, line_option=None, list_name=None):
    line_Ns = {}

    while use_setting.upper() == 'N':
        folder_option = input(
            '請問要轉換單一檔案還是資料夾內的檔案呢？\n'
            '1 = 單一檔案\n'
            '2 = 資料夾內的檔案\n'
            '請輸入1或2：')
        if folder_option == '1' or folder_option == '2':
            break
        else:
            print('錯誤，輸入值不是1或2')

    if folder_option == '1':
        while True:
            file_name = input('請輸入公車路線資料檔名(包含副檔名, *.txt)：')
            if os.path.isfile(file_name):
                break
            else:
                print('無此檔案')
        line_Ns[Path(file_name).stem] = load(file_name)
    
    elif folder_option == '2':
        while use_setting.upper() == 'N':
            folder_name = input('請輸入資料夾路徑：')
            if os.path.isdir(folder_name):
                break
            else:
                print('無此資料夾')

        while use_setting.upper() == 'N':
            line_option = input(
                '請問要讀取全部還是部份路線呢？\n'
                '1 = 全部路線\n'
                '2 = 部分路線(只能處理一行一個編號的txt檔)\n'
                '請輸入1或2：'
            )
            if line_option == '1' or line_option == '2':
                break
            else:
                print('錯誤，輸入值不是1或2')

        if line_option == '2':
            while use_setting.upper() == 'N':
                list_name = input('請輸入欲整合路線列表的路徑(包含副檔名, *.txt)：')
                if os.path.isfile(list_name):
                    if list_name.endswith('txt'):
                        break
                    else:
                        print('只能讀txt檔')
                else:
                    print('無此檔案')
            
            with open(list_name, 'r', encoding = "UTF-8") as list_file:
                list_str = list_file.read()
                
            output_list = list_str.split('\n')
        
            count = 0
            num_file = len(os.listdir(folder_name))
            for f in os.listdir(folder_name):
                count += 1
                if Path(f).stem in output_list:
                    output_list.remove(Path(f).stem)
                    line_Ns[Path(f).stem] = load(os.path.join(folder_name, f))
                progress_bar('已載入檔案', count, num_file, 50)
            
            if len(output_list) > 0:
                print('未找到的路線>> {} <<未找到的路線'.format(', '.join(output_list)))
        
        else:
            count = 0
            num_file = len(os.listdir(folder_name))
            for f in os.listdir(folder_name):
                count += 1
                line_Ns[Path(f).stem] = load(os.path.join(folder_name, f))
                progress_bar('已載入檔案', count, num_file, 50)

    return line_Ns

def load(path_path: str):
    """讀取已經儲存的站牌間路徑"""
    path_file = open(path_path, 'r')
    path_str = path_file.read()
    path_file.close()
    path = path_str.split(',')
    path = list(map(int, path))
    
    return path

def progress_bar(msg: str, current: int, total: int, bar_len: int):
    """ Display the progress bar if the result is printed to the text file. """
    completed = int(current / total * bar_len)
    print(
        '\r[{}{}] {}: {}/{}'.format(
            '■' * completed, '□' * (bar_len - completed), msg, current, total
        ), 
        end=''
    )
    if current == total:
        print()

def create_output_str(line_Ns, line_names, line_df=None, timetable=None, attr_df=None):
    final_output_str = ';;<<PT>><<LINE>>;;\n'
    count = 0
    total_line = len(line_Ns)
    for line in line_Ns:
        count += 1
        line_name_list = line_names.loc[line_names['檔案編號'] == line, 'LINE NAME'].tolist()
        if len(line_name_list) == 1:
            #get located zone
            line_zone = line[:3]

            #create LINE NAME
            line_name = line_name_list[0]

            # create LONGNAME
            if line_df is None:
                long_name = 'N/A'
            else:
                line_spec = line.split('_')
                cond1 = line_df['SubRouteUID'] == line_spec[0]
                cond2 = line_df['Direction'] == int(line_spec[-1])
                SubRouteName_list = line_df.loc[cond1 & cond2, 'SubRouteName'].tolist()
                if len(SubRouteName_list) > 0:
                    SubRouteName = SubRouteName_list[0]
                    Headsign = line_df.loc[cond1 & cond2, 'Headsign'].tolist()[0]
                    long_name = '{} {}'.format(SubRouteName, Headsign)
                else:
                    long_name = 'N/A'
            
            #get the attributes of the line
            attributes = get_line_attr(line, attr_df, timetable)

            #get and append the text
            final_output_str += create_line_str(
                line_Ns[line], line_zone, line_name, long_name, attributes
            )

        progress_bar('已輸出路線', count, total_line, 50)
    
    return final_output_str

def get_line_attr(line, attr_df, timetable):
    """query the attributes of specific line"""
    mode = operator = vehicle_type = fare_system = 0
    headway = [0, 0, 0]

    if (attr_df is not None) and (attr_df['LINE'].isin([line]).any()):
        mode = attr_df.loc[attr_df['LINE'] == line, 'MODE'].tolist()[0]
        operator = attr_df.loc[attr_df['LINE'] == line, 'OPERATOR'].tolist()[0]
        vehicle_type = attr_df.loc[attr_df['LINE'] == line, 'VEHICLETYPE'].tolist()[0]
        fare_system = attr_df.loc[attr_df['LINE'] == line, 'FARESYSTEM'].tolist()[0]

    if (timetable is not None) and (timetable['LINE'].isin([line]).any()):
        headway = [
            timetable.loc[timetable['LINE'] == line, 'weekday_morning_peak'].tolist()[0],
            timetable.loc[timetable['LINE'] == line, 'weekday_evening_peak'].tolist()[0],
            timetable.loc[timetable['LINE'] == line, 'weekday_offpeak'].tolist()[0],
        ]

    return {
        'mode': mode,
        'operator': operator,
        'vehicle_type': vehicle_type,
        'fare_system': fare_system,
        'headway': headway,
    }

def create_line_str(line_N, line_zone, line_name, long_name, attributes):
    """generate the text"""
    global zone_text
    isCircular = 1 if line_N[0] == line_N[-1] else 0
    line_str = (
        ';;;;;;;;{zone};;;;;;;;;;;;;;\n'
        'LINE NAME=\"{linename}\", LONGNAME=\"{longname}\",\n'
        '    MODE={mode}, OPERATOR={operator}, '
            'VEHICLETYPE={vehicletype}, FARESYSTEM={faresystem}, '
            'HEADWAY[1]={h1}, HEADWAY[2]={h2}, HEADWAY[3]={h3},\n'
        '    ONEWAY=T, CIRCULAR={circular}, N='
    ).format(
        zone=zone_text[line_zone],
        linename=line_name,
        longname=long_name,
        mode=attributes['mode'],
        operator=attributes['operator'],
        vehicletype=attributes['vehicle_type'],
        faresystem=attributes['fare_system'],
        h1=attributes['headway'][0], 
        h2=attributes['headway'][1], 
        h3=attributes['headway'][2],
        circular=isCircular
    )

    for i in range(min(12, len(line_N))):
        if i == len(line_N) - 1:
            line_str += '{:>7d}'.format(line_N[i])
        else:
            line_str += '{:>7d},'.format(line_N[i])
    line_str += '\n'

    if len(line_N) > 12:
        num_full_row = (len(line_N) - 12) // 15
        for r in range(num_full_row):
            line_str += '    '
            for c in range(15):
                if c + 15 * r + 12 == len(line_N) - 1:
                    line_str += '{:>7d}'.format(line_N[c + 15 * r + 12])
                else:
                    line_str += '{:>7d},'.format(line_N[c + 15 * r + 12])
            line_str += '\n'
        
        if len(line_N) > 12 + 15 * num_full_row:
            line_str += '    '
            for i in range(12 + 15 * num_full_row, len(line_N)):
                if i == len(line_N) - 1:
                    line_str += '{:>7d}'.format(line_N[i])
                else:
                    line_str += '{:>7d},'.format(line_N[i])
            line_str += '\n'
    
    line_str += '\n'

    return line_str

def main():
    zone_dir = [
        os.path.join('City', 'MiaoliCounty'),
        os.path.join('City', 'Taichung'),
        os.path.join('City', 'ChanghuaCounty'),
        os.path.join('City', 'NantouCounty'),
        os.path.join('City', 'YunlinCounty'),
        'InterCity'
    ]

    while True:
        update_date = input('Enter download date of the bus route data: ')
        if os.path.isdir('PTX_data/CSV_{}'.format(update_date)):
            break
    route_full_file = 'PTX_data/CSV_{}/C_TWN/central_taiwan_bus_routes.csv'.format(update_date)
    full_route = pd.read_csv(route_full_file)

    timetable_list = [
        pd.read_csv(os.path.join('PTX_data', 'CSV_{}'.format(update_date), 'Bus', d, 'route_headway.csv'))
        for d in zone_dir
        if os.path.isfile(os.path.join('PTX_data', 'CSV_{}'.format(update_date), 'Bus', d, 'route_headway.csv'))
    ]
    timetable = pd.concat(timetable_list, axis=0, ignore_index=True)
    timetable['LINE'] = timetable.apply(
        lambda row: '{}_{}_{}'.format(row.SubRouteUID, row.SubRouteName, row.Direction), axis=1
    )

    use_setting = ''
    while use_setting.upper() != 'Y' and use_setting.upper() != 'N':
        use_setting = input('Use combine_line_setting.csv? [Y/N]: ')
    if use_setting.upper() == 'Y':
        setting_df = pd.read_csv('combine_line_setting.csv')
        setting = {}
        for i in setting_df.index:
            setting[setting_df.loc[i, 'name']] = setting_df.loc[i, 'input']
        folder_option = setting['folder_option']
        folder_name = setting['folder_name']
        line_option = setting['line_option']
        list_name = setting['list_name']

    while use_setting.upper() == 'N':
        setting['linename'] = input('EXCEL filepath for LINE NAME lookup: ')
        if os.path.isfile(setting['linename']):
            break
    linename_sheet = pd.read_excel(setting['linename'])

    while use_setting.upper() == 'N':
        setting['attributes'] = input('EXCEL filepath for attributes lookup: ')
        if os.path.isfile(setting['attributes']):
            break
    attr_sheet = pd.read_excel(setting['attributes'])

    if use_setting.upper() == 'N':
        line_Ns = get_line_Ns(use_setting)
    else:
        line_Ns = get_line_Ns(
            use_setting, folder_option=folder_option, folder_name=folder_name,
            line_option=line_option, list_name=list_name
        )
    output_text = create_output_str(
        line_Ns, linename_sheet, line_df=full_route, timetable=timetable, attr_df=attr_sheet
    )

    while use_setting.upper() == 'N':
        setting['output'] = input('請輸入輸出檔路徑：')
        if os.path.isfile(setting['output']):
            break
    with open(setting['output'], 'w', encoding='Big5', errors='ignore') as output_file:
        output_file.write(output_text)
    
if __name__ == '__main__':
    main()