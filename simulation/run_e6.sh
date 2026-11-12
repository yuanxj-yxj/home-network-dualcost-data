#!/bin/bash
# E6：批内混排贪心（mix）vs 逐点判据（ours）vs ORACLE（3^m 穷举）vs 全云
#
# 背景：E5（e5v3）已量化"判据距 ORACLE 的间隙"——16 KB/m=3 时 ours 比 oracle 差
# 68.2%（74 vs 44 ms），m=5 时差 110%（109 vs 52），32/64 KB 差 12–13%。
# 本实验把 O(m log m) 的 LPT 式混排贪心实现在线策略（--policy=mix），检验：
#   Q1 贪心指派是否复现 3^m 穷举指派（判据：wanUpBytes 上云份额逐位相同）；
#   Q2 mix 把 ours→oracle 的间隙回收多少（P50 口径）；
#   Q3 收益的粒度区间（8 KB 处判据曾反超解析参照 5.1%，mix 是否同样回落）；
#   Q4 异构批（lognormal 粒度）下贪心的排序是否带来额外收益。
#
# 与 E5 的可比性：主组参数与 e5v3 逐字相同（N=16 m=3 C=16KB r_c=30 B_u=30
# duration=60 seeds 1–5），只增加 mix 一列；m5/ln 两组为新增。
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

mkdir -p $OUT/e6mix
echo "== E6 主组：g 扫描 × {ours,mix,oracle,allcloud} × 5 seeds =="
for g in 1024 8192 16384 32768 65536; do
  for pol in ours mix oracle allcloud; do
    for s in 1 2 3 4 5; do
      run $OUT/e6mix "e6_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
        --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=60 --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
  echo "  g=$g -> $(ls $OUT/e6mix | wc -l)"
done
wait

echo "== E6 m=5 组（3^5=243 组合空间）=="
for s in 1 2 3; do
  for pol in ours mix oracle; do
    run $OUT/e6mix "e6_m5_${pol}_s${s}" --mode=E2 --discovery=directory \
      --policy=$pol --N=16 --m=5 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=60 --seed=$s &
    while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
  done
done
wait

echo "== E6 异构批组（lognormal 粒度，m=3，g=16 KB 中位）=="
for s in 1 2 3; do
  for pol in ours mix oracle; do
    run $OUT/e6mix "e6_ln_${pol}_s${s}" --mode=E2 --discovery=directory \
      --policy=$pol --N=16 --m=3 --g=16384 --gdist=lognormal --ctxKB=16 \
      --rttMs=30 --bwUpMbps=30 --duration=60 --seed=$s &
    while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
  done
done
wait
echo "=== E6 DONE: $(ls $OUT/e6mix | wc -l) files ==="
