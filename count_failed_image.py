# -*- coding: utf-8 -*-

from csv import reader as csv_reader
from PIL import Image
import os

def get_road_list(road_csv_path: str):
    road_list = {}
    with open(road_csv_path, newline='') as road_csv:
        road_row = csv_reader(road_csv)
        for r in road_row:
            if r[0] == 'ID':
                continue
            else:
                road_list[int(r[0])] = [(int(r[2]), int(r[3])), int(r[4])]
    print('完成道路讀取...')
    return road_list

def count_white_proportion(folder_name, file_name, color_white):
    im = Image.open(os.path.join(folder_name, file_name))

    width, height = im.size

    total_pixel = width * height

    white = 0
    for pixel in im.getdata():
        if pixel == color_white:
            white += 1
    return white / total_pixel

def progress_bar(current_num: int, total_num: int):
    """ Display the progress bar if the result is printed to the text file. """
    print(
        '\r[{:<50}] {}: {}/{}'.format(
            '=' * int(current_num / (2 * total_num) * 100), 
            'processed images', current_num, total_num
        ), 
        end=''
    )
    if current_num == total_num:
        print()

def main():
    road_list = get_road_list('P:/09091-中臺區域模式/Working/98_GIS/road/CSV/C_TWN_ROAD_picked.csv')

    image_format = input('請輸入要檢查的圖檔副檔名(png, jpg)：')

    if image_format == 'png':
        color_white = (255, 255, 255, 255)
    else:
        color_white = (255, 255, 255)

    folder_name = 'test'
    failed_img = []
    
    total_num = len([img for img in os.listdir(folder_name) if img.endswith('png')])
    processed_count = 0
    for link_img in os.listdir(folder_name):
        if link_img.endswith('png'):
            proportion = count_white_proportion(folder_name, link_img)
            processed_count += 1
            progress_bar(processed_count, total_num)
            if proportion > 0.5:
                failed_img.append(link_img)
    print('Failed image: ', failed_img)

if __name__ == '__main__':
    main()