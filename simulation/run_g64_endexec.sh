#!/bin/bash
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e4b_alllocal_t6
mkdir -p "$OUT"
for s in 1 2 3 4 5; do
  $BIN --mode=E2 --discovery=directory --policy=alllocal --N=16 --m=3 --g=65536 \
       --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=40 --seed=$s \
       --taskTimeoutMs=6000 --out="/tmp/q64_$s" > /dev/null 2>&1
  cp "/tmp/q64_$s.csv" "$OUT/x_e4b_none_g65536_alllocal_t6_s${s}.csv" 2>/dev/null
done
python3 - "$OUT" << 'PY'
import glob, os, sys, statistics as st
d = sys.argv[1]
vs = []
for f in glob.glob(os.path.join(d, "x_e4b_none_g65536_alllocal_t6_s*.csv")):
    lines = [l.strip() for l in open(f) if l.strip()]
    row = dict(zip(lines[0].split(','), lines[-1].split(',')))
    vs.append((float(row["p50"]), float(row["taskDone"]), float(row["taskSent"])))
p = sorted(v[0] for v in vs)
print("64KB end-exec P50 =", st.median(p), " n =", len(vs),
      " done/sent =", sum(v[1] for v in vs), "/", sum(v[2] for v in vs))
PY
