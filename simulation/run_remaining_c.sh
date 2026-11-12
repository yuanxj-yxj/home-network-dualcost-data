#!/bin/bash
# ④ 补充：ours_meas（门限带 + 网关实测上行）与 thresh 在同条件对比；含 24 KB 判别点
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
JOBS=${JOBS:-7}

run () { local dir=$1; shift; local nm=$1; shift
  $BIN "$@" --out="/tmp/v_$nm" > "/tmp/v_$nm.log" 2>&1
  cp "/tmp/v_$nm.csv" "$dir/" 2>/dev/null || true
}

mkdir -p "$OUT/e2_oursmeas"
for bg in none backup; do
  for g in 128 512 2048 4096 8192 16384 24576 32768 65536; do
    for s in 1 2 3 4 5; do
      run "$OUT/e2_oursmeas" "e2om_${bg}_g${g}_oursmeas_s${s}" --mode=E2 --discovery=directory \
        --policy=ours --useMeasUp=1 --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 \
        --bwUpMbps=30 --duration=40 --bg=$bg --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
  echo "  bg=$bg done"
done

# thresh 也补 24 KB 判别点
mkdir -p "$OUT/e2_thresh"
for bg in none backup; do
  for s in 1 2 3 4 5; do
    run "$OUT/e2_thresh" "e2th_${bg}_g24576_thresh_s${s}" --mode=E2 --discovery=directory \
      --policy=thresh --N=16 --m=3 --g=24576 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=40 --bg=$bg --seed=$s &
    while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
  done
done
wait
echo "DONE: oursmeas=$(ls $OUT/e2_oursmeas/*.csv | wc -l) thresh=$(ls $OUT/e2_thresh/*.csv | wc -l)"
