#!/bin/bash
NS=/root/quic-research/ns-allinone-3.35/ns-3.35
SRC=/mnt/d/工作区/ns3_work/scratch
RUNS=/mnt/d/工作区/ns3_work/runs/thread/disc

cp "$SRC"/thread-edge-old3.cc "$NS"/scratch/ || exit 1
cp "$SRC"/thread-edge-old4.cc "$NS"/scratch/ || exit 1
cp "$SRC"/thread-edge-old5.cc "$NS"/scratch/ || exit 1

cd "$NS" || exit 1
echo "### BUILD ###"
./waf build --targets=thread-edge-old3,thread-edge-old4,thread-edge-old5 -j8 2>&1 | tail -30

export LD_LIBRARY_PATH="$NS"/build/lib
mkdir -p "$RUNS"

for v in old3 old4 old5; do
  echo "### RUN $v ###"
  ./build/scratch/thread-edge-"$v" --camp=T1 --N=8 --seed=1 --duration=30 --out="$RUNS"/chk_"$v"_N8 2>&1 | tail -3
  echo "=== $v CSV rows ==="
  wc -l < "$RUNS"/chk_"$v"_N8.csv
done
echo "### DONE ###"
