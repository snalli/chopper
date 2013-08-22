#!/usr/bin/python 

import subprocess
import os
import getpass
import pwd
import grp

def formatToOnePart(devname, confpath):
    conffile = open(confpath, "r")

    cmd = ["sfdisk", devname]
    #cmd = ["cat"]
    p = subprocess.Popen(cmd, stdin=conffile)
    p.wait()
    
    conffile.close()
    print "formatToOnePart:", p.returncode
    return p.returncode

def makeExt4(devname, blockscount=16777216):
    cmd = ["mkfs.ext4", devname, blockscount]
    cmd = [str(x) for x in cmd]
    p = subprocess.Popen(cmd)
    p.wait()
    print "makeExt4:", p.returncode
    return p.returncode

def umountFS(mountpoint):
    cmd = ["umount", "-f", mountpoint]
    p = subprocess.Popen(cmd)
    p.wait()
    print "umountFS:", p.returncode
    return p.returncode

def mountExt4(devname, mountpoint):
    if not os.path.exists(mountpoint):
        os.makedirs(mountpoint)

    cmd = ["mount", "-t", "ext4", devname, mountpoint]
    p = subprocess.Popen(cmd)
    p.wait()
    print "mountExt4:", p.returncode
    return p.returncode

def chDirOwner(mountpoint, username, groupname):
    try:
        uid = pwd.getpwnam(username).pw_uid
        gid = grp.getgrnam(groupname).gr_gid
    
        print username,groupname,uid,gid
        os.chown(mountpoint, uid, gid)
    except:
        print "cannot chown", username, ":", groupname, "in system"

    return 0

def remakeExt4(partition, mountpoint, username, groupname, blockscount=16777216):
    ret = umountFS(mountpoint)
    if ret != 0:
        print "Error in umountFS: this should not happen"
        print "Tolerated"
    ret = makeExt4(partition, blockscount)
    if ret != 0:
        print "Error in makeExt4: this should not happen"
        return ret
    ret = mountExt4(partition, mountpoint)
    if ret != 0:
        print "Error in mountExt4: this should not happen"
        return ret
    chDirOwner(mountpoint, username, groupname)

def buildNewExt4(devname, mountpoint, confpath, username, groupname):
    devname_part1 = devname+"1"
    
    ret = umountFS(mountpoint)
    if ret != 0:
        print "Error in umountFS: this should not happen"
        print "Tolerated"

    ret = formatToOnePart(devname, confpath)
    if ret != 0:
        print "Error in formatToOnePart: this should not happen"
        print "Tolerated"

    remakeExt4(devname_part1, mountpoint, username, groupname)

#buildNewExt4("/dev/sdb", "/mnt/scratch", "../../conf/sfdisk.conf")

