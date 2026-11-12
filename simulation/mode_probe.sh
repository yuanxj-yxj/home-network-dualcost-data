#!/bin/bash
# 对照：同一二进制下 E2 与 E4 模式 × {none, backup}，16 KB 全云，60 s
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/mode_probe
mkdir -p "$OUT"

for mode in E2 E4; do
  for bg in none backup; do
    for s in 1 2; do
      $BIN --mode=$mode --discovery=directory --policy=allcloud --N=16 --m=3 --g=16384 \
           --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --bg=$bg --seed=$s \
           --out="$OUT/x_${mode}_${bg}_s${s}" > /dev/null 2>&1
    done
  done
done
python3 - "$OUT" << 'PY'
import glob, os, sys, statistics as st
d = sys.argv[1]
for mode in ("E2", "E4"):
    for bg in ("none", "backup"):
        vs, ups = [], []
        for f in glob.glob(os.path.join(d, f"x_{mode}_{bg}_s*.csv")):
            lines = [l.strip() for l in open(f) if l.strip()]
            r = dict(zip(lines[0].split(","), lines[-1].split(",")))
            vs.append(float(r["p50"]))
            ups.append(float(r["wanUpRealB"]) / 1e6)
        print(f"{mode} {bg:7s} P50={st.median(vs):7.1f}  wanUpReal={st.median(ups):7.2f} MB  n={len(vs)}")
PY
