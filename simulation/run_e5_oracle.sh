#!/bin/bash
# E5：ORACLE（3^m 离线穷举）上界对照
# ours=按门限带逐个放置（忽略批内排队）；oracle=按批完成时间穷举 3^m 最优
set -e
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/agent-sim
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e5_oracle
mkdir -p $OUT
cd $NS3

for g in 1024 8192 16384 32768 65536; do
  for pol in ours oracle allcloud; do
    for s in 1 2 3 4 5; do
      $BIN --mode=E2 --discovery=directory --policy=$pol --N=16 --m=3 --g=$g \
           --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --seed=$s \
           --out=/tmp/e5_g${g}_${pol}_s${s} > /tmp/e5_g${g}_${pol}_s${s}.log 2>&1 &
      while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
    done
    cp /tmp/e5_g${g}_${pol}_s*.csv $OUT/ 2>/dev/null || true
  done
  echo "E5 g=$g done: $(ls $OUT | wc -l)"
done
wait
# m=5 的更大组合空间（243 种指派），只测 ours/oracle
for s in 1 2 3; do
  for pol in ours oracle; do
    $BIN --mode=E2 --discovery=directory --policy=$pol --N=16 --m=5 --g=16384 \
         --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --seed=$s \
         --out=/tmp/e5_m5_${pol}_s${s} > /tmp/e5_m5_${pol}_s${s}.log 2>&1 &
    while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
  done
done
cp /tmp/e5_m5_*.csv $OUT/ 2>/dev/null || true
wait
echo "E5 ALL: $(ls $OUT | wc -l)"
