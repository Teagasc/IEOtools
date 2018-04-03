#!/usr/bin/env python3
# By Guy Serbin, Environment, Soils, and Land Use Dept., CELUP, Teagasc,
# Johnstown Castle, Co. Wexford Y35 TC97, Ireland
# email: guy <dot> serbin <at> teagasc <dot> ie

# version 1.1.1

# This script creates VRTs from ingested Landsat data and catalogue files

import os, sys, glob, datetime, argparse, ieo
from subprocess import Popen

parser = argparse.ArgumentParser('This script creates VRT files for Landsat data.')

parser.add_argument('-i', '--indir', type = str, default = None, help = 'Input directory. If this is set then --nodataval must also be set. Otherwise, default values will be used.')
parser.add_argument('-o', '--outdir', type = str, default = None, help = 'Data output directory.')
parser.add_argument('-y', '--year', type = int, default = None, help = 'Process secenes only for a specific year.')
parser.add_argument('--overwrite', action = "store_true", help = 'Overwrite existing files.')
parser.add_argument('--nodataval', type = int, default = None, help = 'No data value. This must be set if --indir is also set.')
parser.add_argument('--minrow', type = int, default = 21, help = 'Lowest WRS-2 Row number.')
parser.add_argument('--rowspath', type = int, default = 4, help = 'Max WRS-2 Rows per Path.')
args = parser.parse_args()

if args.indir:
    indirs = [args.indir]
    nodatavals = {args.indir: args.nodataval}
else:
    indirs = [ieo.srdir, ieo.fmaskdir, ieo.btdir, ieo.ndvidir, ieo.evidir, ieo.pixelqadir]
    nodatavals = {ieo.srdir: '-9999', ieo.fmaskdir: '255', ieo.btdir: '-9999', ieo.ndvidir: '0', ieo.evidir: '0', ieo.pixelqadir: '1'}

def makefiledict(dirname, year):
    if args.year:
        flist = glob.glob(os.path.join(dirname, 'L*{}*.dat'.format(args.year)))
    else:
        flist = glob.glob(os.path.join(dirname, 'L*.dat'))
    filedict = {}
    if len(flist) >= 2:
        if len(os.path.basename(flist[0])) > 40:
            rangerow = [7, 10, 17]
        else:
            rangerow = [6, 9, 16]
        if len(flist) == 2 and os.path.basename(flist[0])[rangerow[0]:rangerow[1]] == os.path.basename(flist[1])[rangerow[0]:rangerow[1]]:
            filedict = None
            return filedict
        for f in flist:
            basename = os.path.basename(f)
            if not basename[9:16] in filedict.keys():
                filedict[basename[rangerow[1]:rangerow[2]]] = [f]
            elif not f in filedict[basename[rangerow[1]:rangerow[2]]]:
                filedict[basename[rangerow[1]:rangerow[2]]].append(f)
    return filedict

def makevrtfilename(outdir, filelist):
    numscenes = len(filelist)
    basename = os.path.basename(filelist[0]).replace('.dat', '.vrt')
    if len(basename) < 40:
        startrow = basename[8:9]
        endrow = os.path.basename(filelist[-1])[8:9]
        outbasename = '{}{}{}{}{}'.format(basename[:6], numscenes, startrow, endrow, basename[9:])
    else:
        startrow = basename[9:10]
        endrow = os.path.basename(filelist[-1])[9:10]
        outbasename = '{}{}{}{}{}'.format(basename[:7], numscenes, startrow, endrow, basename[10:])
    vrtfilename = os.path.join(outdir, outbasename)
    return vrtfilename

def writetocsv(catfile, vrt, filelist, d):
    datetuple = datetime.datetime.strptime(d, '%Y%j')
    scenelist = ['None'] * args.rowspath
    for f in filelist:
        if len(f) < 40:
            sceneID = os.path.basename(f)[:21]
            i = int(sceneID[7:9]) - args.minrow
            path = sceneID[3:6]
        else:
            sceneID = os.path.basename(f)[:40]
            i = int(sceneID[8:10]) - args.minrow
            path = sceneID[4:7]
        scenelist[i] = sceneID
    header = 'Date,Year,DOY,Path,R021,R022,R023,R024,VRT'    
    if not os.path.isfile(catfile): # creates catalog file if missing
        with open(catfile, 'w') as output:
            output.write('{}\n'.format(header))    
    outline = '{},{},{},{}'.format(datetuple.strftime('%Y-%m-%d'), datetuple.strftime('%Y'), datetuple.strftime('%j'), path)
    for s in scenelist:
        outline += ',{}'.format(s)
    with open(catfile, 'a') as output:
        output.write('{}\n'.format(outline))
    
def makevrt(filelist, catfile, vrt, datetuple):
    dirname, basename = os.path.split(vrt)
    print('Now creating VRT: {}'.format(basename))
    proclist = ['gdalbuildvrt', '-srcnodata', nodatavals[os.path.dirname(filelist[0])], vrt]    
#    scenelist.append(vrt)
    for f in filelist:
        if f:
            proclist.append(f)
    p = Popen(proclist)
    print(p.communicate())
    writetocsv(catfile, vrt, filelist, datetuple)

today = datetime.datetime.today()
catdir = os.path.join(ieo.catdir, 'Landsat')

for indir in indirs:
    print('Now processing files in subdir {}, number {} of {}.'.format(os.path.basename(indir), indirs.index(indir) + 1, len(indirs)))
    if args.outdir:
        vrtdir = args.outdir
    else:
        vrtdir = os.path.join(indir, 'vrt')
    print('New VRTs will be written to: {}'.format(vrtdir))
    
    if not os.path.isdir(vrtdir):
        os.mkdir(vrtdir)
    catfile = os.path.join(catdir, '{}_vrt.csv'.format(os.path.basename(indir)))
    print('New VRTs created will be logged in: {}'.format(catfile))
        
    filedict = makefiledict(indir, args.year)
    keylist = sorted(filedict.keys())
    if len(keylist) > 0:
        for key in keylist:
            if len(filedict[key]) > 1:
                filedict[key].sort()
                vrt = makevrtfilename(vrtdir, filedict[key])
                if args.overwrite or not os.path.isfile(vrt):
                    print('Now processing {}, number {} of {}.'.format(os.path.basename(vrt), keylist.index(key) + 1, len(keylist)))
                    makevrt(filedict[key], catfile, vrt, key)
                else:
                    print('{} exists and no overwrite set, skipping.'.format(os.path.basename(vrt)))
            else:
                print('An insufficient number of scenes for dat {} exist, skipping.'.format(key))
        
print('Processing complete.')