import os, sys, glob, datetime, argparse, ieo

parser = argparse.ArgumentParser('Create ESA/EOLI download page for missing scenes.')
parser.add_argument('--path', type = int, help = 'WRS-2 Path')
parser.add_argument('--row', type = int, help = 'WRS-2 Row. If this is specified, then --path must also be specified.')
parser.add_argument('--maxcc', default = 100.0, type = float, help = 'Maximum cloud cover in percent')
parser.add_argument('--startdate', type = str, help = 'Starting date, DD/MM/YYYY')
parser.add_argument('--enddate', type = str, help = 'Ending date, DD/MM/YYYY')
parser.add_argument('--sensor', type = str, help = 'Landsat sensor: TM, ETM, ETM_SLC_OFF, OLI, OLI_TIRS, TIRS')
parser.add_argument('--startdoy', type = int, help = 'Starting day of year, 1-366')
parser.add_argument('--enddoy', type = int, help = 'Ending day of year, 1-366. If less than starting day of year then this will be used to span the new year.')
parser.add_argument('--startyear', type = int, help = 'Starting year')
parser.add_argument('--endyear', type = int, help = 'Ending year. If less than starting starting year then these will be swapped.')
parser.add_argument('-o', '--outdir', type = str, default = os.path.join(ieo.catdir, 'LEDAPS_processing_lists'), help = 'Output directory')
args = parser.parse_args()

outdir = args.outdir
infile = os.path.join(ieo.catdir, 'ESA_EOLI_parsed.csv')
today = datetime.datetime.today()
todaystr = today.strftime('%Y%m%d-%H%M%S')
srdir = ieo.srdir
outfile = os.path.join(outdir, 'EOLI_list_{}.html'.format(todaystr))
urllist=[]

localscenelist = []
srlist = glob.glob(os.path.join(srdir, 'L*_ref_ITM.dat'))
for s in srlist:
    localscenelist.append(os.path.basename(s)[:21])

if args.sensor:
    if 'TM' in args.sensor:
        sensor = 'LANDSAT_{}'.format(args.sensor)
    elif not ('OLI' in args.sensor or 'TIRS' in args.sensor):
        print('Error: this sensor is not supported. Acceptable sensors are: TM, ETM, ETM_SLC_OFF, OLI, OLI_TIRS, TIRS. Leaving --sensor blank will search for all sensors. Exiting.')
        exit()
    else:
        sensor = args.sensor
else:
    sensor = ''

pathrows = {}
for i in range(205, 210):
    pr = []
    if i < 209 and i > 206:
        j1 = 22
    else:
        j1 = 21
    for j in range(j1, 25):
        pr.append(str(j))
    pathrows[str(i)] = pr
# elif not args.row:
#     if args.path < 209 and args.path > 206:
#         j1 = 22
#     else:
#         j1 = 21
#     for j in range(j1, 25):
#         pr.append(j)
#     pathrows.append([args.path, pr])
# else:
#     pathrows.append([args.path, [args.row]])


if args.startdoy or args.enddoy:
    if not (args.startdoy and args.enddoy):
        print('Error: if used, both --startdoy and --enddoy must be defined. Exiting.')
        exit()
    
if args.startdate:
    startdate = datetime.datetime.strptime(args.startdate,'%d/%m/%Y')
if args.enddate:
    enddate = datetime.datetime.strptime(args.enddate,'%d/%m/%Y')
# Get EOLI scene list from CSV file
print('Opening {}'.format(infile))
# linenum=1
# print('Searching for scenes from WRS-2 Path %d, Row %d, with a maximum cloud cover of %0.1f%%.'%(args.path,args.row,args.maxcc))

ESAscenes = {}
subdictkeys = 'Path,Row,Date,Year,DOY,CC,SCENE_CENTER,FOOTPRINT,Download_URL,THUMBNAIL_URL'.split(',')

with open(infile,'r') as lines:
    for line in lines:
        if not line.startswith('SceneID'):
            line = line.rstrip('\n').split(',')
            ESAscenes[line[0]] = {}
            for x, y in zip(subdictkeys, line[1:]):
                ESAscenes[line[0]][x] = y

scenelist =  list(ESAscenes.keys())
scenelist.sort()

dldict = {}

for s in scenelist:
    process = True
    if args.startdoy and args.enddoy:
        if int(ESAscenes[s]['DOY']) < args.startdoy or int(ESAscenes[s]['DOY']) > args.enddoy:
            process = False
    if args.maxcc < float(ESAscenes[s]['CC']):
        process = False
    if (not any(s[:16] in x for x in localscenelist)) and process and (not s in dldict.keys()) and (ESAscenes[s]['Path'] in pathrows.keys()):
        if ESAscenes[s]['Row'] in pathrows[ESAscenes[s]['Path']]:
            print('Found SceneID {} for download.'.format(s))
            dldict[s] = ESAscenes[s]['Download_URL']
            for r in pathrows[ESAscenes[s]['Path']]:
                if r != pathrows[ESAscenes[s]['Path']]:
                    s1 = '{}{}{}'.format(s[:7],[r],s[9:16])
                    if not any(s1 in x for x in localscenelist) and not any(s1 in x for x in dldict.keys()):
                        s1list = [x for x in scenelist if s1 in x]
                        if len(s1list) > 0:
                            s1list.sort()
                            s1list.reverse()
                            print('Found SceneID {} for download.'.format(s1list[0]))
                            dldict[s1list[0]] = ESAscenes[s1list[0]]['Download_URL']
                        
        #                 
        # 
        #     
        #     if args.path and args.row:
        #         if path==int(line[1]) and row==int(line[2]) and args.maxcc<=float(line[6]) and len(glob.glob(os.path.join(srdir,'%s*_ref_ITM.dat'%line[0])))==0:
        #             urllist.append(line[9])
        #     else:
        #         if args.maxcc<=float(line[6]) and len(glob.glob(os.path.join(srdir,'%s*_ref_ITM.dat'%line[0])))==0:
        #             urllist.append(line[9])
        # linenum+=1

# linenum=1
dllist = list(dldict.keys())
if len(dllist) > 0:
    dllist.sort()
    print('A total of {} scenes have been identified for download.'.format(len(dllist)))
# if len(urllist)>0:
    print('Writing output to: {}'.format(outfile))
    with open(outfile,'w') as output:
        output.write('<html>\n<head><title>EOLI download list</title></head>\n<body>\n')
        output.write('<p><a href="https://eo-sso-idp.eo.esa.int/idp/AuthnEngine">Login here first, then navigate back to this page</a></p>\n<p><ol>\n')
        for SceneID in dllist:
            output.write('<li><a href="{}">{}</a></li>\n'.format(dldict[SceneID],SceneID))
        output.write('</ol>\n</body>\n</html>')

print('Processing complete.')