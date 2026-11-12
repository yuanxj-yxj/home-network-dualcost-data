#!/bin/bash
# 完整 T1 全量实验（修复后 binary）：N∈{8,16,32,48,64,96,128,160,192,224} × seed{1..5} = 50 次
# 输出：runs/thread/disc/x_td_N{N}_be0_s{s}.csv
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/thread-edge
OUT=/mnt/d/工作区/ns3_work/runs/thread
mkdir -p $OUT/disc
cd $NS3
echo "== T1 发现扫描（fixed binary, 802.15.4 BEB, 10 N x 5 seeds）=="
for N in 8 16 32 48 64 96 128 160 192 224; do
  for s in 1 2 3 4 5; do
    $BIN --camp=T1 --N=$N --pinBe=0 --seed=$s --duration=30 \
         --out=$OUT/disc/x_td_N${N}_be0_s${s} > /dev/null 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then echo "  !! N=$N s=$s exit=$rc"; fi
  done
  echo "  N=$N done ($(date +%H:%M:%S))"
done
echo "=== T1 DONE: $(ls $OUT/disc/x_td_*_be0_*.csv 2>/dev/null | wc -l) csv files ==="
