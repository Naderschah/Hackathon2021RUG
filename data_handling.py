
import os
import sys
from stat import *
import pprint

import numpy as np
from numpy.core.arrayprint import _object_format
import pandas as pd
import geopandas as gpd
import geojson
import rasterio 
import xmltodict
import zipfile
from netCDF4 import Dataset
from bs4 import BeautifulSoup
import shapely.wkt
from shapely.geometry import Point



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

        self.files = self.get_file_tree(self.filename)

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

    def get_all_data(self, files=None):
        """
        Returns all files of file dictionary passed 
        Returns a non nested dictionary with content of each file
        """
        file_cont = {}
        if files  == None:
            return self.iterate(file_cont, self.files['items'])
        else:
            if 'items' in files: files = files['items']
            return self.iterate(file_cont, files)

    def format_geopandas(self, files, files_to_use): # TODO: Does not work with the netcdf files
        """
        Formats nc file directories into geopandas dataframe
        """
        crs = self.get_crs()
        gml = self.get_gml().split(' ')
        print(crs)
        df = pd.DataFrame({'longitude':gml[::2], 'latitude':gml[1::2]})
        
        if crs == None:
            print('Coordinate reference system could not be found')

        geometry = gpd.points_from_xy(df.longitude, df.latitude, crs=crs)
        
        #Create Geopandas frame
        #First we check that the arrays arent redundantly nested
        for i in files_to_use:
            if type(files[i])==list and len(files[i])==1 and type(files[i][0])!=float:
                """In case the array is nested"""
                files[i] = files[i][0]
        #Next we create our dictionary object for pandas, since we are working with multidimensional data, we will make a seperate one for each
        data_dict = {}
        for i in files_to_use:
            for j in range(len(files[i])):
                # We will index the individual products based on their position
                data_dict[i.split('_')[0]+'_'+str(j)] = files[i][j]
                print(files[i].shape)
        #Now we create a dataframe
        df = pd.DataFrame(data=data_dict)
        print(df)
        return gpd.GeoDataFrame(df, geometry=geometry)#crs=crs, geometry=coord_dict)

    
    def iterate(self, file_dat_dict, file_dict):
        """Function to repetatively iterate json file and load content"""
        for i in file_dict:
            #Double check that this filename isnt already used
            if i in file_dat_dict.keys():
                name = '2_'+i
            else:
                name = i
            if os.path.isdir(file_dict[i]['full_path']):
                #Call the same function with the items subset of file_dict (which contains the lower order files)
                self.iterate(file_dat_dict,file_dict[i]['items'])

            elif file_dict[i]['full_path'][-4::]=='safe' or file_dict[i]['full_path'][-4::]=='.xml' or file_dict[i]['full_path'][-4::]=='.xsd':
                #This applies to all xml/xsd/safe formated files
                file_dat_dict[name] = self.get_xml(file_dict[i]['full_path'])

            elif file_dict[i]['full_path'][-4::]=='tiff':
                """We will load all tiff files by default using Geotiff format"""
                file_dat_dict[name] = self.get_tiff(file_dict[i]['full_path'])

            elif file_dict[i]['full_path'][-3::]=='jp2':
                """We will load all tiff files by default using Geotiff format"""   
                file_dat_dict[name] = self.get_jp2(file_dict[i]['full_path'])
                
            elif file_dict[i]['full_path'][-3::]=='.nc':
                file_dat_dict[name] = self.get_nc(file_dict[i]['full_path'])
            #TODO: No file extension data
            elif len(file_dict[i]['full_path'].split('/')[-1].split('.'))==1:
                print('Could not load file without extension: {}'.format(file_dict[i]['full_path']))
            else:
                print('Could not load file {}'.format(file_dict[i]['full_path']))

        return file_dat_dict

    def get_xml(self,file_path):
        """Function to get xml/xsd/safe"""
        with open(file_path,'r') as f:
            file_cont = f.read()
        #Creates OrderedDictionary of content
        return xmltodict.parse(file_cont)

    def get_nc(self, file_path):
        """Load netCDF files"""
        rootgrp = Dataset(file_path, "r")
        array = []
        #Load the data (here the assumption is that the directory contains several nc files with geolocation and data files)
        for i in rootgrp.variables.keys():
            array.append(rootgrp[i][:])
        return array

    def get_tiff(self, file_path):
        """Load tiff files (assumption that the files are geotiff)"""
        return self.get_jp2(file_path)


    def get_jp2(self,file_path):
        """Load jp2 image data and create geopandas dataframe"""
        #First we load the file
        dat = rasterio.open(file_path, 'r+')
        # Now we need to establish what coordinate reference system is used,
        # Most likely it will not be contained in the metadata, but will be in the manifest
        crs = self.get_crs(dat)
        if crs == None:
            print('Coordinate reference system could not be found for {}'.format(file_path))

        # Now we create 1D coordinate arrays
        xmin, ymax = np.around(dat.xy(0.00, 0.00), 9)
        xmax, ymin = np.around(dat.xy(dat.height-1, dat.width-1), 9)
        x = np.linspace(xmin, xmax, dat.width)
        y = np.linspace(ymax, ymin, dat.height)

        xs, ys = np.meshgrid(x, y)
        #Read in data
        zs = dat.read(1)
        #Get mask
        mask = dat.read_masks(1) > 0
        xs, ys, zs = xs[mask], ys[mask], zs[mask]
        #Create dict of data
        data = {"X": pd.Series(xs.ravel()),
            "Y": pd.Series(ys.ravel()),
            "Z": pd.Series(zs.ravel())}
        #Create Geopandas frame
        df = pd.DataFrame(data=data)
        geometry = gpd.points_from_xy(df.X, df.Y)
        df = df['Z']
        return gpd.GeoDataFrame(df, crs=crs, geometry=geometry)

    def get_crs(self, dat=None):
        """Function to get the coordinate reference system which is generally not included in jp2s"""
        #In case the crs is saved in the data file
        if dat != None:
            if dat.crs != None:
                return dat.crs
        
        #We now retrieve the crs from the manifest
        if os.path.isfile(os.path.join(self.filename, 'manifest.safe')):
            mainfest = self.get_xml(os.path.join(self.filename, 'manifest.safe'))
        elif os.path.isfile(os.path.join(self.filename, 'xfdumanifest.xml')):
            mainfest = self.get_xml(os.path.join(self.filename, 'xfdumanifest.xml'))
        else:
            return None
        for i in mainfest['xfdu:XFDU']['metadataSection']['metadataObject']:
            if i['@ID'] == 'measurementFrameSet':
                try:
                    crs=i['metadataWrap']['xmlData']['safe:frameSet']['safe:footPrint']['@srsName'].split('/')[-1].replace('.xml', '').split('#')
                except:
                    crs=None
                if crs == None:
                    try:
                        crs=i['metadataWrap']['xmlData']['sentinel-safe:frameSet']['sentinel-safe:footPrint']['@srsName'].split('/')[-3::]
                        crs = crs[0::2]
                    except:
                        crs=None
                return crs
        #In case it doesnt find anything
        return None

    def get_gml(self):
        """Function to get the coordinate reference system which is generally not included in jp2s"""
        
        #We now retrieve the gml from the manifest
        if os.path.isfile(os.path.join(self.filename, 'manifest.safe')):
            mainfest = self.get_xml(os.path.join(self.filename, 'manifest.safe'))
        elif os.path.isfile(os.path.join(self.filename, 'xfdumanifest.xml')):
            mainfest = self.get_xml(os.path.join(self.filename, 'xfdumanifest.xml'))
        else:
            return None
        for i in mainfest['xfdu:XFDU']['metadataSection']['metadataObject']:
            if i['@ID'] == 'measurementFrameSet':
                try:
                    crs=i['metadataWrap']['xmlData']['safe:frameSet']['safe:footPrint']['gml:posList']
                except:
                    crs=None
                if crs == None:
                    try:
                        crs=i['metadataWrap']['xmlData']['sentinel-safe:frameSet']['sentinel-safe:footPrint']['gml:posList']
                    except:
                        crs=None
                return crs
        #In case it doesnt find anything
        return None

    def plt_on_map(self, gpd_frame=None):
        """Creates plot object of world map and returns figure if a geopandas dataframe is added
        it will be plotted on top of the map.
        ---------
        dpg_frame -- > geopandas DataFrame with data, all of it will be plotted
        """

        #Here we plot a map of the world 
        ax = gpd.read_file('world.geo.json').plot(color='white', edgecolor='black',figsize=(16,16))

        # We have to turn the well-known Text (wkl) footprint into a shapely object which then gets loaded into a geodataframe to ease plotting
        
        if type(gpd_frame)!=None:
            gpd_frame.plot(ax=ax,column='Z',cmap='plasma')

        return ax
