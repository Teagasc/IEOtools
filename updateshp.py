#!/usr/bin/env python3
# By Guy Serbin, Environment, Soils, and Land Use Dept., CELUP, Teagasc,
# Johnstown Castle, Co. Wexford Y35 TC97, Ireland
# email: guy <dot> serbin <at> teagasc <dot> ie

# version 1.1.1

# This script will create and update a shapefile of all available Landsat TM/ETM+/OLI-TIRS scenes, including available metadata

import os, sys, urllib.error, datetime, shutil, ieo, glob
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

global pathrows, errorsfound

config = configparser.ConfigParser()
config_location = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'updateshp.ini')

config.read(config_location) # config_path
pathrowvals = config['DEFAULT']['pathrowvals'] # this is a comma-delimited string containing multiples of four values: start path, end path, start row, end row. It is designed to query rectangular path/row combinations, in order to avoid scenes that don't touch landmasses or are not of interest. 
useWRS2 = config['DEFAULT']['useWRS2'] # Setting this parameter to "Yes" in updateshp.ini will query WRS-2 Path/ Row field values from ieo.WRS2, and may result in a great increase in the number of queries to USGS servers

pathrows = []
subpathrow = []
xmls = []

#xmls = ['metadata21.xml', 'metadata22_24.xml']
ingestdir = os.path.join(ieo.ingestdir, 'Metadata')
dirname = os.path.join(ieo.catdir, 'Landsat')
logdir = ieo.logdir
jpgdir = os.path.join(ieo.catdir, 'Landsat', 'Thumbnails')
itmdir = ieo.srdir
shapefile = ieo.landsatshp
layername = os.path.basename(shapefile)[:-4] # assumes a shapefile ending in '.shp'
addfields = ['Thumb_JPG', 'LEDAPS', 'BT', 'Fmask', 'Pixel_QA', 'NDVI', 'EVI']
errorlist = []
scenelist = []
startdate = '1982-01-01'
today = datetime.datetime.today()
enddate = today.strftime('%Y-%m-%d')

errorfile = os.path.join(logdir, 'Landsat_inventory_download_errors.csv')
errorsfound = False

localxmls = False # New code as the old XML download string doesn't include newer landsat data or the new product IDs.
local = input('Do you have local XML metadata files that you downloaded from the USGS? (y/N): ')
if local.lower() == 'y' or local.lower == 'yes':
    localxmls = True
    xmls = glob.glob(os.path.join(ingestdir, '*.xml'))

if not localxmls and len(xmls) == 0:
    if useWRS2.lower() == 'yes':
#        gdb, wrs = os.path.split(ieo.WRS2)
        driver = ogr.GetDriverByName("ESRI Shapefile")
        ds = driver.Open(ieo.WRS2, 0)
        layer = ds.Getlayer()
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


def dlxmls(startdate, enddate, xmls, ingestdir, *args, **kwargs): # This downloads queried XML files
    #pathrows = [[207, 208, 21, 21],[205, 209, 22, 24]]
    global errorsfound
    tries = 1
    downloaded = False
    for x, p in zip(xmls, pathrows):
        
        print('Downloading {} to: {}'.format(x, ingestdir))
        xml = os.path.join(ingestdir, x)
        if os.access(xml, os.F_OK):
            print('Backing up current xml file.')
            shutil.move(xml, '{}.{}.bak'.format(xml, today.strftime('%Y%m%d-%H%M%S')))
        urlname = 'http://earthexplorer.usgs.gov/EE/InventoryStream/pathrow?start_path={}&end_path={}&start_row={}&end_row={}&sensor_name=LANDSAT_COMBINED_C1&start_date={}&end_date={}'.format(p[0], p[1], p[2], p[3], startdate, enddate) #&cloud_cover = 100&seasonal = False&aoi_entry=path_row&output_type=unknown
        tries = 1
        downloaded = False   
        while not downloaded and tries < 6: 
            print('Download attempt {} of 5.'.format(tries))
            try: 
#                url = urllib.request.urlopen(urlname)
                urlretrieve(urlname, xml) # filename=xml
                downloaded = True
            except URLError as e:
                print(e.reason)
                ieo.logerror(urlname, e.reason, errorfile = errorfile)
                errorsfound = True
                tries += 1
        if tries == 6:    
            ieo.logerror(xml, 'Download error.', errorfile = errorfile)
            print('Download failure: {}'.format(x))
            errorsfound = True
    else:
        return 'Success!' 


def dlthumb(url, jpgdir, *args, **kwargs): # This downloads thumbnails from the USGS 
    global errorsfound
    basename = os.path.basename(url)
    f = os.path.join(jpgdir, basename)
    tries = 1
    downloaded = False
    print('Downloading {} to {}'.format(basename, jpgdir))
    while not downloaded and tries < 6: 
        print('Download attempt {} of 5.'.format(tries))
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
            errorsfound = True
    if tries == 6:    
        ieo.logerror(f, 'Download error.', errorfile = errorfile)
        print('Download failure: {}'.format(basename))
        errorsfound = True
    else:
        return 'Success!'

def findlocalfiles(sceneID, tdict, fielddict, xmldict):
    localfiledict = {}
    for field in addfields[1:]:
        localfiledict[field] = None
    itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(sceneID, ieo.projacronym))
    if not os.path.isfile(itm): # Populate 'LEDAPS' field if surface reflectance data are present in library
        itmlist = glob.glob(os.path.join(itmdir, '{}*_ref_{}.dat'.format(sceneID[:16], ieo.projacronym)))
        if len(itmlist) > 0:
            itm = itmlist[0]
        else:
            itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(xmldict['LandsatPID'], ieo.projacronym))
            if not os.path.isfile(itm):
                itm = None
    if itm:
        localfiledict['ITM'] = itm
        itmbasename = os.path.basename(itm)
        extloc =  itmbasename.find('_ref_')
        scenebase = itmbasename[:extloc]
        for key in fielddict.keys():
            datafile = os.path.join(fielddict[key]['dirname'], '{}{}'.format(scenebase, fielddict[key]['ext']))
            if os.path.isfile(datafile):
                localfiledict[key] = datafile
    return localfiledict

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
        bak = jpw.replace('.jpw', '.jpw.{}.bak'.format(today.strftime('%Y%m%d-%H%M%S')))
        shutil.move(jpw, bak)
    with open(jpw, 'w') as file:
        file.write('{}\n-{}\n-{}\n-{}\n{}\n{}\n'.format(A, D, B, E, C, F))
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

#target = osr.SpatialReference()
#i = ieo.prjstr.find(':') + 1
#target.ImportFromEPSG(int(ieo.prjstr[i:])) # EPSG code set in ieo.ini 
target = ieo.prj

transform = osr.CoordinateTransformation(source, target)

# Create Shapefile
driver = ogr.GetDriverByName("ESRI Shapefile")

polycoords = ['upperLeftCornerLatitude', 'upperLeftCornerLongitude', 'upperRightCornerLatitude', 'upperRightCornerLongitude', 'lowerLeftCornerLatitude', 'lowerLeftCornerLongitude', 'lowerRightCornerLatitude', 'lowerRightCornerLongitude']



fnames = ['LandsatPID', 'sceneID', 'sensor', 'acqDate', 'Updated', 'path', 'row', 'CenterLat', 'CenterLong', 'CC', 'CCFull', 'UL_Q_CCA', 'UR_Q_CCA', 'LL_Q_CCA', 'LR_Q_CCA', 'dayOrNight', 'sunEl', 'sunAz', 'StartTime', 'StopTime', 'SN', 'DT_L1', 'cartURL', 'DT_L0RP', 'DATUM', 'ELEVSOURCE', 'ELLIPSOID', 'EPHEM_TYPE', 'CPS_MODEL', 'GCPSVERIFY', 'RMSE_MODEL', 'RMSE_X', 'RMSE_Y', 'RMSEVERIFY', 'GC_SIZE_R', 'GC_SIZE_TH', 'PROJ_L1', 'PROJ_L0RA', 'ORIENT', 'FORMAT', 'L1_AVAIL', 'LINES', 'SAMPLES', 'RESAMP_OPT', 'TH_LINES', 'TH_SAMPLES', 'UTM_ZONE', 'PROCSOFTVE', 'CPF_NAME', 'IMAGE_QUAL', 'DATEL1_GEN', 'GCP_Ver', 'CCLand', 'CollectCat', 'CollectNum', 'flightPath', 'RecStation', 'imageQual1', 'imageQual2', 'gainBand1', 'gainBand2', 'gainBand3', 'gainBand4', 'gainBand5', 'gainBand6H', 'gainBand6L', 'gainBand7', 'gainBand8', 'GCBand1', 'GCBand2', 'GCBand3', 'GCBand4', 'GCBand5', 'GCBand6H', 'GCBand6L', 'GCBand7', 'GCBand8', 'GCSIZE_PAN', 'PAN_LINES', 'PANSAMPLES', 'SCAN_GAP_I', 'ROLL_ANGLE', 'FULL_PART', 'NADIR_OFFN', 'RLUT_FNAME', 'BPF_N_OLI', 'BPF_N_TIRS', 'TIRS_SSM', 'browse', 'browseURL']

tags = []
tagvals = [['LANDSAT_PRODUCT_ID', ogr.OFTString, 40], 
        ['sceneID', ogr.OFTString, 21], 
        ['sensor', ogr.OFTString, 0], 
        ['acquisitionDate', ogr.OFTDate, 0], 
        ['dateUpdated', ogr.OFTDate, 0], 
        ['path', ogr.OFTInteger, 0], 
        ['row', ogr.OFTInteger, 0], 
        ['sceneCenterLatitude', ogr.OFTReal, 0], 
        ['sceneCenterLongitude', ogr.OFTReal, 0], 
        ['cloudCover', ogr.OFTInteger, 0], 
        ['cloudCoverFull',ogr.OFTInteger, 0], 
        ['FULL_UL_QUAD_CCA', ogr.OFTReal, 0], 
        ['FULL_UR_QUAD_CCA', ogr.OFTReal, 0], 
        ['FULL_LL_QUAD_CCA', ogr.OFTReal, 0], 
        ['FULL_LR_QUAD_CCA', ogr.OFTReal, 0], 
        ['dayOrNight', ogr.OFTString, 0], 
        ['sunElevation', ogr.OFTReal, 0], 
        ['sunAzimuth', ogr.OFTReal, 0], 
        ['sceneStartTime', ogr.OFTString, 0], 
        ['sceneStopTime', ogr.OFTString, 0], 
        ['satelliteNumber', ogr.OFTString, 0], 
        ['DATA_TYPE_L1', ogr.OFTString, 0], 
        ['cartURL', ogr.OFTString, 0], 
        ['DATA_TYPE_L0RP', ogr.OFTString, 0], 
        ['DATUM', ogr.OFTString, 0], 
        ['ELEVATION_SOURCE', ogr.OFTString, 0], 
        ['ELLIPSOID', ogr.OFTString, 0], 
        ['EPHEMERIS_TYPE', ogr.OFTString, 0], 
        ['GROUND_CONTROL_POINTS_MODEL', ogr.OFTInteger, 0], 
        ['GROUND_CONTROL_POINTS_VERIFY', ogr.OFTInteger, 0], 
        ['GEOMETRIC_RMSE_MODEL', ogr.OFTReal, 0], 
        ['GEOMETRIC_RMSE_MODEL_X', ogr.OFTReal, 0], 
        ['GEOMETRIC_RMSE_MODEL_Y', ogr.OFTReal, 0], 
        ['GEOMETRIC_RMSE_VERIFY', ogr.OFTReal, 0], 
        ['GRID_CELL_SIZE_REFLECTIVE', ogr.OFTInteger, 0], 
        ['GRID_CELL_SIZE_THERMAL', ogr.OFTInteger, 0], 
        ['MAP_PROJECTION_L1', ogr.OFTString, 0], 
        ['MAP_PROJECTION_L0RA', ogr.OFTString, 0], 
        ['ORIENTATION', ogr.OFTString, 0], 
        ['OUTPUT_FORMAT', ogr.OFTString, 0], 
        ['L1_AVAILABLE', ogr.OFTString, 0], 
        ['REFLECTIVE_LINES', ogr.OFTInteger, 0], 
        ['REFLECTIVE_SAMPLES', ogr.OFTInteger, 0], 
        ['RESAMPLING_OPTION', ogr.OFTString, 0], 
        ['THERMAL_LINES', ogr.OFTInteger, 0], 
        ['THERMAL_SAMPLES', ogr.OFTInteger, 0], 
        ['UTM_ZONE', ogr.OFTInteger, 0], 
        ['PROCESSING_SOFTWARE_VERSION', ogr.OFTString, 0], 
        ['CPF_NAME', ogr.OFTString, 0], 
        ['IMAGE_QUALITY', ogr.OFTInteger, 0], 
        ['DATE_L1_GENERATED', ogr.OFTDate, 0], 
        ['GROUND_CONTROL_POINTS_VERSION', ogr.OFTInteger, 0], 
        ['CLOUD_COVER_LAND', ogr.OFTInteger, 0], 
        ['COLLECTION_CATEGORY', ogr.OFTString, 0], 
        ['COLLECTION_NUMBER', ogr.OFTInteger, 0],
        ['flightPath', ogr.OFTString, 0],
        ['receivingStation', ogr.OFTString, 0],
        ['imageQuality1', ogr.OFTString, 0],
        ['imageQuality2', ogr.OFTString, 0],
        ['gainBand1', ogr.OFTString, 0],
        ['gainBand2', ogr.OFTString, 0],
        ['gainBand3', ogr.OFTString, 0],
        ['gainBand4', ogr.OFTString, 0],
        ['gainBand5', ogr.OFTString, 0],
        ['gainBand6H', ogr.OFTString, 0],
        ['gainBand6L', ogr.OFTString, 0],
        ['gainBand7', ogr.OFTString, 0],
        ['gainBand8', ogr.OFTString, 0],
        ['gainChangeBand1', ogr.OFTString, 0],
        ['gainChangeBand2', ogr.OFTString, 0],
        ['gainChangeBand3', ogr.OFTString, 0],
        ['gainChangeBand4', ogr.OFTString, 0],
        ['gainChangeBand5', ogr.OFTString, 0],
        ['gainChangeBand6H', ogr.OFTString, 0],
        ['gainChangeBand6L', ogr.OFTString, 0],
        ['gainChangeBand7', ogr.OFTString, 0],
        ['gainChangeBand8', ogr.OFTString, 0],
        ['GRID_CELL_SIZE_PANCHROMATIC', ogr.OFTString, 0],
        ['PANCHROMATIC_LINES', ogr.OFTString, 0],
        ['PANCHROMATIC_SAMPLES', ogr.OFTString, 0],
        ['SCAN_GAP_INTERPOLATION', ogr.OFTString, 0],
        ['ROLL_ANGLE', ogr.OFTString, 0],
        ['FULL_PARTIAL_SCENE', ogr.OFTString, 0],
        ['NADIR_OFFNADIR', ogr.OFTString, 0],
        ['RLUT_FILE_NAME', ogr.OFTString, 0],
        ['BPF_NAME_OLI', ogr.OFTString, 0],
        ['BPF_NAME_TIRS', ogr.OFTString, 0],
        ['TIRS_SSM_MODEL', ogr.OFTString, 0],
        ['browseAvailable', ogr.OFTString, 0], 
        ['browseURL', ogr.OFTString, 0]]

for tagval in tagvals:
    tags.append(tagval[0])

if not os.access(shapefile, os.F_OK):
    # Create Shapefile
    
    data_source = driver.CreateDataSource(shapefile)
    layer = data_source.CreateLayer(layername, target, ogr.wkbPolygon)
    for fname, tagval in zip(fnames, tagvals):
        field_name = ogr.FieldDefn(fname, tagval[1])
        if tagval[2] > 0:
            field_name.SetWidth(tagval[2])
        layer.CreateField(field_name)
        
    
    layer.CreateField(ogr.FieldDefn('Thumb_JPG', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('LEDAPS', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('BT', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('Fmask', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('Pixel_QA', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('NDVI', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('EVI', ogr.OFTString))
    spatialRef = ieo.prj
    spatialRef.MorphToESRI()
    with open(shapefile.replace('.shp', '.prj'), 'w') as output:
        output.write(spatialRef.ExportToWkt())

    
else:
    shpfnames = []
    # Open existing shapefile with write access
    data_source = driver.Open(shapefile, 1)
    layer = data_source.GetLayer()
    layerDefinition = layer.GetLayerDefn()
    # Get list of field names 
    for i in range(layerDefinition.GetFieldCount()):
        shpfnames.append(layerDefinition.GetFieldDefn(i).GetName())
    # Find missing fields and create them
    for fname in fnames:
        if not fname in shpfnames:
            i = fnames.index(fname)
            field_name = ogr.FieldDefn(fnames[i], tagvals[i][1])
            if tagvals[i][2] > 0:
                field_name.SetWidth(tagvals[i][2])
            layer.CreateField(field_name)

    # Iterate through features and fetch sceneID values
    for feature in layer:
        scenelist.append(feature.GetField("sceneID"))

fielddict = {'BT' : {'ext' : '_BT_{}.dat'.format(ieo.projacronym), 'dirname' : ieo.btdir}, 
            'Fmask' : {'ext' : '_cfmask.dat', 'dirname' : ieo.fmaskdir},
            'Pixel_QA' : {'ext' : '_pixel_qa.dat', 'dirname' : ieo.pixelqadir},
            'NDVI' : {'ext' : '_NDVI.dat', 'dirname' : ieo.ndvidir},
            'EVI' : {'ext' : '_EVI.dat', 'dirname' : ieo.evidir}}

thumbnails = []
scenes = []
filenum = 1
numfiles = len(xmls)
xmldict = {}

# Download XML files from USGS/EROS
if not localxmls:
    print(dlxmls(startdate, enddate, xmls, ingestdir))

# Parse XML files
for xml in xmls:
    print('Processing {}, file number {} of {}.'.format(xml, filenum, numfiles))
    xmlfile = os.path.join(ingestdir, xml)
    tree = ET.parse(xmlfile)
    root = tree.getroot()
#    headervals = []
#    for i in range(len(root[1])):
#        j = root[1][i].tag.find('}') + 1
#        if not root[1][i].tag[j:] in polycoords:
#            headervals.append(root[1][i].tag[j:])
    
    numnodes = len(root)
    for i in range(numnodes):
        tdict = {} # Version 1.1.1: Now uses a dict rather than absolute position in XML node for fields and values
        for j in range(len(root[i])):
            k = root[i][j].tag.find('}') + 1
            tagname = root[i][j].tag[k:]
            if not tagname in polycoords:
                fname = fnames[tags.index(tagname)]
                tdict[fname] = root[i][j].text
            elif tagname in polycoords:
                tdict[tagname] = root[i][j].text
            else:
                print('ERROR: Discovered previously unused XML tag {}, logging to error file: '.format(tagname, errorfile))
                ieo.logerror(xml, 'Unused XML tag: {}'.format(tagname), errorfile = errorfile)
                errorsfound = True
        
        sys.stderr.write('\rProcessing node {} of {}.'.format(i + 1, numnodes))
        if len(root[i]) > 10:
            sceneID = tdict['sceneID']
            xmldict[sceneID] = tdict
            
            # Add thumbnail URL to download list
            if not sceneID in scenelist:
                if tdict['browseURL'].endswith('.jpg'):
                    dlurl = tdict['browseURL']
                    thumbnails.append(tdict['browseURL'])
                
                print('\nAdding {} to shapefile.'.format(sceneID))
                scenelist.append(sceneID)
                # Determine polygon coordinates in Lat/ Lon WGS-84
                coords = [
[float(tdict['upperLeftCornerLongitude']), float(tdict['upperLeftCornerLatitude'])], 
[float(tdict['upperRightCornerLongitude']), float(tdict['upperRightCornerLatitude'])], 
[float(tdict['lowerRightCornerLongitude']), float(tdict['lowerRightCornerLatitude'])], 
[float(tdict['lowerLeftCornerLongitude']), float(tdict['lowerLeftCornerLatitude'])], [float(tdict['upperLeftCornerLongitude']), float(tdict['upperLeftCornerLatitude'])]]
                # create the feature
                feature = ogr.Feature(layer.GetLayerDefn())
                # Add field attributes from XML
#                for k in range(len(root[i])):
#                    if root[i][k].tag[j:] in headervals:
#                        m = tags.index(root[i][k].tag[j:])
#                        feature.SetField(root[i][k].tag[j:], root[i][k].text)
                for key in tdict.keys():
                    if key in fnames:
                        feature.SetField(key, tdict[key])
                basename = os.path.basename(dlurl)
                jpg = os.path.join(jpgdir, basename)
                localfiledict = findlocalfiles(sceneID, tdict, fielddict, xmldict)
                
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
                            errorsfound = True
                        if os.access(jpg, os.F_OK):
                            feature.SetField('Thumb_JPG', jpg)
                        for key in localfiledict.keys():
                            if localfiledict[key]:
                                feature.SetField(key, localfiledict[key])
                        layer.SetFeature(feature)
                    except Exception as e:
                        print(e)
                        ieo.logerror(os.path.basename(jpg), e, errorfile = errorfile)
                        errorsfound = True
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
    updatingfeature = False
    sceneID = feature.GetField("sceneID")
    localfiledict = findlocalfiles(sceneID, tdict, fielddict, xmldict)
    dlurl = feature.GetField("browseURL")
    if dlurl:
        print('Processing scene {}.'.format(sceneID))
        basename = os.path.basename(dlurl)
        jpg = os.path.join(jpgdir, basename)
#        for fname in fnames:
#            if feature.GetField(fname) != xmldict[sceneID][fname]:
#                print('Updating metadata for sceneID {}, field {}: {}'.format(sceneID, fname, xmldict[sceneID][fname]))
#                feature.Setfield(fname, xmldict[sceneID][fname])
       
        if os.path.isfile(jpg) and jpg != feature.GetField(addfields[0]):
            print('Updating metadata for sceneID {}, field {}: {}'.format(sceneID, jpg, addfields[0]))
            feature.SetField(jpg, addfields[0])
            updatingfeature = True
                
    for key in localfiledict.keys():
        if localfiledict[key] and localfiledict[key] != feature.GetField(localfiledict[key]):
            feature.SetField(key, localfiledict[key])
            updatingfeature = True
    if updatingfeature:
        layer.SetFeature(feature)

data_source = None

if errorsfound:
    print('Errors were found during script execution. please see the error log file for details: {}'.format(errorfile))

print('Processing complete.')
        