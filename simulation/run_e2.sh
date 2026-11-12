#!/bin/bash
# E2 正式扫描（真实转发版）
# A 部分：门限带曲线 —— g × 4 策略，基线参数
# B 部分：比较静态 —— 扰动组 × 3 个 g 点，ours 策略
# 用法：bash run_e2.sh <并发度>
set -u
cd /root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e2_formal
mkdir -p "$OUT"
P=${1:-6}

run_one() {
  local tag="$1" ; shift
  ./build/scratch/agent-sim "$@" --out="/tmp/e2f_$tag" > "/tmp/e2f_$tag.log" 2>&1
  local rc=$?
  cp "/tmp/e2f_$tag.csv" "$OUT/" 2>/dev/null
  echo "$tag rc=$rc"
}
export -f run_one
export LD_LIBRARY_PATH
export OUT

JOBS=/tmp/e2_jobs.txt
: > "$JOBS"

GS="128 512 2048 4096 8192 16384 32768 65536"
# A：门限带曲线（基线 N=16 m=3 C=16 rtt=30 bu=30）
for g in $GS; do
  for pol in ours allcloud alllocal static; do
    for s in 1 2 3 4 5; do
      echo "A_g${g}_${pol}_s${s}|--mode=E2 --discovery=directory --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --seed=$s" >> "$JOBS"
    done
  done
done
# B：比较静态（扰动 ours；g 取 3 个代表点）
for pert in "rtt10 --rttMs=10" "rtt60 --rttMs=60" "bu10 --bwUpMbps=10" "bu100 --bwUpMbps=100" "c4 --ctxKB=4" "c64 --ctxKB=64" "m1 --m=1" "m5 --m=5" "n64 --N=64"; do
  pname=${pert%% *}; pargs=${pert#* }
  for g in 2048 16384 65536; do
    for s in 1 2 3 4 5; do
      echo "B_${pname}_g${g}_s${s}|--mode=E2 --discovery=directory --policy=ours --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 --duration=60 --seed=$s $pargs" >> "$JOBS"
    done
  done
done

wc -l < "$JOBS"
cat "$JOBS" | xargs -P "$P" -I{} bash -c 'I="{}"; tag="${I%%|*}"; args="${I#*|}"; run_one "$tag" $args'
echo ALLDONE
