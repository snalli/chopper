# The monitor is used to monitor the FS fragmentation status.
# What I want to see is, generally, how's the metadata. This may include:
#
#  SIZE of inode and extent tree. (number of inode block and extent tree
#  block). This can be find by debugfs "dump_extents [-n] [-l] filespec".
#  But you have to do it for ALL files in the file system, which might be
#  slow. I haven't got a better approach. A good indicator of metadata
#  problem is #_metadata_block/#_data_block. This should be very informative
#  about the aging of a file system which causes metadata disaster.
#       I expect the following from the output of this per file:
#       
#       filepath create_time n_metablock n_datablock metadata_ratio filebytes
#
#  Extent fragmentation overview. This can be obtained by e2freefrag. This
#  should give me a good sense of how fragemented the FS is. The acceleration
#  rate of fragmentation might be a good indicator of whether a workload
#  can cause metadata problem. (Because of fragmentation, physical blocks
#  might not be able to allocated contiguously, then it needs two or more
#  extents to the logically contiguous blocks.)
#       I expect the following from the output of this per FS:
#       JUST LIKE THE ORIGINAL OUTPUT BUT FORMAT IT A LITTLE BIT

import subprocess
from time import strftime, localtime, sleep
import re
import shlex
import os
import pprint

import btrfs_db_parser
import xfs_db_parser
import dataframe

class cd:
    """Context manager for changing the current working directory"""
    def __init__(self, newPath):
        self.newPath = newPath

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)

def fill_white_space(path, filler="_"):
    path.strip()
    return path.replace(" ", filler)

class FSMonitor:
    """
    This monitor probes the ext4 file system and return information I 
    want in a nice format.
    """
    def __init__(self, dn, mp, ld="/tmp", cw=20, filesystem='ext4'):
        self.devname = dn   # this should be the device name of the partition 
        self.mountpoint = mp # please only provide path without mountpoint
                             # when using this class.
        self.col_width = cw
        self.logdir = ld
        self.resetMonitorTime()
        self.resetJobID()
        self.filesystem = filesystem # the file system this monitor monitors
    
    def resetMonitorTime(self, monitorid=""):
        "monitor_time is used to identify each data retrieval"
        if monitorid == "":
            self.monitor_time = strftime("%Y-%m-%d-%H-%M-%S", localtime())
        else:
            self.monitor_time = monitorid

    def resetJobID(self, jobid="DefaultJOBID"):
        self.jobid = jobid

    def _spliter_dumpfs(self, line):
        line = line.replace(",", " ")
        elems = line.split(":")[1]
        elems = elems.split()

        new_elems = [] # [[a0,a1],[b0,b1]...]
        for elem in elems:
            e = elem.split("-")
            elen = len(e)
            if elen == 2:
                new_elems.append(e)
            elif elen == 1:
                e = e*2
                new_elems.append(e)
            else:
                print "wrong split", elem
                exit(1)
        return new_elems

    def dumpfsSummary(self):
        if self.filesystem != 'ext4':
            return 
        print "dumpfs..."
        cmd = ["dumpe2fs", "-h", self.devname]
        proc = subprocess.Popen(cmd, 
                                stdout=subprocess.PIPE)

        print "dumpfs finished. Parsing results..."
        proc.wait()
        return proc.communicate()[0]

    def dumpfs(self):
        if self.filesystem != 'ext4':
            return 

        print "dumpfs..."
        cmd = ["dumpe2fs", self.devname]
        proc = subprocess.Popen(cmd, 
                                stdout=subprocess.PIPE)

        print "dumpfs finished. Parsing results..."
        freeblocks = []
        freeinodes = []
        for line in proc.stdout:
            if line.startswith("  Free blocks:"):
                freeblocks += self._spliter_dumpfs(line)
            elif line.startswith("  Free inodes:"):
                freeinodes += self._spliter_dumpfs(line)
            else:
                pass
        proc.wait()

        # initialize
        freeblocks_df = dataframe.DataFrame(header=['start', 'end'],
                                           table=freeblocks)
        freeinodes_df = dataframe.DataFrame(header=['start', 'end'],
                                           table=freeinodes)

        # add additional columns 
        freeblocks_df.addColumn(key="monitor_time",
                                       value=self.monitor_time)
        freeblocks_df.addColumn(key="jobid",
                                       value=self.jobid)
        freeblocks_df.addColumn(key="HEADERMARKER_freeblocks",
                                       value="DATAMARKER_freeblocks")

        freeinodes_df.addColumn(key="monitor_time",
                                       value=self.monitor_time)
        freeinodes_df.addColumn(key="jobid",
                                       value=self.jobid)
        freeinodes_df.addColumn(key="HEADERMARKER_freeinodes",
                                       value="DATAMARKER_freeinodes")

        return {"freeblocks":freeblocks_df, "freeinodes":freeinodes_df}

    def e2freefrag(self):
        if self.filesystem != 'ext4':
            return 

        cmd = ["e2freefrag", self.devname]
        proc = subprocess.Popen(cmd,
                           stdout=subprocess.PIPE)
        proc.wait()

        part = 0
        sums_dict = {}
        hist_table = ""
        hist_df = dataframe.DataFrame()
        for line in proc.stdout:
            if part == 0:
                if "HISTOGRAM" in line:
                    part = 1
                    continue
                mo = re.search( r'(.*): (\d+)', line, re.M)
                if mo:
                    keyname = mo.group(1)
                    keyname = keyname.replace('.', '')
                    keyname = "_".join(keyname.split())
                    sums_dict[keyname] = mo.group(2)
            elif part == 1:
                # This part is the histogram.
                line = line.strip()
                if "Extent Size" in line:
                    hist_table = "Extent_start Extent_end  Free_extents   Free_Blocks  Percent"
                    hist_df.header = hist_table.split()
                    continue
                fline = re.sub(r'[\-:\n]', "", line)
                fline = re.sub(r'\.{3}', "", fline)
                row = fline.split()
                hist_df.addRowByList(row)

        hist_df.addColumns(keylist = ["HEADERMARKER_freefrag_hist",
                                      "monitor_time",
                                      "jobid"],
                           valuelist = ["DATAMARKER_freefrag_hist",
                                        self.monitor_time,
                                        self.jobid])

        # convert dict to data frame
        sums_df = dataframe.DataFrame(header=sums_dict.keys(),
                                      table=[sums_dict.values()])
        sums_df.addColumn(key="HEADERMARKER_freefrag_sum",
                          value="DATAMARKER_freefrag_sum")
        sums_df.addColumn(key="monitor_time",
                          value=self.monitor_time)
        sums_df.addColumn(key="jobid",
                          value=self.jobid)
                                      
                 
        return {"FragSummary":sums_df, "ExtSizeHistogram":hist_df}

   
    def imap_of_a_file(self, filepath):
        if self.filesystem != 'ext4':
            return 
        #cmd = "debugfs " + self.devname + " -R 'imap " + filepath + "'"
        cmd = ['debugfs', self.devname, '-R', 'imap "' + filepath + '"']
        print cmd, '......'
        #cmd = shlex.split(cmd)
        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

        imapdict = {}
        for line in proc.stdout:
            #print line
            if "block group" in line:
                nums = re.findall(r'\d+', line)
                if len(nums) != 2:
                    print "Error parsing imap"
                    exit(1)
                imapdict['inode_number'] = nums[0] 
                imapdict['group_number'] = nums[1]
            elif 'located at block' in line:
                items = line.split()
                imapdict['block_number'] = items[3].rstrip(',')
                imapdict['offset_in_block'] = items[5]

        proc.wait()
        #print imapdict
        return imapdict


    def dump_extents_of_a_file(self, filepath):
        "This function only gets ext list for this file"
        if self.filesystem != 'ext4':
            return 
        #print "filepath:", filepath 
        #cmd = "debugfs " + self.devname + " -R 'dump_extents " + filepath + "'"
        cmd = ['debugfs', self.devname, '-R', 'dump_extents "' + filepath + '"']
        #print cmd, '......'
        #cmd = shlex.split(cmd)
        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

        ext_list = [] # Use list here in case I want to extract data in Python
        header = []

        max_level = 0
        df_ext = dataframe.DataFrame()
        header = ["Level_index", "Max_level", 
                 "Entry_index", "N_Entry",
                 "Logical_start", "Logical_end",
                 "Physical_start", "Physical_end",
                 "Length", "Flag"]
        df_ext.header = header
        for line in proc.stdout:
            #print "LLL:", line,
            if "Level" in line:
                pass
            else:
                savedline = line
                line = re.sub(r'[/\-]', " ", line)
                tokens = line.split()
                if len(tokens) == 8:
                    # there is no physical end
                    tokens.insert(7, tokens[6]) #TODO: this is dangerous

                d = {}
                for i in range(9):
                    try:
                        d[ header[i] ] = tokens[i]
                    except:
                        print savedline
                        print "token:", tokens
                        print "header:", header # having a try-except can grant you
                                            # the opportunity to do something 
                                            # after bad thing happen
                
                if len(tokens) == 10:
                    d["Flag"] = tokens[10]
                else:
                    d["Flag"] = "NA"
                
                df_ext.addRowByDict(d)

        proc.wait()


        # Put the location of the inode the df_ext, level_index as -1 to
        # indicate that it is a inode

        imapdict = self.imap_of_a_file(filepath)
        d = {}
        d['Level_index'] = '-1'
        d['Max_level'] = '-1'
        d['Entry_index'] = 'NA'
        d['N_Entry'] = 'NA'
        d['Logical_start'] = 'NA'
        d['Logical_end'] = 'NA'
        d['Physical_start'] = imapdict['block_number']
        d['Physical_end'] = imapdict['block_number']
        d['Length'] = '1'
        d['Flag'] = 'NA'

        df_ext.addRowByDict(d)

        df_ext.addColumn(key = "filepath",
                         value = fill_white_space(filepath))
        df_ext.addColumn(key = "HEADERMARKER_extlist",
                         value = "DATAMARKER_extlist")
        df_ext.addColumn(key = "jobid",
                         value = self.jobid)
        df_ext.addColumn(key = "monitor_time",
                         value = self.monitor_time)

        return df_ext

    def setBlock(self, blockn, count):
        if self.filesystem != 'ext4':
            return 

        cmd = "debugfs " + self.devname + \
                " -w -R 'setb " + str(blockn) + " " + str(count) + "'"
        cmd = shlex.split(cmd)

        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)
        proc.wait()
        return proc.returncode

    def isAllBlocksInUse(self, blockn, count):
        "if any of the blocks is not in use, return false. return true otherwise"
        if self.filesystem != 'ext4':
            return 

        cmd = "debugfs " + self.devname + \
                " -w -R 'testb " + str(blockn) + " " + str(count) + "'"
        cmd = shlex.split(cmd)

        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

        for line in proc.stdout:
            if 'not' in line:
                return False
        proc.wait()

        return True



    def dumpextents_sum(self, filepath):
        "TODO: merge this with dump_extents_of_a_file()"

        if self.filesystem != 'ext4':
            return 

        #cmd = "debugfs " + self.devname + " -R 'dump_extents " + filepath + "'"
        #cmd = ['debugfs', self.devname, '-R', '"dump_extents ' + filepath + '"']
        cmd = ['debugfs', self.devname, '-R', 'dump_extents "' + filepath + '"']
        #print cmd, "........."
        #cmd = shlex.split(cmd)

        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

        header = []
        n_entries = [0] * 3 # n_entries[k] is the number of entries at level k
                            # it can be used to calculate number of 
                            # internal/leaf nodes
        max_level = 0
        exttable = ""
        header = ["Level_index", "Max_level", 
                 "Entry_index", "N_Entry",
                 "Logical_start", "Logical_end",
                 "Physical_start", "Physical_end",
                 "Length", "Flag"]
        for line in proc.stdout:
            #print "LLL:", line,
            if "Level" in line:
                pass
            else:
                savedline = line
                line = re.sub(r'[/\-]', " ", line)
                tokens = line.split()
                if len(tokens) == 8:
                    # there is no physical end
                    tokens.insert(7, "NA") #TODO: this is dangerous

                d = {}
                for i in range(9):
                    try:
                        d[ header[i] ] = tokens[i]
                    except:
                        print savedline
                        print "token:", tokens
                        print "header:", header # having a try-except can grant you
                                            # the opportunity to do something 
                                            # after bad thing happen
                
                if len(tokens) == 10:
                    d["Flag"] = tokens[10]
                else:
                    d["Flag"] = "NA"

                n_entries[ int(d["Level_index"]) ] = int( d["N_Entry"] )
                max_level = int( d["Max_level"] )
                
        #print "..... finished stdout parsing .... "
        proc.terminate()
        #print "..... after terminating .... "



        # calculate number of meatadata blocks
        # only 1st and 2nd levels takes space. 
        # How to calculate:
        #   if there is only 1 level (root and level 1).
        #   the number of entires in level 0 indicates the
        #   number of nodes in level 1.
        #   Basically, the number of entries in level i
        #   equals the number of ETB of the next level
        n_metablock = 0
        if max_level == 0:
            # the tree has no extent tree block outside of the inode
            n_metablock = 0
        else:
            for n in n_entries[0:max_level]:
                n_metablock += n
        
        dumpdict = {}
        dumpdict["filepath"] = fill_white_space(filepath)
        dumpdict["n_metablock"] = n_metablock
        others = self.filefrag(filepath)
        if others.has_key('nblocks'):
            dumpdict["n_datablock"] = others["nblocks"]
        else:
            dumpdict["n_datablock"] = 'NA'

        if others.has_key('nbytes'):
            dumpdict["filebytes"] = others["nbytes"]
        else:
            dumpdict["filebytes"] = 'NA'
    
        #print "Reached end of debugfs...."
        return dumpdict

    def filefrag(self, filepath):
        if self.filesystem != 'ext4':
            return 

        fullpath = os.path.join(self.mountpoint, filepath)  
        cmd = ["filefrag", "-sv", fullpath]
        #print cmd
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)

        mydict = {}
        for line in proc.stdout:
            if line.startswith("File size of"):
                #print line
                line = line.split(" is ")[1]
                #print line
                nums = re.findall(r'\d+', line)
                if len(nums) != 3:
                    print "filefrag something wrong"
                    exit(1)
                mydict["nbytes"] = nums[0]
                mydict["nblocks"] = nums[1]
                mydict["blocksize"] = nums[2]

        return mydict

    def getAllInodePaths(self, rootdir="."):
        "it returns paths of all files and diretories"
        rootpath = os.path.join(self.mountpoint)
        paths = []
        with cd(rootpath):
            cmd = ['find', rootdir]
            proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

            for line in proc.stdout:
                paths.append(line.replace("\n", ""))
            proc.wait()
            
        return paths

    def getExtentList_of_a_dir(self, rootdir="."):
        if self.filesystem != 'ext4':
            return 

        files = self.getAllInodePaths(rootdir)
        #print files
        #exit(1)
        df = dataframe.DataFrame()
        for f in files:
            if len(df.header) == 0:
                df = self.dump_extents_of_a_file(f)
            else:
                df.table.extend( self.dump_extents_of_a_file(f).table )
        return df


    def getPerFileBlockCounts(self, rootdir="."):
        if self.filesystem != 'ext4':
            return 

        files = self.getAllInodePaths(rootdir)
        counts_df = dataframe.DataFrame()
        for f in files:
            d = self.dumpextents_sum(f) 
            if len(counts_df.header) == 0:
                counts_df.header = d.keys()
            counts_df.addRowByDict(d)

        counts_df.addColumns(keylist=["HEADERMARKER_extstats",
                                     "monitor_time",
                                     "jobid"],
                            valuelist=["DATAMARKER_extstats",
                                     self.monitor_time,
                                     self.jobid])
           
        return counts_df
        
    def getFSBlockCount(self, df_files):
        "df_files has number of metablocks datablocks of each file"
        if self.filesystem != 'ext4':
            return 

        if len(df_files.table) == 0:
            return ""

        fs_nmetablocks = 0
        fs_ndatablocks = 0
        nmetaindex = df_files.header.index('n_metablock')
        ndataindex = df_files.header.index('n_datablock')

        for row in df_files.table:
            if row[nmetaindex] == 'NA' or row[ndataindex] == 'NA':
                fs_nmetablocks = 'NA'
                fs_ndatablocks = 'NA'
                break
            fs_nmetablocks += int(row[nmetaindex])
            fs_ndatablocks += int(row[ndataindex])

        headerstr = "fs_nmetablocks fs_ndatablocks monitor_time HEADERMARKER_extstatssum jobid"
        valuelist = [fs_nmetablocks, fs_ndatablocks, self.monitor_time, 
                    'DATAMARKER_extstatssum', self.jobid]
        fsblkcount_df = dataframe.DataFrame(
                            header=headerstr.split(),
                            table=[valuelist])
        return fsblkcount_df

    def widen(self, s):
        return s.ljust(self.col_width)

    def dict2table(self, mydict):
        mytable = ""

        header = ""
        for keyname in mydict:
            header += self.widen(keyname) + " "
        header += self.widen("monitor_time") + " HEADERMARKER_freefrag_sum\n"

        vals = ""    
        for keyname in mydict:
            vals += self.widen(mydict[keyname]) + " "
        vals += self.widen(str(self.monitor_time)) + " DATAMARKER_freefrag_sum\n"

        return header + vals

    def display(self, savedata=False, logfile="", monitorid="", jobid="myjobid"):

        self.resetMonitorTime(monitorid=monitorid)
        self.resetJobID(jobid=jobid)

        ret_dict = {'d_span':'NA',
                    'physical_layout_hash':'NA'}
        if savedata: 
            if logfile == "":
                filename = self.monitor_time + ".result"
            else:
                filename = logfile
            fullpath = os.path.join(self.logdir, filename)
            f = open(fullpath, 'w')

        if self.filesystem == 'ext4':
            ######################
            # get per file block count
            #df_bcounts = self.getPerFileBlockCounts()
            #if savedata and df_bcounts != None:
                #extstats_header = "----------- per file block counts  -------------\n"
                #f.write(extstats_header + df_bcounts.toStr())

            # FS block count
            #df_fscounts = self.getFSBlockCount(df_bcounts)
            #if savedata and df_fscounts != None:
                #h = "------------- FS block counts ---------------\n"
                #f.write(h+df_fscounts.toStr())
            
            ######################
            # get extents of all files
            extlist = self.getExtentList_of_a_dir(rootdir='./pid00000.dir00000')
            extlist = extlist_translate_new_format(extlist)

            if savedata and extlist != None:
                h = "---------------- extent list -------------------\n"
                f.write(extlist.toStr())
            ret_dict['d_span'] = get_d_span_from_extent_list(extlist, 
                                    './pid00000.dir00000/pid.00000.file.')
            ret_dict['physical_layout_hash'] = \
                get_physical_layout_hash(extlist, 
                                         'file', 
                                         merge_contiguous=True)

            ######################
            # e2freefrag
            #frag = self.e2freefrag()
            #if savedata and frag != None:
                #frag0_header    = "-----------  Extent summary  -------------\n"
                #frag1_header    = "----------- Extent Histogram   -------------\n"
                #f.write(frag0_header + frag["FragSummary"].toStr())
                #f.write(frag1_header + frag["ExtSizeHistogram"].toStr())

            ######################
            # dumpfs
            #freespaces = self.dumpfs()
            #if savedata and frag != None:
                #dumpfs_header   = "----------- Dumpfs Header ------------\n"
                #f.write(dumpfs_header + freespaces['freeblocks'].toStr())
                #f.write(dumpfs_header + freespaces['freeinodes'].toStr())

        elif self.filesystem == 'xfs':
            df_ext = self.xfs_getExtentList_of_a_dir()
            df_ext = extlist_translate_new_format(df_ext)
            
            if savedata and df_ext != None:
                df_ext.addColumns(keylist=["HEADERMARKER_extlist",
                                         "monitor_time",
                                         "jobid"],
                                  valuelist=["DATAMARKER_extlist",
                                         self.monitor_time,
                                         self.jobid])
                h = "---------------- extent list -------------------\n"
                f.write( h + df_ext.toStr() )
            ret_dict['d_span'] = get_d_span_from_extent_list(df_ext, 
                                            './pid00000.dir00000/pid.00000.file.')
            ret_dict['physical_layout_hash'] \
                    = get_physical_layout_hash(df_ext, 
                                               'file', 
                                               merge_contiguous=True)
        elif self.filesystem == 'btrfs':
            tree_lines = btrfs_db_parser.btrfs_debug_tree(self.devname)

            tree_parser = btrfs_db_parser.TreeParser(tree_lines)
            df_dic = tree_parser.parse()
            df_rawext = df_dic['extents']
            df_chunk = df_dic['chunks']
            df_map = btrfs_db_parser.get_filepath_inode_map(
                        self.mountpoint, "./")

            #print df_ext.toStr()
            #print df_chunk.toStr()


            df_ext = btrfs_convert_rawext_to_ext(df_rawext, df_chunk, df_map)

            ret_dict['d_span'] = get_d_span_from_extent_list(df_ext, 
                                    './pid00000.dir00000/pid.00000.file.')
            ret_dict['physical_layout_hash'] \
                    = get_physical_layout_hash(df_ext, 
                                               'file', 
                                               merge_contiguous=True)

            if savedata:
                df_ext.addColumns(keylist=["HEADERMARKER_extlist",
                                         "monitor_time",
                                         "jobid"],
                                  valuelist=["DATAMARKER_extlist",
                                         self.monitor_time,
                                         self.jobid])

                h = "---------------- extent list -------------------\n"
                f.write( h + df_ext.toStr())

        else:
            print "Unsupported file system."
            exit(1)
        
        if savedata:
            f.flush()
            f.close()
        
        return ret_dict

    def stat_a_file(self, filepath):
        filepath = os.path.join(self.mountpoint, filepath)
        cmd = ["stat",  filepath]

        proc = subprocess.Popen(cmd, 
                                stdout=subprocess.PIPE)
        output = proc.communicate()[0] # communicate() uses buffer. Don't use it
        lines = output.strip()
        lines = lines.split('\n')
       
        stat_dict = {}
        for line in lines:
            #print line
            if not "Inode" in line:
                continue
            mo = re.search( r'Inode:\s(\d+)', line, re.M)
            if mo:
                print mo.group(1)
                inode_number = mo.group(1)
                stat_dict['inode_number'] = inode_number
        return stat_dict

    def xfs_get_extentlist_of_a_file(self, filepath):
        inode_number = self.stat_a_file(filepath)['inode_number']
        df = xfs_db_parser.xfs_get_extent_tree(inode_number, self.devname)
        df.addColumn(key = "filepath",
                         value = fill_white_space(filepath))
        return df

    def xfs_getExtentList_of_a_dir(self, rootdir="."):
        "rootdir is actually relative to mountpoint. Seems bad"
        files = self.getAllInodePaths(rootdir)
        print files
        df = dataframe.DataFrame()
        for f in files:
            #print "UU____UU"
            if len(df.header) == 0:
                df = self.xfs_get_extentlist_of_a_file(f)
            else:
                df.table.extend( self.xfs_get_extentlist_of_a_file(f).table )
        return df


############################################
def get_physical_layout_hash(df_ext, filter_str, merge_contiguous=False):
    """
    It only cares about physical block positions.
    It has nothing to do with filename, logical address of blocks..

    Just sort the physical block start and end, then do a hash
    Inlcuding inode, ETB, and data extent!

    Another way to find layout is to get all the free blocks and do
    hash on them. It is more straight free space.
    """
    hdr = df_ext.header

    phy_blocks = []
    for row in df_ext.table:
        if filter_str in row[hdr.index('filepath')]:
            #print row
            physical_start = int(row[hdr.index('Physical_start')])
            physical_end = int(row[hdr.index('Physical_end')])
        
            phy_blocks.append( physical_start )
            phy_blocks.append( physical_end )
    
    # There can be over lap between extents for inode and only for inode
    # block number can be overlapped in extent
    # block number of the same extent always next to each other
    phy_blocks.sort()

    if merge_contiguous:
        # the block number are ALWAYS in pair, even after sorting
        # [start, end, start, end, start, end, ...]
        # This may not work for BTRFS!
        merged = []
        n = len(phy_blocks)
        assert n % 2 == 0
        for i in range(0, n, 2):
            # i is start of an extent
            if i == 0: # the first extent
                merged.append( phy_blocks[i] )
                merged.append( phy_blocks[i+1] )
                continue
            if phy_blocks[i] == phy_blocks[i-1] + 1:
                # can be merged 
                merged[-1] = phy_blocks[i+1]
            elif phy_blocks[i] == phy_blocks[i-2] and \
                    phy_blocks[i+1] == phy_blocks[i-1]:
                # hmm... duplicated extent. can only happen to inode
                pass # do nothing
            else:
                # cannot be merged
                merged.append( phy_blocks[i] )
                merged.append( phy_blocks[i+1] )
        phy_blocks = merged

    return hash( str(phy_blocks) )

def get_inode_num_from_dfmap(filepath, df_map):
    hdr = df_map.header
    for row in df_map.table:
        if row[hdr.index('filepath')] == filepath:
            return row[hdr.index('inode_number')]

    return None

def get_all_vir_ranges_of_an_inode(inode_number, df_rawext):
    hdr = df_rawext.header

    ranges = []
    for row in df_rawext.table:
        if str(row[hdr.index('inode_number')]) == str(inode_number):
            d = {
                    'virtual_start': int(row[hdr.index('Virtual_start')]),
                    'length': int(row[hdr.index('Length')])
                }
            ranges.append( d )

    return ranges

def btrfs_df_map_to_dic(df_map):
    d = {}
    hdr = df_map.header
    
    for row in df_map.table:
        filepath = row[hdr.index('filepath')]
        inode_number = row[hdr.index('inode_number')]

        d[str(inode_number)] = filepath

    return d


def btrfs_convert_rawext_to_ext(df_rawext, df_chunk, df_map):
    #print df_rawext.toStr()
    #print df_chunk.toStr()
    #print df_map.toStr()

    dic_map = btrfs_df_map_to_dic(df_map)

    hdr = df_rawext.header

    devices = set()
    df_ext = dataframe.DataFrame()
    df_ext.header = ['Level_index',
                    'Max_level',
                    'Entry_index',
                    'N_Entry',
                    'Virtual_start',
                    'Logical_start',
                    'Logical_end',
                    'Physical_start',
                    'Physical_end',
                    'Length',
                    'Flag',
                    'filepath']
    for row in df_rawext.table:
        rowdic = {}
        for col in hdr:
            rowdic[col] = row[hdr.index(col)]
        #print rowdic

        phy_starts = btrfs_db_parser.virtual_to_physical( rowdic['Virtual_start'], df_chunk ) 
        
        for stripe in phy_starts:
            devices.add( stripe['devid'] )
            assert len(devices) == 1, 'we only allow one device at this time'
            rowdic['Physical_start'] = stripe['physical_addr']
            rowdic['Physical_end'] = stripe['physical_addr'] + \
                                      int( rowdic['Length'] ) 
            rowdic['Logical_end'] = int(rowdic['Logical_start']) + \
                                      int( rowdic['Length'] )
            rowdic['Level_index'] = 0
            rowdic['Max_level'] = 0
            rowdic['Entry_index'] = 0
            rowdic['N_Entry'] = 0
            rowdic['filepath'] = dic_map[str( rowdic['inode_number'] )]
            rowdic['Flag'] = "NA"

            df_ext.addRowByDict( rowdic )

    return df_ext

def extlist_translate_new_format(df_ext):
    """
    Use ending of file and new unit(byte)
    Only df_ext of ext4 and xfs need this, btrfs already
    uses byte as unit. 
    But does btrfs use the new style of ending?
    """
    df_ext = extlist_lastblock_to_nextblock(df_ext)
    df_ext = extlist_block_to_byte(df_ext)
    return df_ext

def extlist_lastblock_to_nextblock(df_ext):
    """
    for ext4 and xfs, the Logical_end and Physical_end point
    to the last block of the file. This is not convenient when
    we translate the unit from block to byte. 
    so in this function, we shift the _end to point to the
    next block of the file (out of the file), kind of like
    the .end() of iterator in C++.
    For example, it was 8,8 for a file, indicating, the first
    and the last block of the file is 8.
    After the translating of this file, it is 8,9.
    """
    colnames = ['Logical_end', 'Physical_end']

    hdr = df_ext.header
    for row in df_ext.table:
        for col in colnames:
            x = row[hdr.index(col)]
            if x != 'NA':
                x = int(x) + 1 
            row[hdr.index(col)] = x
    return df_ext


def extlist_block_to_byte(df_ext):
    """
    Translate the unit from block to byte for extent list
    Translated:
        Logical_start Logical_end Physical_start Physical_end
    This function should be used as soon as the df_ext is created
    so all the later functions that use this df_ext can treat it
    as byte.
    """
    BLOCKSIZE = 4096

    colnames = ['Logical_start', 'Logical_end', 
                'Physical_start', 'Physical_end']

    hdr = df_ext.header
    for row in df_ext.table:
        for col in colnames:
            x = row[hdr.index(col)]
            if x != 'NA':
                x = int(x) * BLOCKSIZE
            row[hdr.index(col)] = x
    return df_ext

def get_d_span_from_extent_list(df_ext, filepath):
    hdr = df_ext.header

    byte_max = -1
    byte_min = float('Inf')
    for row in df_ext.table:
        if filepath in row[hdr.index('filepath')] and \
           row[hdr.index('Level_index')] != '-1'  and \
           row[hdr.index('Level_index')] == row[hdr.index('Max_level')]:
            #print row
            physical_start = int(row[hdr.index('Physical_start')])
            physical_end = int(row[hdr.index('Physical_end')])
            mmin = min(physical_start, physical_end)
            mmax = max(physical_start, physical_end)

            if mmin < byte_min:
                byte_min = mmin
            if mmax > byte_max:
                byte_max = mmax

    if byte_max == -1:
        # no extent found
        return 'NA'
    else:
        return byte_max - byte_min 

def stat_a_file(filepath):
    filepath = os.path.join(filepath)
    cmd = ["stat",  filepath]

    proc = subprocess.Popen(cmd, 
                            stdout=subprocess.PIPE)
    output = proc.communicate()[0] # communicate() uses limited buffer
    lines = output.strip()
    lines = lines.split('\n')
   
    stat_dict = {}
    for line in lines:
        #print line
        if not "Inode" in line:
            continue
        mo = re.search( r'Inode:\s(\d+)', line, re.M)
        if mo:
            #print mo.group(1)
            inode_number = mo.group(1)
            stat_dict['inode_number'] = inode_number
    return stat_dict

def get_all_paths(mountpoint, dir):
    "it returns paths of all files and diretories"
    paths = []
    with cd(mountpoint):
        cmd = ['find', dir]
        proc = subprocess.Popen(cmd, stdout = subprocess.PIPE)

        for line in proc.stdout:
            paths.append(line.replace("\n", ""))
        proc.wait()
    return paths


# Testing
#m = FSMonitor('/dev/loop0', '/mnt/loopmount/')
#print m.xfs_db_commands(['convert ino 4194432 fsblock'])
#m.xfs_convert_ino_to_fsb(131)
#m.xfs_extents_of_a_file('/mnt/scratch/initrd.img-3.2.16emulab1')
#m.stat_a_file("/mnt/scratch")
#print m.xfs_getExtentList_of_a_dir("/mnt/scratch").toStr()
#m.imap_of_a_file('./pid00000.dir00000/pid.00000.file.00000')
#print m.dump_extents_of_a_file('./pid00000.dir00000/pid.00000.file.00000').toStr()

