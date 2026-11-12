#!/bin/bash
# 运行 Thread 边缘实测：T1 发现扫描（10×5 = 50 次）+ T2 执行放置扫描
#
# T2 三段口径（详见 05_Thread边缘实测方案.md §5）：
#   A. 边际（N=1 单 leaf，间隔 > 2×空口时长排空链路）→ τ_lb(g) 仿射系数 a_lb/γ_lb
#      g ∈ {512..16000}，须 < 6LoWPAN 分片上限 16376 B（RFC 4944 datagram_size 11bit×8，
#      ns-3.35 IsEntire() 用截断值判重组完成，超过即静默丢弃——已核源码）
#   B. 上限验证（g=20480）：预期 Thread 侧零样本、WAN 侧正常（IPv4 本地分片不受限），
#      证明丢弃是 Thread 段特有的协议级约束
#   C. 共享（N=4 同步并发）→ 排队放大倍数
set -e
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
export LD_LIBRARY_PATH=$NS3/build/lib
BIN=$NS3/build/scratch/thread-edge
OUT=/mnt/d/工作区/ns3_work/runs/thread
mkdir -p $OUT/disc $OUT/place
cd $NS3

# T1：发现两段律 over 802.15.4
#   N 扫描（802.15.4 的 N* 预期远小于 Wi-Fi 的 ~112）
echo "== T1 发现扫描（802.15.4 默认 BEB，对应命题1近线性段）=="
for N in 8 16 32 48 64 96 128 160 192 224; do
  for s in 1 2 3 4 5; do
    $BIN --camp=T1 --N=$N --pinBe=0 --seed=$s --duration=30 \
         --out=$OUT/disc/x_td_N${N}_be0_s${s} > /dev/null 2>&1
  done
  echo "  N=$N done"
done
echo "=== T1 DONE: $(ls $OUT/disc | wc -l) files ==="

# ---------- T2 工具函数：分片数 / 空口时长 / 发送间隔 / 仿真时长 ----------
# 每 6LoWPAN 分片 ≈ 110 B 载荷（114 B l2Mtu − 4 B FRAGN 头），每帧空口 ≈ 114 B / 250 kbps ≈ 4.06 ms
frags_of () { awk -v g=$1 'BEGIN{printf "%d", int((g+48+109)/110)}'; }
air_ms ()  { awk -v n=$1 'BEGIN{printf "%.1f", n*4.06}'; }
iv_marg () { awk -v a=$1 'BEGIN{v=2*a*1.4+200; if(v<1000)v=1000; printf "%d", int(v)}'; }
iv_sh ()   { awk -v a=$1 'BEGIN{v=4*a*1.4+200; if(v<1000)v=1000; printf "%d", int(v)}'; }
dur_of ()  { awk -v iv=$1 'BEGIN{printf "%.1f", 2+6*iv/1000+4}'; }

# ---------- T2-A 边际扫描（N=1） ----------
echo "== T2-A 边际扫描（N=1，τ_lb(g) 仿射系数）=="
for g in 512 1024 2048 4096 8192 12288 16000; do
  NF=$(frags_of $g); AIR=$(air_ms $NF); IV=$(iv_marg $AIR); DUR=$(dur_of $IV)
  for s in 1 2 3 4 5; do
    $BIN --camp=T2 --N=1 --g=$g --seed=$s --duration=$DUR --sendIntervalMs=$IV \
         --out=$OUT/place/x_t2_g${g}_s${s} > /dev/null 2>&1
  done
  echo "  g=$g frags=$NF air=${AIR}ms iv=${IV}ms dur=${DUR}s done"
done

# ---------- T2-B 上限验证（g=20480 > 16376） ----------
echo "== T2-B 6LoWPAN 数据报上限验证（g=20480）=="
NF=$(frags_of 20480); AIR=$(air_ms $NF); IV=$(iv_marg $AIR); DUR=$(dur_of $IV)
for s in 1 2 3; do
  $BIN --camp=T2 --N=1 --g=20480 --seed=$s --duration=$DUR --sendIntervalMs=$IV \
       --out=$OUT/place/x_t2over_g20480_s${s} > /dev/null 2>&1
done
echo "  g=20480 frags=$NF iv=${IV}ms done（预期 lb 零样本、bc 正常）"

# ---------- T2-C 共享口径（N=4 同步并发） ----------
echo "== T2-C 共享扫描（N=4 同步，排队放大）=="
for g in 2048 8192; do
  NF=$(frags_of $g); AIR=$(air_ms $NF); IV=$(iv_sh $AIR); DUR=$(dur_of $IV)
  for s in 1 2; do
    $BIN --camp=T2 --N=4 --g=$g --seed=$s --duration=$DUR --sendIntervalMs=$IV \
         --out=$OUT/place/x_t2sh_g${g}_s${s} > /dev/null 2>&1
  done
  echo "  g=$g frags=$NF air=${AIR}ms iv=${IV}ms dur=${DUR}s done"
done

echo "=== T2 DONE: $(ls $OUT/place | wc -l) files ==="
