#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命题 1（发现两段律）正式图。

左图：发现时滞中位数 discP50 随设备数 N 的变化（双对数），两条曲线
      —— BEB 自适应（真实 Wi-Fi）与钉死 CW_min（禁用 BEB）；
      N=112 处钉死曲线逐 seed 散点展示双峰过渡，N=128 为删失点。
右图：每次成功应答的平均重传次数（碰撞强度的机理证据）。

数据：ns3_work/runs/agentsim/{e1_pinCW_v2,e1_w0_v2}，5 seeds/点。
"""
import glob
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = r"D:\工作区\ns3_work\runs\agentsim"
OUTDIR = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"
os.makedirs(OUTDIR, exist_ok=True)

# 期刊排版：中文用宋体，西文用 Times New Roman 风格
plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,"
        "wanUpBytes,wanDnBytes,payloadBytes,lambda,airtimeS,taskFailed,rounds,"
        "missingResp,discP50,discP95,discP50us,discP95us,txBusyS,retxTotal,"
        "rspTxTotal,rspPhyTxTotal,wanUpRealB,wanDnRealB").split(",")
COL = {h: i for i, h in enumerate(HEAD)}

T95 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}
CENSOR_US = 360000.0  # queryTimeoutMs(60) x (maxRequery(5)+1)


def load(sub, prefix):
    """返回 {N: [(disc_us, retx_per_resp), ...]}"""
    out = {}
    for f in glob.glob(os.path.join(BASE, sub, "%s_N*_s*.csv" % prefix)):
        m = re.search(r"_N(\d+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        n = int(m.group(1))
        with open(f, encoding="utf-8") as fh:
            lines = [l.strip() for l in fh if l.strip()]
        if lines and lines[0].split(",")[0] == "seed":
            lines = lines[1:]
        if not lines:
            continue
        r = lines[-1].split(",")
        if len(r) < 26:  # v3 数据为 28 列（有 rspTxTotal），不含后加的 WAN 真实字节两列
            continue
        rounds = max(int(r[COL["rounds"]]), 1)
        nn = int(r[COL["N"]])
        # r̄ 的分母必须是"应答帧实际发送次数"，不能用 rounds×N：
        # 重查询会让同一轮发出多于 N 个应答，用 rounds×N 会在高密度段高估 r̄。
        sends = rounds * nn
        if len(r) > COL.get("rspTxTotal", 10 ** 6):
            try:
                sends = max(int(r[COL["rspTxTotal"]]), 1)
            except ValueError:
                pass
        out.setdefault(n, []).append((float(r[COL["discP50us"]]),
                                      int(r[COL["retxTotal"]]) / float(sends),
                                      float(r[COL["txBusyS"]])))
    return out


def stat(vals):
    n = len(vals)
    m = sum(vals) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return m, T95.get(n, 2.571) * math.sqrt(var / n)


pin = load("e1_v3/pin", "pin")
beb = load("e1_v3/beb", "sweepW0")
NS = sorted(set(pin) & set(beb))
print("N 点：", NS)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.0))

# ---------- 左图：discP50 vs N ----------
for dat, lab, color, mk, ls in ((beb, "BEB 自适应", "0.20", "o", "-"),
                                (pin, "钉死 $CW_{\\min}$（禁用 BEB）", "0.55", "s", "--")):
    xs, ys, es = [], [], []
    for n in NS:
        m, e = stat([d for d, _, _ in dat[n]])
        xs.append(n)
        ys.append(m / 1000.0)
        es.append(e / 1000.0)
    ax1.errorbar(xs, ys, yerr=es, color=color, marker=mk, ls=ls, ms=4.2,
                 lw=1.2, capsize=2.0, elinewidth=0.8, mfc="white" if mk == "s" else color,
                 label=lab, zorder=3)

# N=112 钉死组逐 seed 散点：展示双峰过渡（相变涨落）
if 112 in pin:
    ax1.scatter([112] * len(pin[112]), [d / 1000.0 for d, _, _ in pin[112]],
                marker="x", s=16, color="0.35", lw=0.8, zorder=4,
                label="钉死组 N=112 逐种子")

# 删失标记：N=128 钉死组触顶
ax1.plot([128], [CENSOR_US / 1000.0], marker="s", ms=5.5, mfc="white",
         mec="0.55", mew=1.0, ls="none", zorder=5)
ax1.annotate("≥360（删失）", xy=(128, 360), xytext=(26, 300),
             fontsize=7.5, color="0.35",
             arrowprops=dict(arrowstyle="->", lw=0.7, color="0.45"))

# N* 临界带
ax1.axvspan(96, 128, color="0.88", alpha=0.55, lw=0, zorder=1)
ax1.text(108, 0.62, "$N^*$ 临界带", fontsize=7.5, color="0.30", ha="center")

ax1.set_xscale("log", base=2)
ax1.set_yscale("log")
ax1.set_xticks(NS)
ax1.set_xticklabels([str(n) for n in NS], fontsize=6.2, rotation=45)
ax1.minorticks_off()
ax1.set_xlim(1.7, 170)
ax1.set_ylim(0.5, 500)
ax1.set_xlabel("设备数 $N$")
ax1.set_ylabel("发现时滞中位数 $D_{50}$ / ms")
ax1.grid(alpha=0.22, lw=0.5, which="major")
ax1.tick_params(labelsize=7.5, direction="in")
ax1.legend(fontsize=6.6, frameon=False, loc="upper left")
ax1.set_title("(a) 发现时滞随密度的两段律", fontsize=8.5, pad=4)

# ---------- 右图：发现阶段真实空口占用 vs N ----------
# 不用 r̄ 作右图：MAC 重传上限（long retry limit）会把 r̄ 截断在 3.5–3.8，
# 崩溃点两组几乎相同，反而掩盖差异；空口占用是单调的承载代价，分化清晰。
for dat, lab, color, mk, ls in ((beb, "BEB 自适应", "0.20", "o", "-"),
                                (pin, "钉死 $CW_{\\min}$（禁用 BEB）", "0.55", "s", "--")):
    xs, ys = [], []
    for n in NS:
        xs.append(n)
        ys.append(stat([b for _, _, b in dat[n]])[0])
    ax2.plot(xs, ys, color=color, marker=mk, ls=ls, ms=4.2, lw=1.2,
             mfc="white" if mk == "s" else color, label=lab, zorder=3)

ax2.set_xscale("log", base=2)
ax2.set_xticks(NS)
ax2.set_xticklabels([str(n) for n in NS], fontsize=6.2, rotation=45)
ax2.minorticks_off()
ax2.set_xlim(1.7, 170)
ax2.set_xlabel("设备数 $N$")
ax2.set_ylabel("发现阶段空口占用 $D_{\\mathrm{air}}$ / s")
ax2.grid(alpha=0.22, lw=0.5)
ax2.tick_params(labelsize=7.5, direction="in")
ax2.legend(fontsize=6.6, frameon=False, loc="upper left")
ax2.set_title("(b) 发现的承载代价：空口占用", fontsize=8.5, pad=4)

for ax in (ax1, ax2):
    for s in ax.spines.values():
        s.set_linewidth(0.8)

fig.tight_layout(pad=0.6)
p = os.path.join(OUTDIR, "fig1_discovery_law.png")
fig.savefig(p, dpi=300)
print("wrote", p)

# 关键数字复核
for n in NS:
    mb, _ = stat([d for d, _, _ in beb[n]])
    mp, _ = stat([d for d, _, _ in pin[n]])
    rb, _ = stat([r for _, r, _ in beb[n]])
    rp, _ = stat([r for _, r, _ in pin[n]])
    print("N=%3d  BEB %8.0f us r=%.2f | PIN %9.0f us r=%.2f | 比值 %.1f"
          % (n, mb, rb, mp, rp, mp / mb))
