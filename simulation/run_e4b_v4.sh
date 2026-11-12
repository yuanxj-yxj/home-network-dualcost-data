#!/bin/bash
# 云侧 backup 重测（当前二进制，bg 确认生效）：24/32/48/64 KB allcloud + ours，5 seeds
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e4b_v4
mkdir -p "$OUT"
JOBS=${JOBS:-7}

for g in 24576 32768 49152 65536; do
  for pol in allcloud ours; do
    for s in 1 2 3 4 5; do
      ( $BIN --mode=E2 --discovery=directory --policy=$pol --N=16 --m=3 --g=$g \
             --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=40 --bg=backup --seed=$s \
             --out="/tmp/t_${g}_${pol}_${s}" > /dev/null 2>&1
        cp "/tmp/t_${g}_${pol}_${s}.csv" "$OUT/x_e4b4_backup_g${g}_${pol}_s${s}.csv" 2>/dev/null ) &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
done
wait
python3 - "$OUT" << 'PY'
import glob, os, sys, statistics as st
d = sys.argv[1]
print(f"{'g/KB':>5s} {'pol':>9s} {'P50':>7s} {'seeds':>28s} {'succ':>6s}")
for g in (24576, 32768, 49152, 65536):
    for pol in ("allcloud", "ours"):
        vs, dn = [], []
        for f in glob.glob(os.path.join(d, f"x_e4b4_backup_g{g}_{pol}_s*.csv")):
            lines = [l.strip() for l in open(f) if l.strip()]
            r = dict(zip(lines[0].split(","), lines[-1].split(",")))
            vs.append(float(r["p50"]))
            dn.append(float(r["taskDone"]) / max(1, float(r["taskSent"])))
        if vs:
            print(f"{g//1024:5d} {pol:>9s} {st.median(vs):7.1f} {str(sorted(int(v) for v in vs)):>28s} "
                  f"{sum(dn)/len(dn):6.3f}")
PY
