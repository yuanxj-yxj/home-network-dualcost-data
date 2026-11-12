#!/bin/bash
# 补点：backup 下 64 KB 云侧（ours 标称）与 48 KB 家庭侧（oursM 实测退回）
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
JOBS=${JOBS:-7}

run () { local dir=$1; shift; local nm=$1; shift
  $BIN "$@" --out="/tmp/u_$nm" > "/tmp/u_$nm.log" 2>&1
  cp "/tmp/u_$nm.csv" "$dir/" 2>/dev/null || true
}

for s in 1 2 3 4 5; do
  run "$OUT/e4b_thresh" "e4b_backup_g65536_ours_s${s}" --mode=E2 --discovery=directory \
    --policy=ours --N=16 --m=3 --g=65536 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
    --duration=40 --bg=backup --seed=$s &
  run "$OUT/e2_oursmeas" "e2om_backup_g49152_oursmeas_s${s}" --mode=E2 --discovery=directory \
    --policy=ours --useMeasUp=1 --N=16 --m=3 --g=49152 --ctxKB=16 --rttMs=30 \
    --bwUpMbps=30 --duration=40 --bg=backup --seed=$s &
  run "$OUT/e2_oursmeas" "e2om_none_g49152_oursmeas_s${s}" --mode=E2 --discovery=directory \
    --policy=ours --useMeasUp=1 --N=16 --m=3 --g=49152 --ctxKB=16 --rttMs=30 \
    --bwUpMbps=30 --duration=40 --bg=none --seed=$s &
  while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
done
wait
python3 - << 'PY'
import glob, statistics as st
def med(pat, key="p50"):
    vs = []
    for f in glob.glob(pat):
        lines = [l.strip() for l in open(f) if l.strip()]
        d = dict(zip(lines[0].split(','), lines[-1].split(',')))
        try: vs.append(float(d[key]))
        except: pass
    return st.median(vs) if vs else float('nan')
print("backup 64KB ours(cloud)  P50 =", med('/mnt/d/工作区/ns3_work/runs/agentsim/e4b_thresh/e4b_backup_g65536_ours_s*.csv'))
print("backup 48KB oursM(home)  P50 =", med('/mnt/d/工作区/ns3_work/runs/agentsim/e2_oursmeas/e2om_backup_g49152_oursmeas_s*.csv'))
print("none   48KB oursM(home)  P50 =", med('/mnt/d/工作区/ns3_work/runs/agentsim/e2_oursmeas/e2om_none_g49152_oursmeas_s*.csv'))
PY
