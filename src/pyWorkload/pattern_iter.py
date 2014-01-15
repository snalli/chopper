import itertools
import producer
import re
import random
import pprint
import subprocess
import pat_data_struct
import copy

N_OPERATIONS = 4 # OPEN FSYNC CLOSE SYNC

def Filter( opstr, keep ):
    # input is like (FSYNC, True)
    if keep:
        return opstr 
    else:
        return ""

def wrappers_to_symbols( wrappers ):
    num_of_chunks = len(wrappers) / N_OPERATIONS
    #strs = ['OPEN', 'FSYNC', 'CLOSE', 'SYNC'] * num_of_chunks
    symbols = ['(', 'C', 'F', ')', 'S'] * num_of_chunks

    #TODO: this can go bad when the number of operations changes
    choices = [ (wrappers[i], True, wrappers[i+1], wrappers[i+2], wrappers[i+3]) \
                    for i in range(0, num_of_chunks*N_OPERATIONS, N_OPERATIONS) ]
    choices = list(itertools.chain.from_iterable(choices))
    seq = map(Filter, symbols, choices)
    seq = ''.join(seq)

    return seq


def IsLegal( wrappers ):
    "conver to string and use regex"
    seq = wrappers_to_symbols( wrappers )
   
    # use regex to check seq
    #
    # GOOD ONE backup: mo = re.match(r'^(\((C+F?)+\)S?)+$', seq, re.M)
    #mo = re.match(r'^(\((C+F)+\))S$', seq, re.M) # always Fsync, only one open-close, must sync
    mo = re.match(r'^(\((C+F?)+\)S)+$', seq, re.M)
    if mo:
        #print "good match!", seq
        return True
    else:
        #print 'BAD match!', seq
        return False

def pattern_iter_nfiles(nfiles, filesize, chunksize):
    """
    Input: 
        nfiles: number of files
        filesize: file size
        chunksize: chunk size
    
    Output:
        a iteratorable object like itertool.permutation
    
    Usage:
        for x in pattern_iter(xxx,xxx,xx):
            use x
        OR
        l = list(pattern_iter(xxx,xxx,xxx))
        for x in l:
            use x
        
    Single file case is not hard, multiple is hard.
    """
    nchunks_per_file = filesize/chunksize

    # split to chunks
    file_chunks = [] # it is a list of chunks from different files
    for i in range(nfiles):
        file_chunks.append( 
                split_a_file_to_chunks(filesize  =filesize, 
                                       chunksize =chunksize,
                                       fileid    =i) )

    # sort the chunks
    #all_chunks = [c for f in file_chunks for c in f ]

    # Separate chunks of different files out

    # Assign only legal operations to chunks for each file
    possible_ops = list(operations_iter( nchunks_per_file )) #{chunks, operations}
    # you now have all k possible operation sequences for a file
    # you need to pick n (could be repeated) from k and assign to
    # the n files
    ## pick n
    for j in range(10):
        #ops_for_files = random.sample( possible_ops, nfiles )
        print 'len', len(possible_ops)
        ops_for_files = [random.choice( possible_ops ) for i in range(nfiles)]
        pprint.pprint( ops_for_files )
        #ops_for_files = list(possible_ops[0]) * nfiles 
        chks_ops_of_files = zip (file_chunks, ops_for_files)
        chks_ops_of_files = [ dict( zip( ['chunks', 'operations'], FileEntry) ) \
                                            for FileEntry in chks_ops_of_files ]
        for fentry in chks_ops_of_files:
            fentry['operations'] = operations_to_human_readable( fentry['operations'] )
        chks_ops_of_files = [ merge_chks_ops( fentry ) for fentry in chks_ops_of_files]
        chks_ops_of_files = zip( *chks_ops_of_files )
        chks_ops_of_files = [y for x in chks_ops_of_files for y in x]
        #print "pppppppppppppppppppppp"
        #pprint.pprint( chks_ops_of_files )
        yield chks_ops_of_files

def merge_chks_ops ( chks_ops ):
    """
    Input: {'chunks':... 'operations':...}
    Output:[ 
             {'chunks':.. 'operations':...},
             {'chunks':.. 'operations':...} 
             ...
           ]
    """
    #print chks_ops
    ret = [ dict(zip(['chunk','operations'], onechunk)) \
            for onechunk in zip( chks_ops['chunks'], chks_ops['operations'] ) ]
    #pprint.pprint( ret )
    return ret


def operations_iter(num_of_chunks, method='fixed'):
    """
    It will return an iterable object the iterates all/selected
    operations to the num_of_chunks chunks

    If reduce == True. We try to reduce the number of operations
    """
    if method == 'ALL':
        wrapper_iter = itertools.product([False, True], 
                            repeat=num_of_chunks*N_OPERATIONS)
        for wraps in wrapper_iter:
            if not IsLegal(wraps):
                # skip bad ones
                continue
            yield wraps # (True, False, False, ..)
    elif method == 'fixed':
        # Try to reduce the amount of operation sequences
        # OPEN FSYNC CLOSE SYNC
        # You can set cretiria like: 
        #   1. only one open/close
        #   2. no fsync
        #   3. always fsync
        #   4. always sync   USEFUL, I always need it. 

        # 1. only one open-close
        opens = [False] * num_of_chunks 
        opens[0] = True
        closes = [False] * num_of_chunks
        closes[-1] = True

        # 2. no fsync
        #fsyncs = [False] * num_of_chunks
        fsyncs_iter = itertools.product([False, True],
                            repeat=num_of_chunks)
        # 3. always fsync
        #fsyncs = [True] * num_of_chunks

        # 4. always sync
        syncs = [False] * num_of_chunks
        #syncs[-1] = True

        for fsyncs in fsyncs_iter:
            wrappers = zip( opens, fsyncs, closes, syncs )
            wrappers = [y for x in wrappers for y in x]
            yield wrappers

    elif method == 'sample':
        pass
    else:
        print 'not defined method in operations_iter'
        exit(1)

def split_a_file_to_chunks(filesize, chunksize, fileid=0):
    """
    At this time, let me just split the file to 
    equal sizes. Later we can do random splits
    """
    num_of_chunks = filesize / chunksize
    chunk_sizes = [chunksize] * num_of_chunks
    file_ids = [fileid] * num_of_chunks
    offsets = range(0, filesize, chunksize)
    chunks = zip(file_ids, offsets, chunk_sizes)

    # convert to dictionary
    ret = [ dict( zip( ['fileid', 'offset', 'length'], c ) ) \
                                                    for c in chunks ]
    return ret

def chunk_order( chunks ):
    chunk_indice = []
    for off, len in chunks:
        index = off/len
        chunk_indice.append(index)
    return chunk_indice

def pattern_string( chunks, wrappers ):
    chunk_indice = chunk_order(chunks)
    wrappers = [ int(x) for x in wrappers]
    
    n = len(wrappers)
    o = [ wrappers[i] for i in range(0, n, N_OPERATIONS) ]
    f = [ wrappers[i] for i in range(1, n, N_OPERATIONS) ]
    c = [ wrappers[i] for i in range(2, n, N_OPERATIONS) ]
    s = [ wrappers[i] for i in range(3, n, N_OPERATIONS) ]

    mix = zip(o,chunk_indice,f,c,s) 
    mix = [ str(j) for x in mix for j in x ]
    mix = "".join( mix )

    return mix


def pattern_iter_files(nfiles, filesize, chunksize, num_of_chunks):
    # get all ways of writing one file
    patterns = list(pattern_iter(nfiles, filesize, chunksize, num_of_chunks))
    pat_list = []
    for i,p in enumerate(patterns):
        p_chkseq = pat_data_struct.chunkop_to_chunkseq(p)
        for c_chkbox in p_chkseq['seq']:
            c_chkbox['chunk']['single_file_write_patternid'] = i
        pat_list.append(p_chkseq)

    # get all possible mix
    # this is different ways of mixing different files
    file_chunk_tags = range(nfiles) * num_of_chunks
    chunkmix = list(set(list(itertools.permutations(file_chunk_tags)))) # improve this!

    # now fill the chunk placeholders with real chunks
    for p in itertools.product( pat_list, repeat=nfiles ):
        # p = (ChunkSeq0, ChunkSeq1, ..)
        # p is a mix of patterns of writing one file
        for mix in chunkmix:
            # mix is a mix of different ways of mixing
            # single file writting patterns
            cur_pos = [0] * nfiles
            files_chkseq = pat_data_struct.get_empty_ChunkSeq()
            for fileid in mix:
                cur_chkseq = copy.deepcopy(p[fileid])
                cur_chkbox = cur_chkseq['seq'][ cur_pos[fileid] ]
                cur_chkbox['chunk']['fileid'] = fileid
                files_chkseq['seq'].append(copy.deepcopy(cur_chkbox))
                cur_pos[fileid] += 1
            yield files_chkseq



def pattern_iter(nfiles, filesize, chunksize, num_of_chunks=3):
    "Note that nfiles is NOT used"
    chunk_sizes = [chunksize] * num_of_chunks
    # we want the last chunk at the end of the file
    stridesize = (filesize - chunksize) / (num_of_chunks - 1) 
    
    assert (filesize - chunksize) % (num_of_chunks - 1) == 0, 'chunks cannot be evenly distributed'

    offsets = range(0, filesize, stridesize)
    chunks = zip(offsets, chunk_sizes)

    chunk_iter = itertools.permutations(chunks)
    for chks in chunk_iter:
        wrapper_iter = itertools.product([False, True], repeat=num_of_chunks*N_OPERATIONS)
        for wraps in wrapper_iter:
            if not IsLegal(wraps):
                # skip bad ones
                continue
            #print chks
            #print wraps
            yield {'chunks':chks, 'wrappers':wraps}

def GenWorkloadFromChunks( chunks,
                           wrappers,
                           rootdir,
                           tofile
                           ):
        
    num_of_chunks = len(chunks)

    # organize it as dictionary
    chunks = [ dict( zip( ['offset', 'length'], c ) ) \
                                                    for c in chunks ]
    # group wrapers to 3 element groups
    wrappers = [wrappers[i:i+N_OPERATIONS] for i in range(0, num_of_chunks*N_OPERATIONS, N_OPERATIONS) ]
    wrappers = [ dict( zip(['OPEN', 'FSYNC', 'CLOSE', 'SYNC'], w) ) \
                                                    for w in wrappers]

    prd = producer.Producer(
            rootdir = rootdir,
            tofile = tofile)
    prd.addDirOp('mkdir', pid=0, dirid=0)

    # ( (off,size), {wrapper} )
    entries = zip(chunks, wrappers)
    for entry in entries:
        #print entry
        if entry[1]['OPEN']:
            prd.addUniOp('open', pid=0, dirid=0, fileid=0)
        
        # the chunk write
        prd.addReadOrWrite('write', pid=0, dirid=0,
               fileid=0, off=entry[0]['offset'], len=entry[0]['length'])

        if entry[1]['FSYNC']: 
            prd.addUniOp('fsync', pid=0, dirid=0, fileid=0)

        if entry[1]['CLOSE']: 
            prd.addUniOp('close', pid=0, dirid=0, fileid=0)

        if entry[1]['SYNC']:
            prd.addOSOp('sync', pid=0)

    prd.display()
    prd.saveWorkloadToFile()
    return True

def operations_to_human_readable( wrappers ):
    # put operations of a chunk to a tuple
    num_of_wrappers = len(wrappers)
    wrappers = [wrappers[i:i+N_OPERATIONS] \
            for i in range(0, num_of_wrappers, N_OPERATIONS) ]
    # give them names
    wrappers = [ dict( zip(['OPEN', 'FSYNC', 'CLOSE', 'SYNC'], w) ) \
                                                    for w in wrappers]
    return wrappers

def GenWorkloadFromChunksOfFiles(  chks_ops,
                                   rootdir,
                                   tofile
                                ):
    #print "888888888888888888888888888888888888"
    #pprint.pprint( chks_ops_of_files )

    prd = producer.Producer(
            rootdir = rootdir,
            tofile = tofile)
    prd.addDirOp('mkdir', pid=0, dirid=0)

    for entry in chks_ops:
        #pprint.pprint(entry)
        if entry['operations']['OPEN']:
            prd.addUniOp('open', pid=0, dirid=0, fileid=entry['chunk']['fileid'])
        
        # the chunk write
        prd.addReadOrWrite('write', pid=0, dirid=0,
           fileid=entry['chunk']['fileid'], 
           off=entry['chunk']['offset'], 
           len=entry['chunk']['length'])

        if entry['operations']['FSYNC']: 
            prd.addUniOp('fsync', 
                    pid=0, dirid=0, fileid=entry['chunk']['fileid'])

        if entry['operations']['CLOSE']: 
            prd.addUniOp('close', 
                    pid=0, dirid=0, fileid=entry['chunk']['fileid'])

        if entry['operations']['SYNC']:
            prd.addOSOp('sync', pid=0)

    prd.display()
    prd.saveWorkloadToFile()
    return True

def regldg(max_length, num_words_output, regstr):
    #./regldg --debug-code=1 --universe-set=7 --universe-checking=3 --max-length=8 --readable-output --num-words-output=100 "(a|b)[cd]{2}\1"
    cmd = [
            './regldg-1.0.0/regldg', 
            '--debug-code=1', 
            '--universe-set=33', 
            '--universe-checking=3',
            '--max-length='+str(max_length),
            '--readable-output',
            '--num-words-output='+str(num_words_output),
            regstr
            ]
    proc = subprocess.Popen(cmd, 
                    stdout = subprocess.PIPE)
    proc.wait()

    wordlist = []
    for line in proc.stdout:
        wordlist.append(line.strip())
    
    pprint.pprint( wordlist )
    return wordlist

def perm_with_repeats(seq):
    "This algorithm is NOT efficient in larger scale!"
    return list(set(list(itertools.permutations(seq))))

def overwrite_iter(filesize):
    nchunks = 6


#print perm_with_repeats([0,0,0,1,1,1])

#pattern_iter_files(nfiles=2, filesize=12, chunksize=6, num_of_chunks=2)

#regldg(max_length = 30, 
       #num_words_output=100,
       ##regstr="(a|b)[cd]{4}\\1")
       ##regstr="(\((C+F?)+\)S?)+")
       #regstr="(CF?)+")

#pprint.pprint( list(pattern_iter_nfiles(2, 900, 300)) )

#for chks_ops_of_files in pattern_iter_nfiles(2, 900, 300):
    #print "****************************"
    ##pprint.pprint( chks_ops_of_files )
    #GenWorkloadFromChunksOfFiles(chks_ops_of_files, 
                                 #rootdir='/mnt/scratch',
                                 #tofile ='/tmp/workkkkkload')
    #break

#for x in pattern_iter(1, 6, 2):
    #print x
