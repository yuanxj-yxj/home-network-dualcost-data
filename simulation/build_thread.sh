#!/bin/bash
# 构建 thread-edge 场景（Thread / 802.15.4 末梢实测）
#
# 约定（与 build_agentsim.sh 同构）：
#   1) 只同步 thread-edge.cc，不碰 agent-sim.cc / quic-arscc.cc；
#   2) 必须用 --targets=thread-edge 隔离 QUIC / agent 资产；
#   3) 日志写 /root/ 而非 /tmp（WSL 重启清空 /tmp）。
NS3=$HOME/quic-research/ns-allinone-3.35/ns-3.35
LOG=/root/build_thread.log

echo "=== 同步场景文件 ==="
cp /mnt/d/工作区/ns3_work/scratch/thread-edge.cc "$NS3/scratch/thread-edge.cc" || exit 1

echo "=== 编译（仅 thread-edge 目标）==="
cd "$NS3" || exit 1
./waf build --targets=thread-edge -j8 > "$LOG" 2>&1
RC=$?
echo "EXIT=$RC"
grep -nE "error:" "$LOG" | head -30
tail -3 "$LOG"
exit $RC
