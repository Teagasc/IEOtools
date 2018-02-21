#!/usr/bin/env python3
# By Guy Serbin, Environment, Soils, and Land Use Dept., CELUP, Teagasc,
# Johnstown Castle, Co. Wexford Y35 TC97, Ireland
# email: guy <dot> serbin <at> teagasc <dot> ie

# version 1.1.0

# This script will create and update a shapefile of all available Landsat TM/ETM+/OLI-TIRS scenes, including available metadata

import os, sys, urllib.error, datetime, shutil, ieo
from osgeo import ogr, osr
import xml.etree.ElementTree as ET
from PIL import Image

if sys.version_info[0] == 2:
    import ConfigParser as configparser
    from urllib import urlretrieve
    from urllib2 import urlopen, URLError
else:
    import configparser
    from urllib.request import urlopen, urlretrieve
    from urllib.error import URLError

global pathrows

config = configparser.ConfigParser()
config_location = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'updateshp.ini')

config.read(config_location) # config_path
pathrowvals = config['DEFAULT']['pathrowvals'] # this is a comma-delimited string containing multiples of four values: start path, end path, start row, end row. It is designed to query rectangular path/row combinations, in order to avoid scenes that don't touch landmasses or are not of interest. 
useWRS2 = config['DEFAULT']['useWRS2'] # Setting this parameter to "Yes" in updateshp.ini will query WRS-2 Path/ Row field values from ieo.WRS2, and may result in a great increase in the number of queries to USGS servers

pathrows = []
subpathrow = []
xmls = []

if useWRS2.lower() == 'yes':
    gdb, wrs = os.path.split(ieo.WRS2)
    driver = ogr.GetDriverByName("FileGDB")
    ds = driver.Open(gdb, 0)
    layer = ds.Getlayer(wrs)
    for feature in layer:
        path = feature.GetField('PATH')
        row = feature.GetField('ROW')
        pathrows.append([path, path, row, row])
        xmls.append('Metadata_{}{:03d}.xml'.format(path, row))
    ds = None
else:
    pathrowvals = pathrowvals.split(',')
    numxmls = len(pathrowvals) / 4
    xmlnum = 1
    i = 0
    if numxmls > 0:
        while xmlnum <= numxmls:
            subpathrow.append(int(pathrowvals[i]))
            i += 1
            if i % 4 == 0:
                xmls.append('Metadata_{}.xml'.format(xmlnum))
                pathrows.append(subpathrow)
                subpathrow = []
                xmlnum += 1
    else:
        print('Error: there are no values for WRS Paths/Rows in updateshp.ini, or the file is missing. Returning.')
        sys.exit()
    

#xmls = ['metadata21.xml', 'metadata22_24.xml']
ingestdir = os.path.join(ieo.ingestdir, 'Metadata')
dirname = os.path.join(ieo.catdir, 'Landsat')
logdir = ieo.logdir
jpgdir = os.path.join(ieo.catdir, 'Landsat', 'Thumbnails')
itmdir = ieo.srdir
shapefile = ieo.landsatshp
layername = os.path.basename(shapefile)[:-4] # assumes a shapefile ending in '.shp'
addfields = ['Thumb_JPG', 'LEDAPS' ]
errorlist = []
scenelist = []
startdate = '1982-01-01'
today = datetime.datetime.today()
enddate = today.strftime('%Y-%m-%d')

errorfile = os.path.join(logdir, 'Landsat_inventory_download_errors.csv')

def dlxmls(startdate, enddate, xmls, ingestdir): # This downloads queried XML files
    #pathrows = [[207, 208, 21, 21],[205, 209, 22, 24]]
    tries = 1
    downloaded = False
    for x, p in zip(xmls, pathrows):
        
        print('Downloading %s to: %s'%(x, ingestdir))
        xml = os.path.join(ingestdir, x)
        if os.access(xml, os.F_OK):
            print('Backing up current xml file.')
            shutil.move(xml, '{}.{}.bak'.format(xml, today.strftime('%Y%m%d-%H%M%S')))
        urlname = 'http://earthexplorer.usgs.gov/EE/InventoryStream/pathrow?start_path=%d&end_path=%d&start_row=%d&end_row=%d&sensor_name=LANDSAT_COMBINED_C1&start_date=%s&end_date=%s'%(p[0], p[1], p[2], p[3], startdate, enddate) #&cloud_cover = 100&seasonal = False&aoi_entry=path_row&output_type=unknown
        tries = 1
        downloaded = False   
        while not downloaded and tries < 6: 
            print('Download attempt %d of 5.'%tries)
            try: 
#                url = urllib.request.urlopen(urlname)
                urlretrieve(urlname, xml) # filename=xml
                downloaded = True
            except URLError as e:
                print(e.reason)
                ieo.logerror(urlname, e.reason, errorfile = errorfile)
                tries += 1
        if tries == 6:    
            ieo.logerror(xml, 'Download error.', errorfile = errorfile)
            print('Download failure: %s'%x)
    else:
        return 'Success!' 


def dlthumb(url, jpgdir): # This downloads thumbnails from the USGS 
    basename = os.path.basename(url)
    f = os.path.join(jpgdir, basename)
    tries = 1
    downloaded = False
    print('Downloading %s to %s'%(basename, jpgdir))
    while not downloaded and tries < 6: 
        print('Download attempt %d of 5.'%tries)
        try: 
            url = urlopen(dlurl)
            urlretrieve(dlurl, filename = f)
            if url.length == os.stat(f).st_size:
                downloaded = True
            else:
                print('Error downloading, retrying.')
                tries += 1
        except urllib.error.URLError as e:
            print(e.reason)
            ieo.logerror(dlurl, e.reason, errorfile = errorfile)
    if tries == 6:    
        ieo.logerror(f, 'Download error.', errorfile = errorfile)
        print('Download failure: %s'%basename)
    else:
        return 'Success!'

def makeworldfile(jpg, geom): # This attempts to make a worldfile for thumbnails so they can be displayed in a GIS
    img = Image.open(jpg)
    basename = os.path.basename(jpg)
    width, height = img.size
    width = float(width)
    height = float(height)
    minX, maxX, minY, maxY = geom.GetEnvelope()
    if basename[:3] == 'LE7':
        wkt = geom.ExportToWkt()
        start = wkt.find('(') + 2
        end = wkt.find(')')
        vals = wkt[start:end]
        vals = vals.split(',')
        corners = []
        for val in vals:
            val = val.split()
            for v in val:
                corners.append(float(v))
        A = (maxX - corners[0]) / width
        B = (corners[0] - minX) / height
        C = corners[0]
        D = (maxY - corners[3]) / width
        E = (corners[3] - minY) / height
        F = corners[1]
    else:
        A = (maxX - minX) / width
        B = 0.0
        C = minX
        D = (maxY - minY) / height
        E = 0.0
        F = maxY
    jpw = jpg.replace('.jpg', '.jpw')
    if os.access(jpw, os.F_OK):
        bak = jpw.replace('.jpw', '.jpw.%s.bak'%today.strftime('%Y%m%d-%H%M%S'))
        shutil.move(jpw, bak)
    with open(jpw, 'w') as file:
        file.write('%f\n-%f\n-%f\n-%f\n%f\n%f\n'%(A, D, B, E, C, F))
    del img
    
def reporthook(blocknum, blocksize, totalsize):
    # This makes a progress bar. I did not originally write it, nor do I remember from where I found the code.
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize
        s = "\r%5.1f%% %*d / %d" % (
            percent, len(str(totalsize)), readsofar, totalsize)
        sys.stderr.write(s)
        if readsofar >= totalsize: # near the end
            sys.stderr.write("\n")
    else: # total size is unknown
        sys.stderr.write("read %d\n" % (readsofar,))

# Lat/ Lon WGS-84 to Irish Transverse Mercator ERTS-89 transformation
source = osr.SpatialReference() # Lat/Lon WGS-64
source.ImportFromEPSG(4326)

target = osr.SpatialReference()
i = ie.prj.find(':') + 1
target.ImportFromEPSG(int(ieo.prj[i:])) # EPSG code set in ieo.ini

transform = osr.CoordinateTransformation(source, target)

# Create Shapefile
driver = ogr.GetDriverByName("ESRI Shapefile")

polycoords = ['upperLeftCornerLatitude', 'upperLeftCornerLongitude', 'upperRightCornerLatitude', 'upperRightCornerLongitude', 'lowerLeftCornerLatitude', 'lowerLeftCornerLongitude', 'lowerRightCornerLatitude', 'lowerRightCornerLongitude']

fnames = ['sceneID', 'sensor', 'acqDate', 'Updated', 'path', 'row', 'CenterLat', 'CenterLong', 'CC', 'CCFull', 'UL_Q_CCA', 'UR_Q_CCA', 'LL_Q_CCA', 'LR_Q_CCA', 'dayOrNight', 'sunEl', 'sunAz', 'StartTime', 'StopTime', 'SN', 'DT_L1', 'cartURL', 'DT_L0RP', 'DATUM', 'ELEVSOURCE', 'ELLIPSOID', 'EPHEM_TYPE', 'CPS_MODEL', 'GCPSVERIFY', 'RMSE_MODEL', 'RMSE_X', 'RMSE_Y', 'RMSEVERIFY', 'GC_SIZE_R', 'GC_SIZE_TH', 'PROJ_L1', 'PROJ_L0RA', 'ORIENT', 'FORMAT', 'L1_AVAIL', 'LINES', 'SAMPLES', 'RESAMP_OPT', 'TH_LINES', 'TH_SAMPLES', 'UTM_ZONE', 'PROCSOFTVE', 'CPF_NAME', 'IMAGE_QUAL', 'browse', 'browseURL', 'DATEL1_GEN', 'GCP_Ver']

tags = ['sceneID', 'sensor', 'acquisitionDate', 'dateUpdated', 'path', 'row', 'sceneCenterLatitude', 'sceneCenterLongitude', 'cloudCover', 'cloudCoverFull', 'FULL_UL_QUAD_CCA', 'FULL_UR_QUAD_CCA', 'FULL_LL_QUAD_CCA', 'FULL_LR_QUAD_CCA', 'dayOrNight', 'sunElevation', 'sunAzimuth', 'sceneStartTime', 'sceneStopTime', 'satelliteNumber', 'DATA_TYPE_L1', 'cartURL', 'DATA_TYPE_L0RP', 'DATUM', 'ELEVATION_SOURCE', 'ELLIPSOID', 'EPHEMERIS_TYPE', 'GROUND_CONTROL_POINTS_MODEL', 'GROUND_CONTROL_POINTS_VERIFY', 'GEOMETRIC_RMSE_MODEL', 'GEOMETRIC_RMSE_MODEL_X', 'GEOMETRIC_RMSE_MODEL_Y', 'GEOMETRIC_RMSE_VERIFY', 'GRID_CELL_SIZE_REFLECTIVE', 'GRID_CELL_SIZE_THERMAL', 'MAP_PROJECTION_L1', 'MAP_PROJECTION_L0RA', 'ORIENTATION', 'OUTPUT_FORMAT', 'L1_AVAILABLE', 'REFLECTIVE_LINES', 'REFLECTIVE_SAMPLES', 'RESAMPLING_OPTION', 'THERMAL_LINES', 'THERMAL_SAMPLES', 'UTM_ZONE', 'PROCESSING_SOFTWARE_VERSION', 'CPF_NAME', 'IMAGE_QUALITY', 'browseAvailable', 'browseURL', 'DATE_L1_GENERATED', 'GROUND_CONTROL_POINTS_VERSION']

if not os.access(shapefile, os.F_OK):
    # Create Shapefile
    
    data_source = driver.CreateDataSource(shapefile)
    layer = data_source.CreateLayer(layername, target, ogr.wkbPolygon)
    field_name = ogr.FieldDefn(fnames[0], ogr.OFTString)
    field_name.SetWidth(21)
    layer.CreateField(field_name)
    field_name = ogr.FieldDefn(fnames[1], ogr.OFTString)
    layer.CreateField(field_name)
    field_name = ogr.FieldDefn(fnames[2], ogr.OFTDate)
    layer.CreateField(field_name)
    field_name = ogr.FieldDefn(fnames[3], ogr.OFTDate)
    layer.CreateField(field_name)
    layer.CreateField(ogr.FieldDefn(fnames[4], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[5], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[6], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[7], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[8], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[9], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[10], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[11], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[12], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[13], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[14], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[15], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[16], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[17], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[18], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[19], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[20], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[21], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[22], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[23], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[24], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[25], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[26], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[27], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[28], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[29], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[30], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[31], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[32], ogr.OFTReal))
    layer.CreateField(ogr.FieldDefn(fnames[33], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[34], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[35], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[36], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[37], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[38], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[39], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[40], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[41], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[42], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[43], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[44], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[45], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[46], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[47], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[48], ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn(fnames[49], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn(fnames[50], ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('Thumb_JPG', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('LEDAPS', ogr.OFTString))
else:
    data_source = driver.Open(shapefile, 1)
    layer = data_source.GetLayer()
    for feature in layer:
        scenelist.append(feature.GetField("sceneID"))

thumbnails = []
scenes = []
filenum = 1
numfiles = len(xmls)

# Download XML files from USGS/EROS
print(dlxmls(startdate, enddate, xmls, ingestdir))

# Parse XML files
for xml in xmls:
    print('Processing %s, file number %d of %d.'%(xml, filenum, numfiles))
    xmlfile = os.path.join(ingestdir, xml)
    tree = ET.parse(xmlfile)
    root = tree.getroot()
    headervals = []
    for i in range(len(root[1])):
        j = root[1][i].tag.find('}') + 1
        if not root[1][i].tag[j:] in polycoords:
            headervals.append(root[1][i].tag[j:])
    
    numnodes = len(root)
    for i in range(numnodes):
        sys.stderr.write('\rProcessing node %d of %d.'%(i + 1, numnodes))
        if len(root[i])>10:
        
            # Add thumbnail URL to download list

            if not root[i][2].text in scenelist:
                if root[i][1].text.endswith('.jpg'):
                    dlurl = root[i][1].text
                    thumbnails.append(root[i][1].text)
                sceneID = root[i][2].text
                print('\nAdding %s to shapefile.'%sceneID)
                scenelist.append(sceneID)
                # Determine polygon coordinates in Lat/ Lon WGS-84
                coords = [[float(root[i][9].text), float(root[i][8].text)], [float(root[i][11].text), float(root[i][10].text)], [float(root[i][15].text), float(root[i][14].text)], [float(root[i][13].text), float(root[i][12].text)], [float(root[i][9].text), float(root[i][8].text)]]
                # create the feature
                feature = ogr.Feature(layer.GetLayerDefn())
                # Add field attributes from XML
                for k in range(len(root[i])):
                    if root[i][k].tag[j:] in headervals:
                        m = tags.index(root[i][k].tag[j:])
                        feature.SetField(fnames[m], root[i][k].text)
                basename = os.path.basename(dlurl)
                jpg = os.path.join(jpgdir, basename)
                itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(sceneID, ieo.projacronym))
                if not os.access(jpg, os.F_OK):
                    try:
                        response = dlthumb(dlurl, jpgdir)
                        if response == 'Success!':
                            geom = feature.GetGeometryRef()
                            print('Creating world file.')
                            makeworldfile(jpg, geom)
                            print('Migrating world and projection files to new directory.')
                            jpw = jpg.replace('.jpg', '.jpw')
                            prj = jpg.replace('.jpg', '.prj')
                            
                            
                        else:
                            print('Error with sceneID or filename, adding to error list.')
                            ieo.logerror(sceneID, response, errorfile = errorfile)
                        if os.access(jpg, os.F_OK):
                            feature.SetField('Thumb_JPG', jpg)
                        if os.access(itm, os.F_OK):
                            feature.SetField('LEDAPS', itm)
                        layer.SetFeature(feature)
                    except Exception as e:
                        print(e)
                        ieo.logerror(os.path.basename(jpg), e, errorfile = errorfile)
                # Create ring
                ring = ogr.Geometry(ogr.wkbLinearRing)
                for coord in coords:
                    ring.AddPoint(coord[0], coord[1])
                # Create polygon
                poly = ogr.Geometry(ogr.wkbPolygon)
                
                poly.AddGeometry(ring)  
                poly.Transform(transform)   # Convert to local projection
                feature.SetGeometry(poly)  
                layer.CreateFeature(feature)
                print('\n')
    print('\n')    
    
    filenum += 1

# Update metadata in shapefile
layer_defn = layer.GetLayerDefn()
field_names = [layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())]
for field in addfields: #Add any missing fields
    if not field in field_names:
        new_field = ogr.FieldDefn(field, ogr.OFTString)
        layer.CreateField(new_field)
for feature in layer:
    sceneID = feature.GetField("sceneID")
    itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(sceneID, ieo.projacronym))
    dlurl = feature.GetField("browseURL")
    print('Processing scene %s.'%sceneID)
    basename = os.path.basename(dlurl)
    jpg = os.path.join(jpgdir,basename)
    for x, y in zip(addfields, [jpg, itm]):
        if os.access(y, os.F_OK) and y != feature.GetField(x):
            print('Updating metadata for sceneID {}, field {}: {}'.format(sceneID, x, y))
            feature.SetField(x, y)
            layer.SetFeature(feature)

print('Processing complete.')
        