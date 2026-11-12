#!/bin/bash
# v3 全量重跑（2026-10-21 晚）
# 触发原因：a) 云侧上下文门控；b) 数据块加 seq 头（消除跨 agent 错账）；
#          c) NACK 补发；d) 网关队列 1000 包、块长 1200 B。a~d 共同改变云侧时延
#          与 WAN 字节口径，旧数据（e2v2/e3v2/e4_mixed/e4b_thresh/e5_oracle）不可混用。
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
JOBS=6

mkdir -p $OUT/e4v3
echo "== E4 混合负载 =="
for bg in none video gaming backup; do
  for bu in 30 10; do
    for pol in ours allcloud alllocal static; do
      for s in 1 2 3 4 5; do
        run $OUT/e4v3 "e4_${bg}_bu${bu}_${pol}_s${s}" --mode=E4 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=$bu \
          --duration=30 --bg=$bg --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
    echo "  bg=$bg bu=$bu -> $(ls $OUT/e4v3 | wc -l)"
  done
done
wait

mkdir -p $OUT/e4bv3
echo "== E4b 门限位移 =="
for bg in none backup; do
  for g in 16384 24576 32768 49152; do
    for pol in ours allcloud alllocal; do
      for s in 1 2 3 4 5; do
        run $OUT/e4bv3 "e4b_${bg}_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
          --duration=40 --bg=$bg --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
  done
  echo "  bg=$bg -> $(ls $OUT/e4bv3 | wc -l)"
done
wait

mkdir -p $OUT/e2v3
echo "== E2 门限带 + 比较静态 =="
for g in 128 2048 8192 16384 32768 65536 131072; do
  for pol in ours allcloud alllocal static; do
    for s in 1 2 3 4 5; do
      run $OUT/e2v3 "e2f_A_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
        --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=60 --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
  echo "  g=$g -> $(ls $OUT/e2v3 | wc -l)"
done
wait
run_pert () { local nm=$1; shift
  for s in 1 2 3 4 5; do
    run $OUT/e2v3 "e2f_B_${nm}_g16384_s${s}" --mode=E2 --discovery=directory \
      --policy=ours --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=60 --seed=$s "$@" &
    while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
  done
}
run_pert rtt10  --rttMs=10
run_pert rtt60  --rttMs=60
run_pert bu10   --bwUpMbps=10
run_pert bu100  --bwUpMbps=100
run_pert c4     --ctxKB=4
run_pert c64    --ctxKB=64
run_pert m1     --m=1
run_pert m5     --m=5
wait

mkdir -p $OUT/e3v3
echo "== E3 Lambda(C) =="
for C in 2 4 8 16 32 64 128 192 256 384 512; do
  for psi in 0 1; do
    for pol in ours allcloud; do
      [ $C -gt 128 ] && [ $pol = allcloud ] && continue
      for s in 1 2 3 4 5; do
        run $OUT/e3v3 "e3_C${C}_p${psi}_${pol}_s${s}" --mode=E2 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=65536 --ctxKB=$C --psi=$psi --rttMs=30 \
          --bwUpMbps=30 --duration=60 --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
  done
  echo "  C=$C -> $(ls $OUT/e3v3 | wc -l)"
done
wait

mkdir -p $OUT/e5v3
echo "== E5 ORACLE =="
for g in 1024 8192 16384 32768 65536; do
  for pol in ours oracle allcloud; do
    for s in 1 2 3 4 5; do
      run $OUT/e5v3 "e5_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
        --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=60 --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
  echo "  g=$g -> $(ls $OUT/e5v3 | wc -l)"
done
wait
for s in 1 2 3; do
  for pol in ours oracle; do
    run $OUT/e5v3 "e5_m5_${pol}_s${s}" --mode=E2 --discovery=directory \
      --policy=$pol --N=16 --m=5 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=60 --seed=$s &
    while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
  done
done
wait
echo "=== v3 DONE: e4=$(ls $OUT/e4v3|wc -l) e4b=$(ls $OUT/e4bv3|wc -l) e2=$(ls $OUT/e2v3|wc -l) e3=$(ls $OUT/e3v3|wc -l) e5=$(ls $OUT/e5v3|wc -l) ==="
