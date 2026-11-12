#!/bin/bash
# T2 执行放置测量：leaf→border(802.15.4/6LoWPAN, IPv6) 单向时延 τ_lb(g)
# 与 border→cloud(WAN, IPv4) 单向时延 τ_bc(g)。跨地址族 pivot 由 border 双栈完成。
# 运行：bash run_thread_t2.sh
NS3=$HOME/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/thread-edge
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/thread/place
mkdir -p "$OUT"
for g in 1024 4096 8192 16384 32768 65536; do
  if [ "$g" -le 8192 ]; then dur=25; else dur=75; fi
  for s in 1 2 3; do
    echo "=== T2 g=$g seed=$s N=4 dur=$dur ==="
    THREAD_WAN=1 "$BIN" --camp=T2 --N=4 --g=$g --f0thread=0.1 \
      --bwUpMbps=30 --rttCloudMs=30 --ctxKB=16 --seed=$s --duration=$dur \
      --nSends=4 --sendIntervalMs=400 --out="$OUT/t2_g${g}_s${s}"
  done
done
echo "T2 sweep done"
