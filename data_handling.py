
import os
import sys
from stat import *
import pprint

import numpy as np
import pandas as pd
import geopandas as gpd
import geojson 
import xmltodict
import zipfile
from netCDF4 import Dataset
from bs4 import BeautifulSoup


class Sentinel:
    """
    Class object to retrieve data from Sentinel 1, 2, 3 satellites and extract relevant data
    """
    def __init__(self, filename):
        """
        Unzips the file and gets 
        """
        #Make sure the file ends in zip
        filename = filename.split('.')[0]+'.zip'
        #Ectract the zipfile
        with zipfile.ZipFile(filename) as z:
            z.extractall()

        #The below makes sure we have the correct extension to the directory name
        #TODO: Add S5p '.SEN3' if filename[:2:]=='S5'
        folder_extension = '.SEN3' if filename[:2:]=='S3' else '.SAFE'

        #Assign folder name
        self.filename = filename.split('.')[0]+folder_extension

        self.files = self.get_file_tree()

    def get_file_tree(self,path):
        """Creates nested tree structure from filepath
        DIrectly taken from https://stackoverflow.com/questions/19522004/building-a-dictionary-from-directory-structure"""
        st = os.stat(path)
        result = {}
        result['active'] = True
        #result['stat'] = st
        result['full_path'] = path
        if S_ISDIR(st.st_mode):
            result['type'] = 'd'
            result['items'] = {
                name : self.get_file_tree(path+'/'+name)
                for name in os.listdir(path)}
        else:
            result['type'] = 'f'
        return result
    
    def print_tree(self):
        """Prints formated tree using pprint"""
        pprint.pprint(self.files)
        return 0

    def get_all_data(self, files):
        """
        Returns all files of file dictionary passed 
        Returns a non nested dictionary with content of each file
        """
        file_cont = {}
        file_cont = self.iterate(file_cont, ['items'])
    
    def iterate(self, file_dat_dict, file_dict):
        """Function to repetatively iterate json file and load content"""
        for i in file_dict:
            if os.path.isdir(file_dict[i]['full_path']):
                #Call the same function with the items subset of file_dict (which contains the lower order files)
                self.iterate(file_dict[i]['items'],file_dat_dict)

            elif file_dict[i]['full_path'][:-4:]=='safe' or file_dict[i]['full_path'][:-4:]=='.xml' or file_dict[i]['full_path'][:-4:]=='.xsd':
                #This applies to all xml/xsd/safe formated files
                file_dat_dict[i] = self.get_xml(file_dict[i]['full_path'])

            elif file_dict[i]['full_path'][:-4:]=='tiff':
                """We will load all tiff files by default using Geotiff format"""
                

            elif file_dict[i]['full_path'][:-3:]=='.nc':
                

        return file_cont


    def get_xml(self,file_path):
        """Function to get xml/xsd/safe"""
        with open(file_path,'r') as f:
            file_cont = f.read()
        #Creates OrderedDictionary of content
        return xmltodict.parse(file_cont)

    def get_jp2(self,)