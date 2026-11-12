#!/bin/bash
# 构建 agent-sim 场景（家庭网络智能体协同仿真）
#
# 三条关键约定（勿改）：
#   1) 只同步 agent-sim.cc，不碰 quic-arscc.cc / quic-comp.cc 等 QUIC 论文的资产；
#   2) 必须用 --targets=agent-sim：本 ns-3 树与 QUIC 论文共用，对方未完成的场景文件
#      会让全量 ./waf build 失败（已实测），限定目标可完全隔离；
#   3) 日志写 /root/ 而非 /tmp：WSL 实例重启会清空 /tmp，此前已因此丢过编译记录。
NS3=$HOME/quic-research/ns-allinone-3.35/ns-3.35
LOG=/root/build_agentsim.log

echo "=== 同步场景文件 ==="
cp /mnt/d/工作区/ns3_work/scratch/agent-sim.cc "$NS3/scratch/agent-sim.cc" || exit 1

echo "=== 编译（仅 agent-sim 目标）==="
cd "$NS3" || exit 1
./waf build --targets=agent-sim -j8 > "$LOG" 2>&1
RC=$?
echo "EXIT=$RC"
grep -nE "error:" "$LOG" | head -20
tail -3 "$LOG"
exit $RC
