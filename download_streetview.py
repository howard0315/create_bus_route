# -*- coding: utf-8 -*-

import os
import requests
# from PIL import Image
from io import BytesIO
import pandas as pd
import ssl

def download(parameter, OD):

    streetview_url = 'https://maps.googleapis.com/maps/api/streetview'

    file_name = '{}_{}.jpg'.format(OD[0], OD[1])
    streetview = requests.get(streetview_url, params=parameter, verify=False)
    print(streetview.url)
    # image_file = open(file_name, 'wb')
    # image_file.write(Image.open(BytesIO(streetview.content)))
    # image_file.close()


def main():
    howard5328821_KEY = 'AIzaSyBYqpQ3DSTrGxfsPpAtMDXydirX4jM8W7I'
    parameter = {
        'size': '427x240',
        'location': '{lat},{lon}'.format(lat=25.033001, lon=121.563360),
        'fov': '90',
        'heading': '0',
        'pitch': '-10',
        'key': howard5328821_KEY,
    }

    OD = [0, 0]

    download(parameter, OD)

if __name__ == '__main__':
    main()