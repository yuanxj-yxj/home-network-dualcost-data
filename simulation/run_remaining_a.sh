#!/bin/bash
# 遗留实验批次 A：① E4b 强制 home 重测  ⑤ B_u=2/4 Mbps  ③ E3 扫到 512 KB
# 均无代码改动，纯参数运行。JOBS 默认 7（14 核，单线程运行）。
set -u
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
JOBS=${JOBS:-7}
cd "$NS3" || exit 1

run () {  # run <dir> <name> <args...>
  local dir=$1; shift; local nm=$1; shift
  $BIN "$@" --out="/tmp/y_$nm" > "/tmp/y_$nm.log" 2>&1
  cp "/tmp/y_$nm.csv" "$dir/" 2>/dev/null || true
}

# ---------------- ① E4b：24/32/48 KB 强制家庭执行（alllocal） ----------------
mkdir -p "$OUT/e4b_thresh"
echo "[1] E4b alllocal 24/32/48 KB"
for bg in none backup; do
  for g in 24576 32768 49152; do
    for s in 1 2 3 4 5; do
      run "$OUT/e4b_thresh" "e4b_${bg}_g${g}_alllocal_s${s}" --mode=E2 --discovery=directory \
        --policy=alllocal --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=30 \
        --duration=40 --bg=$bg --seed=$s &
      while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
    done
  done
done
wait
echo "  done: $(ls $OUT/e4b_thresh/*alllocal* 2>/dev/null | wc -l) files"

# ---------------- ⑤ B_u = 2 / 4 Mbps（推论 2.2 门槛以下） ----------------
mkdir -p "$OUT/e2_bu_low"
echo "[5] B_u 2/4 Mbps"
for bu in 2 4; do
  for g in 8192 16384 32768 65536; do
    for pol in ours allcloud alllocal; do
      for s in 1 2 3 4 5; do
        run "$OUT/e2_bu_low" "x_e2bu_bu${bu}_g${g}_${pol}_s${s}" --mode=E2 --discovery=directory \
          --policy=$pol --N=16 --m=3 --g=$g --ctxKB=16 --rttMs=30 --bwUpMbps=$bu \
          --duration=60 --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
  done
done
wait
echo "  done: $(ls $OUT/e2_bu_low/*.csv 2>/dev/null | wc -l) files"

# ---------------- ③ E3：C 扫到 512 KB ----------------
mkdir -p "$OUT/e3_wide"
echo "[3] E3 C sweep -> 512 KB"
for C in 1 2 4 8 16 32 64 128 256 512; do
  for psi in 0 1; do
    for pol in allcloud ours; do
      for s in 1 2 3 4 5; do
        run "$OUT/e3_wide" "x_e3_C${C}_p${psi}_${pol}_s${s}" --mode=E3 --policy=$pol \
          --ctxKB=$C --psi=$psi --g=65536 --duration=60 --seed=$s &
        while [ $(jobs -r | wc -l) -ge $JOBS ]; do wait -n; done
      done
    done
  done
  echo "  C=$C KB done ($(ls $OUT/e3_wide/*.csv 2>/dev/null | wc -l) files)"
done
wait
echo "ALL DONE: e4b=$(ls $OUT/e4b_thresh/*.csv | wc -l) bu=$(ls $OUT/e2_bu_low/*.csv | wc -l) e3=$(ls $OUT/e3_wide/*.csv | wc -l)"
