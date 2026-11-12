#!/bin/bash
# E4（混合负载）+ E2v2/E3v2（上下文门控修正后的重测）
# 说明：2026-10-21 晚修正——云的执行宿主改为"上下文 C 全部到达才开算"，
# 云侧基线 P50 由 43 ms 变为 52 ms，故 E2/E3 全部重测，避免新旧口径混用。
set -e
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/agent-sim
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
cd $NS3

run () { # $1=outdir $2=name args...
  local dir=$1; shift
  local nm=$1; shift
  $BIN "$@" --out=/tmp/x_$nm > /tmp/x_$nm.log 2>&1
  cp /tmp/x_$nm.csv $dir/ 2>/dev/null || true
}

# ---------------- E4：混合负载 ----------------
mkdir -p $OUT/e4_mixed
for bg in none video gaming backup; do
  for bu in 30 10; do
    for pol in ours allcloud alllocal static; do
      for s in 1 2 3 4 5; do
        run $OUT/e4_mixed "e4_${bg}_bu${bu}_${pol}_s${s}" --mode=E4 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=$bu \
          --duration=30 --bg=$bg --seed=$s &
        while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
      done
    done
    echo "E4 bg=$bg bu=$bu done: $(ls $OUT/e4_mixed | wc -l)"
  done
done
wait
echo "E4 ALL: $(ls $OUT/e4_mixed | wc -l)"

# ---------------- E2 v2：门限带 + 比较静态 ----------------
mkdir -p $OUT/e2v2
for g in 128 2048 8192 16384 32768 65536 131072; do
  for pol in ours allcloud alllocal static; do
    for s in 1 2 3 4 5; do
      run $OUT/e2v2 "e2f_A_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
        --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=60 --seed=$s &
      while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
    done
  done
done
echo "E2v2 A done: $(ls $OUT/e2v2 | wc -l)"

# B 部分：16 KB 处 9 个扰动
run_pert () { # name, extra-args
  local nm=$1; shift
  for s in 1 2 3 4 5; do
    run $OUT/e2v2 "e2f_B_${nm}_g16384_s${s}" --mode=E2 --discovery=directory \
      --policy=ours --N=16 --m=3 --g=16384 --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
      --duration=60 --seed=$s "$@" &
    while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
  done
}
run_pert rtt10  --rttMs=10
run_pert rtt60  --rttMs=60
run_pert bu10   --bwUpMbps=10
run_pert bu100  --bwUpMbps=100
run_pert c4     --ctxKB=4
run_pert c64    --ctxKB=64
run_pert m1     --m=1 --g=16384
run_pert m5     --m=5 --g=16384
wait
echo "E2v2 ALL: $(ls $OUT/e2v2 | wc -l)"

# ---------------- E3 v2：Lambda(C) ----------------
mkdir -p $OUT/e3v2
for C in 2 4 8 16 32 64 128 192 256 384 512; do
  for psi in 0 1; do
    for pol in ours allcloud; do
      [ $C -gt 128 ] && [ $pol = allcloud ] && continue   # 大 C 档只需 ours（判据会改判家庭）
      for s in 1 2 3 4 5; do
        run $OUT/e3v2 "e3_C${C}_p${psi}_${pol}_s${s}" --mode=E2 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=65536 --ctxKB=$C --psi=$psi --rttMs=30 \
          --bwUpMbps=30 --duration=60 --seed=$s &
        while [ $(jobs -r | wc -l) -ge 6 ]; do wait -n; done
      done
    done
  done
  echo "E3v2 C=$C done: $(ls $OUT/e3v2 | wc -l)"
done
wait
echo "E3v2 ALL: $(ls $OUT/e3v2 | wc -l)"
echo "=== FULL DONE ==="
