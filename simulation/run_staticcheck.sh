#!/bin/bash
cd /root/quic-research/ns-allinone-3.35/ns-3.35
cp /mnt/d/工作区/ns3_work/scratch/thread-edge.cc scratch/
cp /mnt/d/工作区/ns3_work/scratch/thread-edge-bisect.cc scratch/
./waf build --targets=thread-edge,thread-edge-bisect -j8 2>&1 | tail -4
export LD_LIBRARY_PATH=/root/quic-research/ns-allinone-3.35/ns-3.35/build/lib
mkdir -p /mnt/d/工作区/ns3_work/runs/thread/disc
echo "--- thread-edge T1 (N=8 dur=8) ---"
./build/scratch/thread-edge --camp=T1 --N=8 --seed=1 --duration=8 --out=/mnt/d/工作区/ns3_work/runs/thread/disc/staticcheck_te 2>&1 | tail -3
echo "rows:"; wc -l < /mnt/d/工作区/ns3_work/runs/thread/disc/staticcheck_te.csv
echo "--- thread-edge-bisect T1 (N=8 dur=8) ---"
./build/scratch/thread-edge-bisect --camp=T1 --N=8 --seed=1 --duration=8 --out=/mnt/d/工作区/ns3_work/runs/thread/disc/staticcheck_bisect 2>&1 | tail -3
echo "rows:"; wc -l < /mnt/d/工作区/ns3_work/runs/thread/disc/staticcheck_bisect.csv
