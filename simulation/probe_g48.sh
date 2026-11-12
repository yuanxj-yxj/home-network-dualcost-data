#!/bin/bash
# 48 KB 端执行：延长仿真时长与放大轮次预算，判断 P50=0 是超时还是硬上限
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e4b_probe
mkdir -p "$OUT"

probe () { # g duration m
  local g=$1 dur=$2 m=$3
  local tag="g${g}_d${dur}_m${m}"
  $BIN --mode=E2 --discovery=directory --policy=alllocal --N=16 --m=$m --g=$g \
       --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=$dur --seed=1 \
       --out="$OUT/x_p_$tag" > /dev/null 2>&1
  python3 - "$OUT/x_p_$tag.csv" "$tag" << 'PY'
import sys
f, tag = sys.argv[1], sys.argv[2]
lines = [l.strip() for l in open(f) if l.strip()]
hdr, row = lines[0].split(','), lines[-1].split(',')
d = dict(zip(hdr, row))
g = lambda k: d.get(k, 'NA')
print(f"{tag:20s} p50={g('p50'):>6s} p95={g('p95'):>6s} rounds={g('rounds'):>4s} "
      f"failed={g('taskFailed'):>4s} done={g('taskDone'):>4s}/{g('taskSent'):>4s} air={g('airtimeS')}")
PY
}

probe 49152 150 3
probe 49152 60 1
probe 40960 150 3
probe 32768 60 1
