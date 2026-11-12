#!/bin/bash
# T2 补点：512B / 2048B，3 seeds，写入 t2_g*_s* 标准命名
NS3=$HOME/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/thread-edge
OUT=/mnt/d/工作区/ns3_work/runs/thread/place
for g in 512 2048; do
  for s in 1 2 3; do
    echo "=== T2 g=$g seed=$s ==="
    THREAD_WAN=1 "$BIN" --camp=T2 --N=4 --g="$g" --f0thread=0.1 \
      --bwUpMbps=30 --rttCloudMs=30 --ctxKB=16 --seed="$s" \
      --duration=25 --nSends=6 --sendIntervalMs=400 --out="$OUT/t2_g${g}_s${s}"
  done
done
echo DONE
