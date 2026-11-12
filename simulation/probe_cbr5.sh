#!/bin/bash
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/mode_probe
for s in 1 2 3 4 5; do
  $BIN --mode=E4 --discovery=directory --policy=allcloud --N=16 --m=3 --g=16384 \
       --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --bg=backup --seed=$s \
       --out="$OUT/x_E4backup5_$s" > /dev/null 2>&1
done
python3 - "$OUT" << 'PY'
import glob, os, sys, statistics as st
d = sys.argv[1]
vs = []
for f in glob.glob(os.path.join(d, "x_E4backup5_*.csv")):
    lines = [l.strip() for l in open(f) if l.strip()]
    r = dict(zip(lines[0].split(","), lines[-1].split(",")))
    vs.append(float(r["p50"]))
print("E4 CBR backup allcloud 16KB, current binary, 5 seeds: P50 =", st.median(vs), " seeds =", sorted(vs))
PY
