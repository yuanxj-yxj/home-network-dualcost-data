#!/bin/bash
# E5：ORACLE（3^m 离线穷举）上界对照
# E4b：背景流下的门限位移直接实测
#   解析：g2* 由 19 KB（无背景，B_u=30）右移至 ~28.6 KB（备份 24 Mbps，B_eff≈6）
#   ⟹ 在 g=24 KB 处，无背景应走云、有备份应仍走家庭（可判别点）
set -e
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/agent-sim
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
cd $NS3

run () { local dir=$1; shift; local nm=$1; shift
  $BIN "$@" --out=/tmp/x_$nm > /tmp/x_$nm.log 2>&1
  cp /tmp/x_$nm.csv $dir/ 2>/dev/null || true
}

# ---------------- E4b：门限位移 ----------------
mkdir -p $OUT/e4b_thresh
for bg in none backup; do
  for g in 16384 24576 32768 49152; do
    for pol in ours allcloud; do
      for s in 1 2 3 4 5; do
        run $OUT/e4b_thresh "e4b_${bg}_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
          --duration=40 --bg=$bg --seed=$s &
        while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
      done
    done
  done
  echo "E4b bg=$bg done: $(ls $OUT/e4b_thresh | wc -l)"
done
wait
echo "E4b ALL: $(ls $OUT/e4b_thresh | wc -l)"

# ---------------- E5：ORACLE 上界 ----------------
mkdir -p $OUT/e5_oracle
for g in 1024 8192 16384 32768 65536; do
  for pol in ours oracle allcloud; do
    for s in 1 2 3 4 5; do
      run $OUT/e5_oracle "e5_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
        --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=60 --seed=$s &
      while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
    done
  done
  echo "E5 g=$g done: $(ls $OUT/e5_oracle | wc -l)"
done
wait
for s in 1 2 3; do
  for pol in ours oracle; do
    run $OUT/e5_oracle "e5_m5_${pol}_s${s}" --mode=E2 --discovery=directory \
      --policy=$pol --N=16 --m=5 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=60 --seed=$s &
    while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
  done
done
wait
echo "E5 ALL: $(ls $OUT/e5_oracle | wc -l)"
echo "=== DONE ==="
