import sys

f = open("puncher.conf", 'w')
sz = 6	# sz GB
blk = 4 # blk KB

# Convert to bytes
sz = sz*1024*1024*1024 # sz bytes
blk = blk*1024

# Write to conf file

# first line is len of file
f.write("0 " + str(sz) + "\n")

# off len
for off in range(blk,sz,blk*2):
	f.write(str(off) + " " + str(blk) + "\n")

# EOF
f.write("-1 -1" + "\n")

# Close conf file
f.flush()
f.close()
