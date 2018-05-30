#!/usr/bin/env python3
# By Guy Serbin, Environment, Soils, and Land Use Dept., CELUP, Teagasc,
# Johnstown Castle, Co. Wexford Y35 TC97, Ireland
# email: guy <dot> serbin <at> teagasc <dot> ie

# version 1.1.1

# This script will create and update a shapefile of all available Landsat TM/ETM+/OLI-TIRS scenes, including available metadata
# Changes:
# 23 May 2018: XML functionality deprecated in favor of JSON queries, as the former is no longer available or efficient

import os, sys, urllib.error, datetime, shutil, glob, argparse, json, getpass, requests, math #, ieo
from osgeo import ogr, osr
import xml.etree.ElementTree as ET
from PIL import Image

try: # This is included as the module may not properly install in Anaconda.
    import ieo
except:
    print('Error: IEO failed to load. Please input the location of the directory containing the IEO installation files.')
    ieodir = input('IEO installation path: ')
    if os.path.isfile(os.path.join(ieodir, 'ieo.py')):
        sys.path.append(r'D:\Data\IEO\ieo')
        import ieo
    else:
        print('Error: that is not a valid path for the IEO module. Exiting.')
        sys.exit()

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

parser = argparse.ArgumentParser('This script imports LEDAPS-processed scenes into the local library. It stacks images and converts them to the locally defined projection in IEO, and adds ENVI metadata.')
#parser.add_argument('-x','--xml', type = bool, default = False, help = 'Use downloaded XML files from USGS.')
#parser.add_argument('-j','--json', type = bool, default = True, help = 'Use JSON query (Default = True).')
parser.add_argument('-u','--username', type = str, default = None, help = 'USGS/EROS Registration System (ERS) username.')
parser.add_argument('-p', '--password', type = str, default = None, help = 'USGS/EROS Registration System (ERS) password.')
parser.add_argument('-c', '--catalogID', type = str, default = 'EE', help = 'USGS/EROS Catalog ID (default = "EE").')
parser.add_argument('-v', '--version', type = str, default = "1.4.0", help = 'JSON version, default = 1.4.0.')
parser.add_argument('--startdate', type = str, default = "1982-01-01", help = 'Start date for query in YYYY-MM-DD format. (Default = 1982-01-01).')
parser.add_argument('--enddate', type = str, default = None, help = "End date for query in YYYY-MM-DD format. (Default = today's date).")
parser.add_argument('-m', '--MBR', type = str, default = None, help = 'Minimum Bounding Rectangle (MBR) coordinates in decimal degrees in the following format (comma delimited, no spaces): lower left latitude, lower left longitude, upper right latitude, upper right longitude. If not supplied, these will be determined from WRS-2 Paths and Rows in updateshp.ini.')
parser.add_argument('-b', '--baseURL', type = str, default = 'https://earthexplorer.usgs.gov/inventory/json/v/', help = 'Base URL to use excluding JSON version (Default = "https://earthexplorer.usgs.gov/inventory/json/v/").')
parser.add_argument('--maxResults', type = int, default = 50000, help = 'Maximum number of results to return (1 - 50000, default = 50000).')
parser.add_argument('--overwrite', type = bool, default = False, help = 'Overwrite existing files.')
parser.add_argument('--thumbnails', type = bool, default = True, help = 'Download thumbnails (default = True).')
args = parser.parse_args()

if not (args.username and args.password):
    if not args.username:
        args.username = input('USGS/ERS username: ')
    if not args.password:
        args.password = getpass.getpass('USGS/ERS password: ')

#pathrows = []
subpathrow = []
#xmls = []

#xmls = ['metadata21.xml', 'metadata22_24.xml']
ingestdir = os.path.join(ieo.ingestdir, 'Metadata')
dirname = os.path.join(ieo.catdir, 'Landsat')
logdir = ieo.logdir
jpgdir = os.path.join(ieo.catdir, 'Landsat', 'Thumbnails')
itmdir = ieo.srdir
shapefile = ieo.landsatshp
layername = os.path.basename(shapefile)[:-4] # assumes a shapefile ending in '.shp'
addfields = ['MaskType', 'Thumb_JPG', 'SR_path', 'BT', 'Fmask', 'Pixel_QA', 'NDVI', 'EVI']
errorlist = []
scenelist = []
if not args.enddate:
    today = datetime.datetime.today()
    args.enddate = today.strftime('%Y-%m-%d')

errorfile = os.path.join(logdir, 'Landsat_inventory_download_errors.csv')
errorsfound = False

#localxmls = False # New code as the old XML download string doesn't include newer landsat data or the new product IDs.
#local = input('Do you have local XML metadata files that you downloaded from the USGS? (y/N): ')
#if local.lower() == 'y' or local.lower == 'yes':
#    localxmls = True
#    xmls = glob.glob(os.path.join(ingestdir, '*.xml'))

pathrowstrs = [] # list of strings containing WRS-2 Path/ Row combinations
paths = [] # list containing WRS-2 Paths
rows = [] # List containing WRS-2 Rows

if useWRS2.lower() == 'yes':
#   gdb, wrs = os.path.split(ieo.WRS2)
    print('Getting WRS-2 Path/Row combinations from shapefile: {}'.format(ieo.WRS2))
    driver = ogr.GetDriverByName("ESRI Shapefile")
    ds = driver.Open(ieo.WRS2, 0)
    layer = ds.Getlayer()
    for feature in layer:
        path = feature.GetField('PATH')
        if not path in paths:
            paths.append(path)
        row = feature.GetField('ROW')
        if not row in rows:
            rows.append(row)
        pathrowstrs.append('{03d}{:03d}'.format(path, row))    
#            pathrows.append([path, path, row, row])
    ds = None
else:
    print('Using WRS-2 Path/Row combinations from INI file.')
    pathrowvals = pathrowvals.split(',')
#    print(pathrowvals)
    iterations = int(len(pathrowvals) / 4)
#    print('Iterations = {}'.format(iterations))
    for i in range(iterations): 
        for j in range(int(pathrowvals[i * 4]), int(pathrowvals[i * 4 + 1]) + 1):
#            print('j = {}'.format(j))
            if not j in paths:
                paths.append(j)
            for k in range(int(pathrowvals[i * 4 + 2]), int(pathrowvals[i * 4 + 3]) + 1): 
#                print('k = {}'.format(k))
                pathrowstrs.append('{:03d}{:03d}'.format(j, k))
                if not k in rows:
                    rows.append(k)

#print('Paths')
#print(paths)
#print('Rows')
#print(rows)

#if not localxmls and len(xmls) == 0:
#    if useWRS2.lower() == 'yes':
##        gdb, wrs = os.path.split(ieo.WRS2)
#        driver = ogr.GetDriverByName("ESRI Shapefile")
#        ds = driver.Open(ieo.WRS2, 0)
#        layer = ds.Getlayer()
#        for feature in layer:
#            path = feature.GetField('PATH')
#            row = feature.GetField('ROW')
#            pathrows.append([path, path, row, row])
#            xmls.append('Metadata_{}{:03d}.xml'.format(path, row))
#        ds = None
#    else:
#        pathrowvals = pathrowvals.split(',')
#        numxmls = len(pathrowvals) / 4
#        xmlnum = 1
#        i = 0
#        if numxmls > 0:
#            while xmlnum <= numxmls:
#                subpathrow.append(int(pathrowvals[i]))
#                i += 1
#                if i % 4 == 0:
#                    xmls.append('Metadata_{}.xml'.format(xmlnum))
#                    pathrows.append(subpathrow)
#                    subpathrow = []
#                    xmlnum += 1
#        else:
#            print('Error: there are no values for WRS Paths/Rows in updateshp.ini, or the file is missing. Returning.')
#            sys.exit()

## JSON functions

def getapiKey():
    # This function gets the apiKey used for all queries to the USGS/EROS servers
    URL = '{}{}/login'.format(args.baseURL, args.version)
    print('Logging in to: {}'.format(URL))
    data = json.dumps({'username': args.username, 'password': args.password, 'catalog_ID': args.catalogID})
    response = requests.post(URL, data = {'jsonRequest':data}) # , verify = False) # 
    json_data = json.loads(response.text)
    apiKey = json_data['data']
    return apiKey

def getMBR():
    # This creates the Minimum Bounding Rectangle (MBR) for JSON queries
    URL = '{}{}/grid2ll'.format(args.baseURL, args.version)
    prs = [[min(paths), min(rows)], [min(paths), max(rows)], [max(paths), max(rows)], [max(paths), min(rows)]]
    Xcoords = []
    Ycoords = []
    for pr in prs:
        print('Requesting coordinates for WRS-2 Path {} Row {}.'.format(pr[0], pr[1]))
        jsonRequest = json.dumps({"gridType" : "WRS2", "responseShape" : "point", "path" : str(pr[0]), "row" : str(pr[1])}).replace(' ','')
        requestURL = '{}?jsonRequest={}'.format(URL, jsonRequest)
        response = requests.post(requestURL) # , verify = False) # URL, data = {'jsonRequest': jsonRequest}
        json_data = json.loads(response.text)
        Xcoords.append(float(json_data["data"]["coordinates"][0]["longitude"]))
        Ycoords.append(float(json_data["data"]["coordinates"][0]["latitude"]))
    return [min(Ycoords), min(Xcoords), max(Ycoords), max(Xcoords)]

def scenesearch(apiKey, scenelist):
    # This searches the USGS archive for scene metadata, and checks it against local metadata. New scenes will be queried for metadata.
    RequestURL = '{}{}/search'.format(args.baseURL, args.version)
    QueryURL = '{}{}/metadata'.format(args.baseURL, args.version)
    datasetNames = ['LANDSAT_8_C1']#, 'LANDSAT_ETM_C1', 'LANDSAT_TM_C1']
    scenedict = {}
    js = {'LL': 0, 'UL': 1, 'UR': 2, 'LR': 3}
    for datasetName in datasetNames:
        print('Querying collection: {}'.format(datasetName))
        searchparams = json.dumps({"apiKey": apiKey,
                        "datasetName": datasetName,
                        "spatialFilter":{"filterType": "mbr",
                                         "lowerLeft":{"latitude": args.MBR[0],
                                                      "longitude": args.MBR[1]},
                                         "upperRight":{"latitude": args.MBR[2],
                                                       "longitude": args.MBR[3]}},
                        "temporalFilter":{"startDate": args.startdate,
                                          "endDate": args.enddate},
                        "includeUnknownCloudCover":False,
                        "maxCloudCover": 100,
                        "maxResults": args.maxResults,
                        "sortOrder": "ASC"})
        response = requests.post(RequestURL, data = {'jsonRequest': searchparams}) # , verify = False)
        json_data = json.loads(response.text)
        querylist = []
        for i in range(len(json_data['data']['results'])):
            sceneID = json_data['data']['results'][i]['entityId']
            if sceneID[3:9] in pathrowstrs and not sceneID in scenelist:
                querylist.append(sceneID)
                scenedict[sceneID] = {'Landsat Product Identifier': json_data['data']['results'][i]["displayId"],
                         "browseUrl": json_data['data']['results'][i]["browseUrl"],
                         "dataAccessUrl": json_data['data']['results'][i]["dataAccessUrl"],
                         "downloadUrl": json_data['data']['results'][i]["downloadUrl"],
                         "metadataUrl": json_data['data']['results'][i]["metadataUrl"],
                         "fgdcMetadataUrl": json_data['data']['results'][i]["fgdcMetadataUrl"],
                         'modifiedDate': json_data['data']['results'][i]["modifiedDate"],
                         "orderUrl": json_data['data']['results'][i]["orderUrl"],
                         'coords': [[0.0, 0.0]] * 5,
                         'Dataset Identifier': datasetName}
        
        if len(querylist) > 0:
            print('{} new scenes have been found, querying metadata.'.format(len(querylist)))
            iterations = math.ceil(len(querylist) / 100) # break up queries into blocks of 100 or less scenes
            total = 0
            iterations = 1 # temporary limitation
            for iteration in range(iterations):
                startval = iteration * 100
                if iteration * 100 > len(querylist):
                    endval = len(querylist) - startval - 1
                else: 
                    endval = startval + 99
                total += endval + 1
                print('Now querying {} scenes, query {}/{}.'.format((endval - startval + 1), iteration + 1, iterations))
                querystr = ''
                
                for sceneID in querylist[startval: endval]:
                    querystr += ',{}'.format(sceneID)
                querystr = querystr[1:]
                queryparams = json.dumps({"apiKey":apiKey,
                            "datasetName":datasetName,
                            'entityIds': querystr})
                query = requests.post(QueryURL, data = {'jsonRequest':queryparams}) # , verify = False)
                if endval == 99:
                    outfile = r'd:\data\ieo\firstquery.txt'
                    with open(outfile, 'w') as output:
                        output.write(query.text)
                querydict = json.loads(query.text)
                if len(querydict['data']) > 0:
                    for item in querydict['data']:
                        if len(item['metadataFields']) > 0:
                            for subitem in item['metadataFields']:
                                fieldname = subitem['fieldName'].rstrip().lstrip().replace('L-1', 'L1')
                                if fieldname == 'Landsat Scene Identifier':
                                    sceneID = subitem['value']
                                elif fieldname in queryfieldnames and not fieldname in scenedict[sceneID].keys():
                                    value = subitem['value']
                                    if value:
                                        i = queryfieldnames.index(fieldname)
                                        if fieldvaluelist[i][3] == ogr.OFTDate or fieldname.endswith('Date'):
                                            if 'Time' in fieldname:
                                                value = datetime.datetime.strptime(value[:-1], '%Y:%j:%H:%M:%S.%f')
                                            elif '/' in value:
                                                value = datetime.datetime.strptime(value, '%Y/%m/%d')
                                            else:
                                                value = datetime.datetime.strptime(value, '%Y-%m-%d')
                                        elif fieldvaluelist[i][3] == ogr.OFTReal:
                                            value = float(value)
                                        elif fieldvaluelist[i][3] == ogr.OFTInteger:
                                            try:
                                                value = int(value)
                                            except:
                                                print('Error: fieldname {} has a value of {}.'.format(fieldname, value))
                                                sys.exit()
                                        elif fieldname == 'browseUrl': 
                                            if value: 
                                                if value.lower() != 'null':
                                                    scenedict[sceneID]['browse'] = 'Y'
                                                else:
                                                    scenedict[sceneID]['browse'] = 'N'
                                        elif fieldname == 'Data Type Level-1':
                                            j = value.rfind('_') + 1
                                            value = value[j:]
                                        scenedict[sceneID][fieldname] = value
                                elif fieldname in polycoords:
                                    if 'Long' in fieldname:
                                        k = 1
                                    else:
                                        k = 0
                                    if fieldname.startswith('LL'): # Scene polygons start and end on lower left corner 
                                        for l in [0, 4]:                                
                                            scenedict[sceneID]['coords'][js[fieldname[:2]] + l][k] = float(value)
                                    else:
                                        scenedict[sceneID]['coords'][js[fieldname[:2]]][k] = float(value)
                                
                    if not 'Spacecraft Identifier' in scenedict[sceneID].keys():
                        scenedict[sceneID]['Spacecraft Identifier'] = 'LANDSAT_{}'.format(sceneID[2:3])
    return scenedict

def findlocalfiles(sceneID, fielddict, scenedict):
#    for field in addfields[1:]:
#        localfiledict[field] = None
    itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(sceneID, ieo.projacronym))
    if not os.path.isfile(itm): # Populate 'SR_path' field if surface reflectance data are present in library
        itmlist = glob.glob(os.path.join(itmdir, '{}*_ref_{}.dat'.format(sceneID[:16], ieo.projacronym)))
        if len(itmlist) > 0:
            itm = itmlist[0]
        else:
            itm = os.path.join(itmdir, '{}_ref_{}.dat'.format(scenedict[sceneID]['Landsat Product Identifier'], ieo.projacronym))
            if not os.path.isfile(itm):
                itm = None
    if itm:
        scenedict['SR_path'] = itm
        itmbasename = os.path.basename(itm)
        extloc =  itmbasename.find('_ref_')
        scenebase = itmbasename[:extloc]
        for key in fielddict.keys():
            datafile = os.path.join(fielddict[key]['dirname'], '{}{}'.format(scenebase, fielddict[key]['ext']))
            if os.path.isfile(datafile):
                scenedict[key] = datafile
                if key == 'PixQA_path':
                    scenedict['MaskType'] = 'Pixel_QA'
                elif key == 'Fmask_path':
                    scenedict['MaskType'] = 'FMask'
    return scenedict

## Old XML functions, deprecated

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




## Other functions

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

if args.MBR: # define MBR for scene queries
    args.MBR = args.MBR.split(',')
    if len(args.MBR) != 4:
        ieo.logerror('--MBR', 'Total number of coordinates does not equal four.', errorfile = errorfile)
        print('Error: Improper number of coordinates for --MBR set (must be four). Either remove this option (will use default values) or fix. Exiting.')
        sys.exit()
else:
    args.MBR = getMBR()

# This section borrowed from https://pcjericks.github.io/py-gdalogr-cookbook/projection.html
# Lat/ Lon WGS-84 to local projection transformation
source = osr.SpatialReference() # Lat/Lon WGS-64
source.ImportFromEPSG(4326)

#target = osr.SpatialReference()
#i = ieo.prjstr.find(':') + 1
#target.ImportFromEPSG(int(ieo.prjstr[i:])) # EPSG code set in ieo.ini 
target = ieo.prj

transform = osr.CoordinateTransformation(source, target)

# Create Shapefile
driver = ogr.GetDriverByName("ESRI Shapefile")

polycoords = ['UL Corner Lat dec', 'UL Corner Long ec', 'UR Corner Lat dec', 'UR Corner Long dec', 'LL Corner Lat dec', 'LL Corner Long dec', 'LR Corner Lat dec', 'LR Corner Long dec']

# fieldvaluelist element format: [shapefile fieldname, XML tag, JSON fieldname, OGR type, field length]
fieldvaluelist = [
    ['LandsatPID', 'LANDSAT_PRODUCT_ID', 'Landsat Product Identifier', ogr.OFTString, 40], 
    ['sceneID', 'sceneID', 'Landsat Scene Identifier', ogr.OFTString, 21], 
    ['SensorID', 'SensorID', 'Sensor Identifier', ogr.OFTString, 0], 
    ['SatNumber', 'satelliteNumber', 'Spacecraft Identifier', ogr.OFTString, 0], 
    ['acqDate', 'acquisitionDate', 'Acquisition Date', ogr.OFTDate, 0], 
    ['Updated', 'dateUpdated', 'modifiedDate', ogr.OFTDate, 0], 
    ['path', 'path', 'WRS Path', ogr.OFTInteger, 0], 
    ['row', 'row', 'WRS Row', ogr.OFTInteger, 0], 
    ['CenterLat', 'sceneCenterLatitude', 'Center Latitude dec', ogr.OFTReal, 0], 
    ['CenterLong', 'sceneCenterLongitude', 'Center Longitude dec', ogr.OFTReal, 0], 
    ['CC', 'cloudCover', 'Cloud Cover Truncated', ogr.OFTInteger, 0], 
    ['CCFull', 'cloudCoverFull', 'Scene Cloud Cover', ogr.OFTReal, 0], 
    ['CCLand', 'CLOUD_COVER_LAND', 'Land Cloud Cover', ogr.OFTReal, 0], 
    ['UL_Q_CCA', 'FULL_UL_QUAD_CCA', 'Cloud Cover Quadrant Upper Left', ogr.OFTReal, 0], 
    ['UR_Q_CCA', 'FULL_UR_QUAD_CCA', 'Cloud Cover Quadrant Upper Right', ogr.OFTReal, 0], 
    ['LL_Q_CCA', 'FULL_LL_QUAD_CCA', 'Cloud Cover Quadrant Lower Left', ogr.OFTReal, 0], 
    ['LR_Q_CCA', 'FULL_LR_QUAD_CCA', 'Cloud Cover Quadrant Lower Right', ogr.OFTReal, 0], 
    ['DT_L1', 'DATA_TYPE_L1', 'Data Type Level-1', ogr.OFTString, 0], 
    ['DT_L0RP', 'DATA_TYPE_L0RP', 'Data Type Level 0Rp', ogr.OFTString, 0], 
    ['L1_AVAIL', 'L1_AVAILABLE', 'L1 Available', ogr.OFTString, 0], 
    ['IMAGE_QUAL', 'IMAGE_QUALITY', 'Image Quality', ogr.OFTString, 0], 
    ['dayOrNight', 'dayOrNight', 'Day/Night Indicator', ogr.OFTString, 0], 
    ['sunEl', 'sunElevation', 'Sun Elevation L1', ogr.OFTReal, 0], 
    ['sunAz', 'sunAzimuth', 'Sun Azimuth L1', ogr.OFTReal, 0], 
    ['StartTime', 'sceneStartTime', 'Start Time', ogr.OFTDate, 0], 
    ['StopTime', 'sceneStopTime', 'Stop Time', ogr.OFTDate, 0], 
    ['UTM_ZONE', 'UTM_ZONE', 'UTM Zone', ogr.OFTInteger, 0], 
    ['DATUM', 'DATUM', 'Datum', ogr.OFTString, 0], 
    ['ELEVSOURCE', 'ELEVATION_SOURCE', 'Elevation Source', ogr.OFTString, 0], 
    ['ELLIPSOID', 'ELLIPSOID', 'Ellipsoid', ogr.OFTString, 0], 
    ['PROJ_L1', 'MAP_PROJECTION_L1', 'Map Projection Level-1', ogr.OFTString, 0], 
    ['PROJ_L0RA', 'MAP_PROJECTION_L0RA', 'Map Projection L0Ra', ogr.OFTString, 0], 
    ['ORIENT', 'ORIENTATION', 'Orientation', ogr.OFTString, 0], 
    ['EPHEM_TYPE', 'EPHEMERIS_TYPE', 'Ephemeris Type', ogr.OFTString, 0], 
    ['CPS_MODEL', 'GROUND_CONTROL_POINTS_MODEL', 'Ground Control Points Model', ogr.OFTInteger, 0], 
    ['GCPSVERIFY', 'GROUND_CONTROL_POINTS_VERIFY', 'Ground Control Points Version', ogr.OFTInteger, 0], 
    ['RMSE_MODEL', 'GEOMETRIC_RMSE_MODEL', 'Geometric RMSE Model (meters)', ogr.OFTReal, 0], 
    ['RMSE_X', 'GEOMETRIC_RMSE_MODEL_X', 'Geometric RMSE Model X', ogr.OFTReal, 0], 
    ['RMSE_Y', 'GEOMETRIC_RMSE_MODEL_Y', 'Geometric RMSE Model Y', ogr.OFTReal, 0], 
    ['RMSEVERIFY', 'GEOMETRIC_RMSE_VERIFY', 'Geometric RMSE Verify', ogr.OFTReal, 0], 
    ['FORMAT', 'OUTPUT_FORMAT', 'Output Format', ogr.OFTString, 0], 
    ['RESAMP_OPT', 'RESAMPLING_OPTION', 'Resampling Option', ogr.OFTString, 0], 
    ['LINES', 'REFLECTIVE_LINES', 'Reflective Lines', ogr.OFTInteger, 0], 
    ['SAMPLES', 'REFLECTIVE_SAMPLES', 'Reflective Samples', ogr.OFTInteger, 0], 
    ['TH_LINES', 'THERMAL_LINES', 'Thermal Lines', ogr.OFTInteger, 0], 
    ['TH_SAMPLES', 'THERMAL_SAMPLES', 'Thermal Samples', ogr.OFTInteger, 0], 
    ['PAN_LINES', 'PANCHROMATIC_LINES', 'Panchromatic Lines', ogr.OFTInteger, 0], 
    ['PANSAMPLES', 'PANCHROMATIC_SAMPLES', 'Panchromatic Samples', ogr.OFTInteger, 0], 
    ['GC_SIZE_R', 'GRID_CELL_SIZE_REFLECTIVE', 'Grid Cell Size Reflective', ogr.OFTInteger, 0], 
    ['GC_SIZE_TH', 'GRID_CELL_SIZE_THERMAL', 'Grid Cell Size Thermal', ogr.OFTInteger, 0], 
    ['GCSIZE_PAN', 'GRID_CELL_SIZE_PANCHROMATIC', 'Grid Cell Size Panchromatic', ogr.OFTInteger, 0], 
    ['PROCSOFTVE', 'PROCESSING_SOFTWARE_VERSION', 'Processing Software Version', ogr.OFTString, 0], 
    ['CPF_NAME', 'CPF_NAME', 'Calibration Parameter File', ogr.OFTString, 0], 
    ['DATEL1_GEN', 'DATE_L1_GENERATED', 'Date L-1 Generated', ogr.OFTString, 0], 
    ['GCP_Ver', 'GROUND_CONTROL_POINTS_VERSION', 'Ground Control Points Version', ogr.OFTInteger, 0], 
    ['DatasetID', 'DatasetID', 'Dataset Identifier', ogr.OFTString, 0],
    ['CollectCat', 'COLLECTION_CATEGORY', 'Collection Category', ogr.OFTString, 0], 
    ['CollectNum', 'COLLECTION_NUMBER', 'Collection Number', ogr.OFTString, 0], 
    ['flightPath', 'flightPath', 'flightPath', ogr.OFTString, 0], 
    ['RecStation', 'receivingStation', 'Station Identifier', ogr.OFTString, 0], 
    ['imageQual1', 'imageQuality1', 'Image Quality 1', ogr.OFTString, 0], 
    ['imageQual2', 'imageQuality2', 'Image Quality 2', ogr.OFTString, 0], 
    ['gainBand1', 'gainBand1', 'Gain Band 1', ogr.OFTString, 0], 
    ['gainBand2', 'gainBand2', 'Gain Band 2', ogr.OFTString, 0], 
    ['gainBand3', 'gainBand3', 'Gain Band 3', ogr.OFTString, 0], 
    ['gainBand4', 'gainBand4', 'Gain Band 4', ogr.OFTString, 0], 
    ['gainBand5', 'gainBand5', 'Gain Band 5', ogr.OFTString, 0], 
    ['gainBand6H', 'gainBand6H', 'Gain Band 6H', ogr.OFTString, 0], 
    ['gainBand6L', 'gainBand6L', 'Gain Band 6L', ogr.OFTString, 0], 
    ['gainBand7', 'gainBand7', 'Gain Band 7', ogr.OFTString, 0], 
    ['gainBand8', 'gainBand8', 'Gain Band 8', ogr.OFTString, 0], 
    ['GainChange', 'GainChange', 'Gain Change', ogr.OFTString, 0], 
    ['GCBand1', 'gainChangeBand1', 'Gain Change Band 1', ogr.OFTString, 0], 
    ['GCBand2', 'gainChangeBand2', 'Gain Change Band 2', ogr.OFTString, 0], 
    ['GCBand3', 'gainChangeBand3', 'Gain Change Band 3', ogr.OFTString, 0], 
    ['GCBand4', 'gainChangeBand4', 'Gain Change Band 4', ogr.OFTString, 0], 
    ['GCBand5', 'gainChangeBand5', 'Gain Change Band 5', ogr.OFTString, 0], 
    ['GCBand6H', 'gainChangeBand6H', 'Gain Change Band 6H', ogr.OFTString, 0], 
    ['GCBand6L', 'gainChangeBand6L', 'Gain Change Band 6L', ogr.OFTString, 0], 
    ['GCBand7', 'gainChangeBand7', 'Gain Change Band 7', ogr.OFTString, 0], 
    ['GCBand8', 'gainChangeBand8', 'Gain Change Band 8', ogr.OFTString, 0], 
    ['SCAN_GAP_I', 'SCAN_GAP_INTERPOLATION', 'Scan Gap Interpolation', ogr.OFTInteger, 0], 
    ['ROLL_ANGLE', 'ROLL_ANGLE', 'Roll Angle', ogr.OFTReal, 0], 
    ['FULL_PART', 'FULL_PARTIAL_SCENE', 'Full Partial Scene', ogr.OFTString, 0], 
    ['NADIR_OFFN', 'NADIR_OFFNADIR', 'Nadir/Off Nadir', ogr.OFTString, 0], 
    ['RLUT_FNAME', 'RLUT_FILE_NAME', 'RLUT File Name', ogr.OFTString, 0], 
    ['BPF_N_OLI', 'BPF_NAME_OLI', 'Bias Parameter File Name OLI', ogr.OFTString, 0], 
    ['BPF_N_TIRS', 'BPF_NAME_TIRS', 'Bias Parameter File Name TIRS', ogr.OFTString, 0],
    ['TIRS_SSM', 'TIRS_SSM_MODEL', 'TIRS SSM Model', ogr.OFTString, 0],
    ['TargetPath',  'Target_WRS_Path', 'Target WRS Path', ogr.OFTInteger, 0],
    ['TargetRow', 'Target_WRS_Row', 'Target WRS Row', ogr.OFTInteger, 0],
    ['DataAnom', 'data_anomaly', 'Data Anomaly', ogr.OFTString, 0],
    ['GapPSource', 'gap_phase_source', 'Gap Phase Source', ogr.OFTString, 0],
    ['GapPStat', 'gap_phase_statistic', 'Gap Phase Statistic', ogr.OFTReal, 0], 
    ['L7SLConoff', 'scan_line_corrector', 'Scan Line Corrector', ogr.OFTString, 0], 
    ['SensorAnom', 'sensor_anomalies', 'Sensor Anomalies', ogr.OFTString, 0], 
    ['SensorMode', 'sensor_mode', 'Sensor Mode', ogr.OFTString, 0], 
    ['browse', 'browseAvailable', 'Browse Available', ogr.OFTString, 0], 
    ['browseURL', 'browseURL', 'browseUrl', ogr.OFTString, 0],
    ['MetadatUrl', 'metadataUrl', 'metadataUrl', ogr.OFTString, 0], 
    ['FGDCMetdat', 'fgdcMetadataUrl', 'fgdcMetadataUrl', ogr.OFTString, 0], 
    ['dataAccess', 'dataAccess', 'dataAccessUrl', ogr.OFTString, 0],
    ['orderUrl', 'orderUrl', 'orderUrl', ogr.OFTString, 0],
    ['DownldUrl', 'downloadUrl', 'downloadUrl', ogr.OFTString, 0]]

queryfieldnames = []
fnames = []
#tagvals = []
#tags = []

for element in fieldvaluelist:
    fnames.append(element[0])
    queryfieldnames.append(element[2])
#    tagvals.append([element[1], element[3], element[4]])
#    tags.append(element[1])

if not os.access(shapefile, os.F_OK):
    # Create Shapefile
    
    data_source = driver.CreateDataSource(shapefile)
    layer = data_source.CreateLayer(layername, target, ogr.wkbPolygon)
    for element in fieldvaluelist:
        field_name = ogr.FieldDefn(element[0], element[3])
        if element[4] > 0:
            field_name.SetWidth(element[4])
        layer.CreateField(field_name)
        
    layer.CreateField(ogr.FieldDefn('MaskType', ogr.OFTString)) # 'Fmask' or 'Pixel_QA'
    layer.CreateField(ogr.FieldDefn('Thumb_JPG', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('SR_path', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('BT_path', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('Fmask_path', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('PixQA_path', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('NDVI_path', ogr.OFTString))
    layer.CreateField(ogr.FieldDefn('EVI_path', ogr.OFTString))
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
            field_name = ogr.FieldDefn(fnames[i], fieldvaluelist[i][3])
            if fieldvaluelist[i][4] > 0:
                field_name.SetWidth(fieldvaluelist[i][4])
            layer.CreateField(field_name)

    # Iterate through features and fetch sceneID values
    for feature in layer:
        scenelist.append(feature.GetField("sceneID"))

fielddict = {'BT_path' : {'ext' : '_BT_{}.dat'.format(ieo.projacronym), 'dirname' : ieo.btdir}, 
            'Fmask_path' : {'ext' : '_cfmask.dat', 'dirname' : ieo.fmaskdir},
            'PixQA_path' : {'ext' : '_pixel_qa.dat', 'dirname' : ieo.pixelqadir},
            'NDVI_path' : {'ext' : '_NDVI.dat', 'dirname' : ieo.ndvidir},
            'EVI_path' : {'ext' : '_EVI.dat', 'dirname' : ieo.evidir}}

thumbnails = []
scenes = []
filenum = 1

# get apiKey for USGS EarthExplorer query
apiKey = getapiKey()

# run query

scenedict = scenesearch(apiKey, scenelist)
sceneIDs = scenedict.keys()
print('Total scenes to be added to shapefile: {}'.format(len(sceneIDs)))

#numfiles = len(xmls)
#xmldict = {}

# Download XML files from USGS/EROS
#if not localxmls:
#    print(dlxmls(args.startdate, args.enddate, xmls, ingestdir))

# Parse XML files
#for xml in xmls:
#    print('Processing {}, file number {} of {}.'.format(xml, filenum, numfiles))
#    xmlfile = os.path.join(ingestdir, xml)
#    tree = ET.parse(xmlfile)
#    root = tree.getroot()
##    headervals = []
##    for i in range(len(root[1])):
##        j = root[1][i].tag.find('}') + 1
##        if not root[1][i].tag[j:] in polycoords:
##            headervals.append(root[1][i].tag[j:])
#    
#    numnodes = len(root)
#    for i in range(numnodes):
#        tdict = {} # Version 1.1.1: Now uses a dict rather than absolute position in XML node for fields and values
#        for j in range(len(root[i])):
#            k = root[i][j].tag.find('}') + 1
#            tagname = root[i][j].tag[k:]
#            if not tagname in polycoords:
#                fname = fnames[tags.index(tagname)]
#                tdict[fname] = root[i][j].text
#            elif tagname in polycoords:
#                tdict[tagname] = root[i][j].text
#            else:
#                print('ERROR: Discovered previously unused XML tag {}, logging to error file: '.format(tagname, errorfile))
#                ieo.logerror(xml, 'Unused XML tag: {}'.format(tagname), errorfile = errorfile)
#                errorsfound = True
#        
#        sys.stderr.write('\rProcessing node {} of {}.'.format(i + 1, numnodes))
#        if len(root[i]) > 10:
#            sceneID = tdict['sceneID']
#            xmldict[sceneID] = tdict
#            
#            # Add thumbnail URL to download list
#            if not sceneID in scenelist:
if len(sceneIDs) > 0:
    for sceneID in sceneIDs:
        print('Processing {}, scene number {} of {}.'.format(sceneID, filenum, len(sceneIDs)))
        scenedict = findlocalfiles(sceneID, fielddict, scenedict)
        if scenedict[sceneID]['browseUrl'].endswith('.jpg'):
            dlurl = scenedict[sceneID]['browseUrl']
            thumbnails.append(scenedict[sceneID]['browseUrl'])
        
        print('\nAdding {} to shapefile.'.format(sceneID))
        scenelist.append(sceneID)
        # Determine polygon coordinates in Lat/ Lon WGS-84
        coords = scenedict[sceneID]['coords']
        '''[
[float(tdict['upperLeftCornerLongitude']), float(tdict['upperLeftCornerLatitude'])], 
[float(tdict['upperRightCornerLongitude']), float(tdict['upperRightCornerLatitude'])], 
[float(tdict['lowerRightCornerLongitude']), float(tdict['lowerRightCornerLatitude'])], 
[float(tdict['lowerLeftCornerLongitude']), float(tdict['lowerLeftCornerLatitude'])], [float(tdict['upperLeftCornerLongitude']), float(tdict['upperLeftCornerLatitude'])]] '''
        # create the feature
        feature = ogr.Feature(layer.GetLayerDefn())
        # Add field attributes from XML
#                for k in range(len(root[i])):
#                    if root[i][k].tag[j:] in headervals:
#                        m = tags.index(root[i][k].tag[j:])
#                        feature.SetField(root[i][k].tag[j:], root[i][k].text)
        for key in scenedict[sceneID].keys():
#            print('key = {}, type = {}, value = '.format(key, type(scenedict[sceneID][key])))
#            print(scenedict[sceneID][key])
            if (scenedict[sceneID][key]) and key in queryfieldnames:
                #print('key = {}, type = {}.'.format(key, type(scenedict[sceneID][key])))
                try:
                    if fieldvaluelist[queryfieldnames.index(key)][3] == ogr.OFTDate:
                        feature.SetField(fnames[queryfieldnames.index(key)], scenedict[sceneID][key].year, scenedict[sceneID][key].month, scenedict[sceneID][key].day, scenedict[sceneID][key].hour, scenedict[sceneID][key].minute, scenedict[sceneID][key].second, 100)
                    else:
                        feature.SetField(fnames[queryfieldnames.index(key)], scenedict[sceneID][key])
                except Exception as e:
                    print('Error with SceneID {}, fieldname = {}, value = {}: {}'.format(sceneID, fnames[queryfieldnames.index(key)], scenedict[sceneID][key], e))
                    ieo.logerror(key, e, errorfile = errorfile)
        basename = os.path.basename(dlurl)
        jpg = os.path.join(jpgdir, basename)
        
        
        if not os.access(jpg, os.F_OK) and args.thumbnails:
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
#                for key in scenedict[sceneID].keys():
#                    if scenedict[sceneID][key]:
#                        feature.SetField(fnames[queryfieldnames.index(key)], scenedict[sceneID][key])
                        
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
        filenum += 1

# Update metadata in shapefile
#layer_defn = layer.GetLayerDefn()
#field_names = [layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())]
#
#for field in addfields: #Add any missing fields
#    if not field in field_names:
#        new_field = ogr.FieldDefn(field, ogr.OFTString)
#        layer.CreateField(new_field)

#for feature in layer:
##    updatingfeature = False
#    sceneID = feature.GetField("sceneID")
#    scenedict = findlocalfiles(sceneID, fielddict, scenedict)
#    dlurl = feature.GetField("browseURL")
#    if dlurl:
#        print('Processing scene {}.'.format(sceneID))
#        basename = os.path.basename(dlurl)
#        jpg = os.path.join(jpgdir, basename)
##        for fname in fnames:
##            if feature.GetField(fname) != xmldict[sceneID][fname]:
##                print('Updating metadata for sceneID {}, field {}: {}'.format(sceneID, fname, xmldict[sceneID][fname]))
##                feature.Setfield(fname, xmldict[sceneID][fname])
#       
#        if os.path.isfile(jpg) and jpg != feature.GetField(addfields[0]):
#            print('Updating metadata for sceneID {}, field {}: {}'.format(sceneID, jpg, addfields[0]))
#            feature.SetField(jpg, addfields[0])
#            updatingfeature = True
                
#    for key in scenedict[sceneID].keys():
#        if scenedict[sceneID][key] and scenedict[sceneID][key] != feature.GetField(fnames[queryfieldnames.index(key)]):
#            feature.SetField(fnames[queryfieldnames.index(key)], scenedict[sceneID][key])
#            updatingfeature = True
#    if updatingfeature:
#        layer.SetFeature(feature)

data_source = None

if errorsfound:
    print('Errors were found during script execution. please see the error log file for details: {}'.format(errorfile))

print('Processing complete.')

'''
old code

queryfieldnames = ['Landsat Product Identifier',
 'Landsat Scene Identifier',
 'Acquisition Date',
 'Collection Category',
 'Collection Number',
 'WRS Path',
 'WRS Row',
 'Target WRS Path',
 'Target WRS Row',
 'Nadir/Off Nadir',
 'Roll Angle',
 'Date L-1 Generated',
 'Start Time',
 'Stop Time',
 'Station Identifier',
 'Day/Night Indicator',
 'Land Cloud Cover',
 'Scene Cloud Cover',
 'Ground Control Points Model',
 'Ground Control Points Version',
 'Geometric RMSE Model (meters)',
 'Geometric RMSE Model X',
 'Geometric RMSE Model Y',
 'Image Quality',
 'Processing Software Version',
 'Sun Elevation L1',
 'Sun Azimuth L1',
 'TIRS SSM Model',
 'Data Type Level-1',
 'Sensor Identifier',
 'Panchromatic Lines',
 'Panchromatic Samples',
 'Reflective Lines',
 'Reflective Samples',
 'Thermal Lines',
 'Thermal Samples',
 'Map Projection Level-1',
 'UTM Zone',
 'Datum',
 'Ellipsoid',
 'Grid Cell Size Panchromatic',
 'Grid Cell Size Reflective',
 'Grid Cell Size Thermal',
 'Bias Parameter File Name OLI',
 'Bias Parameter File Name TIRS',
 'Calibration Parameter File',
 'RLUT File Name',
 'Center Latitude',
 'Center Longitude',
 'UL Corner Lat',
 'UL Corner Long',
 'UR Corner Lat',
 'UR Corner Long',
 'LL Corner Lat',
 'LL Corner Long',
 'LR Corner Lat',
 'LR Corner Long',
 'Center Latitude dec',
 'Center Longitude dec',
 'UL Corner Lat dec',
 'UL Corner Long dec',
 'UR Corner Lat dec',
 'UR Corner Long dec',
 'LL Corner Lat dec',
 'LL Corner Long dec',
 'LR Corner Lat dec',
 'LR Corner Long dec']

fnames = ['LandsatPID', 'sceneID', 'sensor', 'acqDate', 'Updated', 'path', 'row', 'CenterLat', 'CenterLong', 'CC', 'CCFull', 'UL_Q_CCA', 'UR_Q_CCA', 'LL_Q_CCA', 'LR_Q_CCA', 'dayOrNight', 'sunEl', 'sunAz', 'StartTime', 'StopTime', 'SN', 'DT_L1', 'cartURL', 'DT_L0RP', 'DATUM', 'ELEVSOURCE', 'ELLIPSOID', 'EPHEM_TYPE', 'CPS_MODEL', 'GCPSVERIFY', 'RMSE_MODEL', 'RMSE_X', 'RMSE_Y', 'RMSEVERIFY', 'GC_SIZE_R', 'GC_SIZE_TH', 'PROJ_L1', 'PROJ_L0RA', 'ORIENT', 'FORMAT', 'L1_AVAIL', 'LINES', 'SAMPLES', 'RESAMP_OPT', 'TH_LINES', 'TH_SAMPLES', 'UTM_ZONE', 'PROCSOFTVE', 'CPF_NAME', 'IMAGE_QUAL', 'DATEL1_GEN', 'GCP_Ver', 'CCLand', 'CollectCat', 'CollectNum', 'flightPath', 'RecStation', 'imageQual1', 'imageQual2', 'gainBand1', 'gainBand2', 'gainBand3', 'gainBand4', 'gainBand5', 'gainBand6H', 'gainBand6L', 'gainBand7', 'gainBand8', 'GCBand1', 'GCBand2', 'GCBand3', 'GCBand4', 'GCBand5', 'GCBand6H', 'GCBand6L', 'GCBand7', 'GCBand8', 'GCSIZE_PAN', 'PAN_LINES', 'PANSAMPLES', 'SCAN_GAP_I', 'ROLL_ANGLE', 'FULL_PART', 'NADIR_OFFN', 'RLUT_FNAME', 'BPF_N_OLI', 'BPF_N_TIRS', 'TIRS_SSM', 'browse', 'browseURL']

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

'''   