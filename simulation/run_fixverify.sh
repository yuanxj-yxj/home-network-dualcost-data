#!/bin/bash
cd /root/quic-research/ns-allinone-3.35/ns-3.35
cp /mnt/d/工作区/ns3_work/scratch/thread-edge.cc scratch/
./waf build --targets=thread-edge -j8 2>&1 | tail -4
export LD_LIBRARY_PATH=/root/quic-research/ns-allinone-3.35/ns-3.35/build/lib
mkdir -p /mnt/d/工作区/ns3_work/runs/thread/disc
echo "--- thread-edge T1 fix verify (N=8 dur=8) ---"
./build/scratch/thread-edge --camp=T1 --N=8 --seed=1 --duration=8 --out=/mnt/d/工作区/ns3_work/runs/thread/disc/fixverify_T1 2>&1 | tail -5
echo "rows T1:"; wc -l < /mnt/d/工作区/ns3_work/runs/thread/disc/fixverify_T1.csv
echo "--- thread-edge T2 smoke (N=8 dur=8) ---"
./build/scratch/thread-edge --camp=T2 --N=8 --seed=1 --duration=8 --out=/mnt/d/工作区/ns3_work/runs/thread/disc/fixverify_T2 2>&1 | tail -5
echo "exit T2: $?"
