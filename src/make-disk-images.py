import subprocess
import time
import MWpyFS
import os
import sys
import itertools
import pprint

def ParameterCominations(parameter_dict):
    """
    Get all the cominbation of the values from each key
    http://tinyurl.com/nnglcs9

    Input: parameter_dict={
                    p0:[x, y, z, ..],
                    p1:[a, b, c, ..],
                    ...}
    Output: [
             {p0:x, p1:a, ..},
             {..},
             ...
            ]
    """
    d = parameter_dict
    return [dict(zip(d, v)) for v in itertools.product(*d.values())]

def produce_new_inputfile(orig_path, 
                          new_path,
                          config_dict):
    """
    config_dict = {
                    'FSused:': [4, 'GB'] 
                  }
    """
    orig_f = open(orig_path, 'r')
    new_f = open(new_path, 'w')

    for line in orig_f:
        #print line,
        items = line.split()
        #print items
        if len(items) > 0 and items[0] in config_dict.keys():
            newline = [items[0]] + config_dict[items[0]]
            newline = [str(x) for x in newline]
            newline = ' '.join( newline )
            newline += '\n'
        else:
            newline = line
        #print newline,
        new_f.write( newline )
    orig_f.close()
    new_f.close()

def run_impressions(config_dict):
    inputpath = '/tmp/newinputfile'
    produce_new_inputfile('./impressions-v1/inputfile.orig',
                          inputpath,
                          config_dict)
    cmd = ['./impressions-v1/impressions',
           inputpath]
    proc = subprocess.Popen(cmd)
    proc.wait()

def make_file_system(fstype, disksize):
    """
    fstype: ext4, xfs, btrfs
    disksize: in Bytes
    """
    if not os.path.exists("/mnt/mytmpfs"):
        print "/mnt/mytmpfs does not exist. Creating..."
        os.mkdir("/mnt/mytmpfs")
    MWpyFS.FormatFS.makeLoopDevice(
            devname="/dev/loop0",
            tmpfs_mountpoint="/mnt/mytmpfs",
            sizeMB=disksize/(1024*1024))

    print "Loop device has been made :)"

    if not os.path.exists("/mnt/scratch"):
        print "/mnt/scratch does not exist. Creating..."
        os.mkdir("/mnt/scratch")

    if fstype == 'xfs':
        MWpyFS.FormatFS.remakeXFS('/dev/loop0', 
                                  '/mnt/scratch', 
                                  'jhe', 'plfs',
                                  blocksize=4096)
    elif fstype == 'ext4':
        MWpyFS.FormatFS.remakeExt4("/dev/loop0", 
                                   "/mnt/scratch/", 
                                   "jhe", "plfs", 
                                   blockscount=disksize/4096, 
                                   blocksize=4096)
    elif fstype == 'btrfs':
        MWpyFS.FormatFS.btrfs_remake("/dev/loop0", 
                                     "/mnt/scratch/", 
                                     "jhe", "plfs", 
                                     nbytes=disksize)

def make_one_image(fstype, disksize, used_ratio):
    make_file_system(fstype=fstype, 
                     disksize=disksize)

    fsused = int((disksize/(2**30))*used_ratio)

    if fsused == 0:
        pass
    else:
        config_dict = {
                        'Parent_Path:': ['/mnt/scratch/', 1],
                        'FSused:': [ fsused, 'GB'] 
                      }
        pprint.pprint( config_dict )
        run_impressions(config_dict)
    

def make_images():
    para_dict = {
            #'fstype': ['ext4', 'xfs', 'btrfs'],
            'fstype': ['ext4'],
            'disksize': [ x*(2**30) for x in [8, 16]],
            'used_ratio': [ x/10.0 for x in range(0,10,2) ]
            }
    paras = ParameterCominations(para_dict) 
    for para in paras:
        make_one_image(fstype=para['fstype'],
                       disksize=para['disksize'],
                       used_ratio=para['used_ratio'])
        print 'finished one.............'
        time.sleep(1) 




def main():
    make_images()

if __name__ == '__main__':
    main()

