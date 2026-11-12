#!/bin/bash
# 批次 B：② E4 换 TCP 背景重跑（与 e4v3 同条件）  ④ 外部基线 thresh 全扫
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
JOBS=${JOBS:-7}

run () { local dir=$1; shift; local nm=$1; shift
  $BIN "$@" --out="/tmp/w_$nm" > "/tmp/w_$nm.log" 2>&1
  cp "/tmp/w_$nm.csv" "$dir/" 2>/dev/null || true
}

# ---------------- ② TCP 背景：与 e4v3 完全同条件，只换 bgProto ----------------
mkdir -p "$OUT/e4tcp"
echo "[2] E4 with TCP background"
for bg in none video gaming backup; do
  for bu in 30 10; do
    for pol in ours allcloud alllocal static; do
      for s in 1 2 3 4 5; do
        run "$OUT/e4tcp" "e4tcp_${bg}_bu${bu}_${pol}_s${s}" --mode=E4 --policy=$pol \
          --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=$bu \
          --duration=60 --bg=$bg --bgProto=tcp --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
  done
  echo "  bg=$bg done ($(ls $OUT/e4tcp/*.csv 2>/dev/null | wc -l) files)"
done
wait

# ---------------- ④ 外部基线 thresh：门限带全扫（无背景 / 备份背景） ----------------
mkdir -p "$OUT/e2_thresh"
echo "[4] thresh baseline sweep"
for bg in none backup; do
  for g in 128 512 2048 4096 8192 16384 32768 65536; do
    for s in 1 2 3 4 5; do
      run "$OUT/e2_thresh" "e2th_${bg}_g${g}_thresh_s${s}" --mode=E2 --discovery=directory \
        --policy=thresh --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=40 --bg=$bg --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
  echo "  bg=$bg done ($(ls $OUT/e2_thresh/*.csv 2>/dev/null | wc -l) files)"
done
wait
echo "ALL DONE: e4tcp=$(ls $OUT/e4tcp/*.csv | wc -l) thresh=$(ls $OUT/e2_thresh/*.csv | wc -l)"
