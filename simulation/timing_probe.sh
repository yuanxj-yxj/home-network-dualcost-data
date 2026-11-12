#!/bin/bash
# 单次运行耗时实测：E4 全本地 24KB + 云备份背景，60 s 仿真
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/timing_probe
mkdir -p "$OUT"

for G in 24576 32768 49152; do
  S=$(date +%s)
  $BIN --mode=E4 --policy=alllocal --g=$G --bg=backup --bwUpMbps=30 \
       --duration=60 --seed=1 --out="$OUT/x_probe_g${G}_alllocal_s1" > /dev/null 2>&1
  E=$(date +%s)
  echo "g=$((G/1024))KB wall=$((E-S))s"
done

echo "--- 样例结果 ---"
head -1 "$OUT/x_probe_g24576_alllocal_s1.csv" | cut -c1-100
tail -1 "$OUT/x_probe_g24576_alllocal_s1.csv" | cut -c1-160
