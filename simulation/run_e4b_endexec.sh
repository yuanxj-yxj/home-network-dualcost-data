#!/bin/bash
# ① E4b 补测（正式）：24/32/48 KB 强制端执行，taskTimeoutMs=6000 使 48 KB 点可完成
# 注意：2000 ms 默认值对 48 KB（2112 ms）必然超时，此批显式放宽并须在论文中披露。
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e4b_alllocal_t6
JOBS=${JOBS:-7}
mkdir -p "$OUT"

for bg in none backup; do
  for g in 24576 32768 49152; do
    for s in 1 2 3 4 5; do
      ( $BIN --mode=E2 --discovery=directory --policy=alllocal --N=16 --m=3 --g=$g \
             --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=40 --bg=$bg --seed=$s \
             --taskTimeoutMs=6000 --out="/tmp/z_${bg}_${g}_${s}" > /dev/null 2>&1
        cp "/tmp/z_${bg}_${g}_${s}.csv" "$OUT/x_e4b_${bg}_g${g}_alllocal_t6_s${s}.csv" 2>/dev/null ) &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
done
wait

python3 - "$OUT" << 'PY'
import glob, os, sys, statistics as st
d = sys.argv[1]
print(f"{'bg':8s} {'g/KB':>5s} {'n':>3s} {'P50':>7s} {'P95':>7s} {'ms/KB':>6s} {'done':>6s}")
for bg in ("none", "backup"):
    for g in (24576, 32768, 49152):
        fs = glob.glob(os.path.join(d, f"x_e4b_{bg}_g{g}_alllocal_t6_s*.csv"))
        rows = []
        for f in fs:
            lines = [l.strip() for l in open(f) if l.strip()]
            rows.append(dict(zip(lines[0].split(','), lines[-1].split(','))))
        if not rows: continue
        p50 = st.median([float(r["p50"]) for r in rows])
        p95 = st.median([float(r["p95"]) for r in rows])
        dn = sum(float(r["taskDone"]) for r in rows) / sum(float(r["taskSent"]) for r in rows)
        print(f"{bg:8s} {g//1024:5d} {len(rows):3d} {p50:7.0f} {p95:7.0f} {p50/(g/1024):6.1f} {dn:6.3f}")
PY
