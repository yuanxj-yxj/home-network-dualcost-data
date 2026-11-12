#!/bin/bash
# 冒烟：thresh 策略（含/不含背景）+ TCP 背景（上行备份、下行视频）
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/smoke2
mkdir -p "$OUT"

one () { # tag args...
  local tag=$1; shift
  $BIN "$@" --out="$OUT/x_$tag" > "$OUT/$tag.log" 2>&1
  grep "DIAG-BG" "$OUT/$tag.log" | head -1
  python3 - "$OUT/x_$tag.csv" "$tag" << 'PY'
import sys
f, tag = sys.argv[1], sys.argv[2]
lines = [l.strip() for l in open(f) if l.strip()]
d = dict(zip(lines[0].split(','), lines[-1].split(',')))
n = lambda k: float(d.get(k, 'nan'))
print(f"  {tag:34s} p50={n('p50'):7.0f} p95={n('p95'):7.0f} "
      f"cloud={'Y' if n('wanUpRealB')>0 else 'N'} done={n('taskDone'):.0f}/{n('taskSent'):.0f}")
PY
}

echo "--- thresh, 无背景 / 备份背景（24/30 Mbps）---"
one thresh_none   --mode=E2 --discovery=directory --policy=thresh --N=16 --m=3 --g=32768 \
                  --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=40 --seed=1
one thresh_backup --mode=E2 --discovery=directory --policy=thresh --N=16 --m=3 --g=32768 \
                  --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=40 --bg=backup --seed=1

echo "--- TCP 背景 ---"
one tcp_up   --mode=E4 --policy=allcloud --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 \
             --bwUpMbps=30 --duration=40 --bg=backup --bgProto=tcp --seed=1
one tcp_dn   --mode=E4 --policy=allcloud --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 \
             --bwUpMbps=30 --duration=40 --bg=video --bgProto=tcp --seed=1
