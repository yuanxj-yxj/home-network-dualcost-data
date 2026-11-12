#!/bin/bash
# E1：发现开销隔离实验（验证命题 1）
#   设备密度 N × 发现模式 × seeds
# 注意：
#   1) 必须设 LD_LIBRARY_PATH=build/lib，否则找不到 libns3.35-*；
#   2) --link=thread 当前不可用（ns-3 的 6LoWPAN 只处理 IPv6，IPv4 包被丢弃），已移出扫描；
#   3) 空口时长按基本速率折算（basicMbps，默认 6 Mbps），可用 --basicMbps 覆盖。
set -u
WSL_DIR=~/quic-research/ns-allinone-3.35/ns-3.35
BIN=$WSL_DIR/build/scratch/agent-sim
OUT=/mnt/d/工作区/ns3_work/runs/agentsim
mkdir -p "$OUT"
rm -f "$OUT/e1.csv"
export LD_LIBRARY_PATH=$WSL_DIR/build/lib

for LINK in wifi5 wifi24; do
  for DISC in multicast directory cache; do
    for N in 8 16 32 64 128; do
      for SEED in $(seq 1 10); do
        "$BIN" --mode=E1 --link=$LINK --discovery=$DISC --N=$N \
               --seed=$SEED --duration=20 --out="$OUT/e1_${LINK}_${DISC}_N${N}_s${SEED}" \
               > /dev/null 2>&1
        f="$OUT/e1_${LINK}_${DISC}_N${N}_s${SEED}.csv"
        if [ -f "$f" ]; then
          [ -s "$OUT/e1.csv" ] || head -1 "$f" > "$OUT/e1.csv"
          tail -n +2 "$f" >> "$OUT/e1.csv"
          rm -f "$f"
        fi
      done
      echo "[$LINK/$DISC] N=$N done"
    done
  done
done
echo "E1 done -> $OUT/e1.csv"
