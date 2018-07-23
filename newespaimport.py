#!/usr/bin/env python
# By Guy Serbin, Environment, Soils, and Land Use Dept., CELUP, Teagasc,
# Johnstown Castle, Co. Wexford Y35 TC97, Ireland
# email: guy <dot> serbin <at> teagasc <dot> ie

# version 1.1.2

# This script does the following:
# 1. Extracts ESPA-processed Landsat imagery data from tar.gz files
# 2. Virtually stacks surface reflectance (SR) and brightness temperature (BT) bands. 
# 3. Converts SR, BT, and Fmask data from UTM to the local projection.
# 4. Calculates NDVI and EVI for clear land pixels
# 5. Archives tar.gz files after use

import os, sys, glob, datetime, shutil, argparse#, ieo
from osgeo import ogr

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

## main
parser = argparse.ArgumentParser('This script imports ESPA-processed scenes into the local library. It stacks images and converts them to the locally defined projection in IEO, and adds ENVI metadata.')
parser.add_argument('-i','--indir', default = ieo.ingestdir, type = str, help = 'Input directory to search for files. This will be overridden if --infile is set.')
parser.add_argument('-if','--infile', type = str, help = 'Input file. This must be contain the full path and filename.')
parser.add_argument('-f','--fmaskdir', type = str, default = ieo.fmaskdir, help = 'Directory containing FMask cloud masks in local projection.')
parser.add_argument('-q','--pixelqadir', type = str, default = ieo.pixelqadir, help = 'Directory containing Landsat pixel QA layers in local projection.')
parser.add_argument('-o', '--outdir', type = str, default = ieo.srdir, help = 'Surface reflectance output directory')
parser.add_argument('-b', '--btoutdir', type = str, default = ieo.btdir, help = 'Brightness temperature output directory')
parser.add_argument('-n', '--ndvidir', type = str, default = ieo.ndvidir, help = 'NDVI output directory')
parser.add_argument('-e', '--evidir', type = str, default = ieo.evidir, help = 'EVI output directory')
parser.add_argument('-a', '--archdir', type = str, default = ieo.archdir, help = 'Original data archive directory')
parser.add_argument('--overwrite', type = bool, default = False, help = 'Overwrite existing files.')
parser.add_argument('-d', '--delay', type = int, default = 0, help = 'Delay execution of script in seconds.')
parser.add_argument('-r','--remove', type = bool, default = False, help = 'Remove temporary files after ingest.')
args = parser.parse_args()

if args.delay > 0: # if we want to delay execution for whatever reason
    from time import sleep
    print('Delaying execution {} seconds.'.format(args.delay))
    sleep(args.delay)


# Setting a few variables
archdir = args.archdir
fmaskdir = args.fmaskdir
fmasklist = glob.glob(os.path.join(args.fmaskdir, '*.dat'))

reflist = []
scenedict = {}
filelist = []
today = datetime.datetime.today()

# In case there are any errors during script execution
errorfile = 'newespaimport_errors_{}.csv'.format(today.strftime('%Y%m%d_%H%M%S'))
ieo.errorfile = errorfile

def sceneidfromfilename(filename):
    basename = os.path.basename(filename)
    i = basename.find('-')
    if i > 21:
        nsceneid = basename[:i]
        sceneid = nsceneid[:2] + nsceneid[3:10]
        datetuple = datetime.datetime.strptime(nsceneid[10:18], '%Y%m%d')
        sceneid += datetuple.strftime('%Y%j')
    elif i == 21:
        sceneid = basename[:16]
    else:
        sceneid = None
    return sceneid


# Open up ieo.landsatshp and get the existing Product ID, Scene ID, and SR_path status
driver = ogr.GetDriverByName("ESRI Shapefile")
data_source = driver.Open(ieo.landsatshp, 0)
layer = data_source.GetLayer()
for feature in layer:
    sceneID = feature.GetField('sceneID')
    scenedict[sceneID] = {'ProductID' : feature.GetField('LandsatPID'), 'sceneID' : sceneID, 'SR_path' : feature.GetField('SR_path')}
data_source = None

# This look finds any existing processed data 
for dir in [args.outdir, os.path.join(args.outdir, 'L1G')]:
    rlist = glob.glob(os.path.join(args.outdir, '*_ref_{}.dat'.format(ieo.projacronym)))
    for f in rlist:
        if not 'ESA' == os.path.basename(f)[16:19]:
            reflist.append(f)

# Now create the processing list
if args.infile: # This is in case a specific file has been selected for processing
    if os.access(args.infile, os.F_OK) and args.infile.endswith('.tar.gz'):
        print('File has been found, processing.')
        filelist.append(args.infile)
    else:
        print('Error, file not found: {}'.format(args.infile))
        ieo.logerror(args.infile, 'File not found.')
else: # find and process what's in the ingest directory
    for root, dirs, files in os.walk(args.indir, onerror = None): 
        for name in files:
            if name.endswith('.tar.gz') or name.endswith('_sr_band7.img'):
                fname = os.path.join(root, name)
                ssceneID = sceneidfromfilename(name)
                if ssceneID:
                    sslist = [x for x in scenedict.keys() if ssceneID in x]
                    if len(sslist) > 0:
                        for sceneID in sslist:
                            if (args.overwrite or not any(ssceneID in x for x in reflist)) and (not fname in filelist): # any(scenedict[ProductID]['sceneID'][:16] == os.path.basename(x)[:16] for x in reflist)
                                print('Found unprocessed SceneID {}, adding to processing list.'.format(sceneID))
                                filelist.append(fname)

# Now process files that are in the list
numfiles = len(filelist)
print('There are {} reflectance files and {} scenes to be processed.'.format(len(reflist), numfiles))
filenum = 1
for f in filelist:
    basename = os.path.basename(f)
    scene = basename[:16]
    if args.overwrite or not any(scene in x for x in reflist):
        try:
            print('\nProcessing archive {}, file number {} of {}.\n'.format(f, filenum, numfiles))
            ieo.importespa(f, remove = args.remove, overwrite = args.overwrite)
        except Exception as e:
            print('There was a problem processing the scene. Adding to error list.')
            print(e)
            ieo.logerror(f, e)
    else:
        print('Scene {} has already been processed, skipping file number {} of {}.'.format(scene, filenum, numfiles))
    filenum += 1

print('Processing complete.')