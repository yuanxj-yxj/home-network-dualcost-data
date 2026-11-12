#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E4：混合负载（视频/云游戏/备份）× 上行带宽 × 四策略。

产出：
  (a) B_u=30 Mbps（上行充裕）下四策略的 P50 随背景类型变化
  (b) B_u=10 Mbps（弱上行）下同口径，并叠加成功率（失败＝整块上下文丢失，任务超时）
  (c) 解析：可用上行带宽 B_u^eff 与门限 g2* 的关系（背景流把门限左推）
"""
import glob
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = r"D:\工作区\ns3_work\runs\agentsim\e4v3"
OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"

plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}
HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
        "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
        "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
        "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
COL = {h: i for i, h in enumerate(HEAD)}

# 背景流上行占用（Mbps，标称 B_u=30）
BG_UP = {"none": 0.0, "video": 0.5, "gaming": 6.0, "backup": 24.0}
BG_LAB = {"none": "无背景", "video": "视频点播\n(上行0.5)", "gaming": "云游戏\n(上行6)",
          "backup": "云备份\n(上行24)"}
POL_LAB = {"ours": "本文判据", "allcloud": "全云", "alllocal": "全本地", "static": "静态θ=8KB"}


def stat(v):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, 0.0
    s = sum((x - m) ** 2 for x in v) / (n - 1)
    return m, T95.get(n, 2.571) * math.sqrt(s / n)


def read(f):
    lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
    if lines and lines[0].split(",")[0] == "seed":
        lines = lines[1:]
    return lines[-1].split(",") if lines else None


D = {}
for f in glob.glob(os.path.join(BASE, "*.csv")):
    m = re.match(r"(?:x_)?e4_(\w+?)_bu(\d+)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
    if not m:
        continue
    r = read(f)
    if r is None or len(r) < 32:
        continue
    key = (m.group(1), int(m.group(2)), m.group(3))
    D.setdefault(key, []).append((float(r[COL["p50"]]), float(r[COL["p95"]]),
                                  int(r[COL["taskSent"]]), int(r[COL["taskDone"]])))

print("%-8s %-4s %-9s %-8s %-8s %-8s" % ("bg", "Bu", "policy", "P50", "P95", "succ"))
R = {}
for (bg, bu, pol), rec in sorted(D.items()):
    p50, e50 = stat([x[0] for x in rec])
    p95, _ = stat([x[1] for x in rec])
    succ = sum(x[3] for x in rec) / max(1, sum(x[2] for x in rec))
    R[(bg, bu, pol)] = (p50, e50, p95, succ)
    print("%-8s %-4d %-9s %-8.1f %-8.1f %-8.3f" % (bg, bu, pol, p50, p95, succ))

BGS = ["none", "video", "gaming", "backup"]
POLS = ["ours", "allcloud", "static", "alllocal"]
STYLE = {"ours": ("0.10", "o", "-"), "allcloud": ("0.45", "s", "--"),
         "static": ("0.65", "D", ":"), "alllocal": ("0.82", "^", "-.")}

fig, axes = plt.subplots(1, 3, figsize=(7.4, 3.0))

for ax, bu, title in zip(axes[:2], (30, 10),
                         ("(a) 上行充裕 $B_u$=30 Mbps", "(b) 弱上行 $B_u$=10 Mbps")):
    for pol in POLS:
        xs, ys, es = [], [], []
        for i, bg in enumerate(BGS):
            if (bg, bu, pol) not in R:
                continue
            v, e, _, succ = R[(bg, bu, pol)]
            if v <= 0:
                continue
            xs.append(i)
            ys.append(v)
            es.append(e)
        c, mk, ls = STYLE[pol]
        ax.errorbar(xs, ys, yerr=es, color=c, marker=mk, ls=ls, ms=3.6, lw=1.05,
                    capsize=1.6, elinewidth=0.65, label=POL_LAB[pol], zorder=3,
                    mfc="white" if pol in ("allcloud", "static", "alllocal") else c)
    ax.set_xticks(range(len(BGS)))
    ax.set_xticklabels([BG_LAB[b] for b in BGS], fontsize=6.4)
    ax.set_yscale("log")
    ax.set_ylabel("任务完成时延 $T_{50}$ / ms")
    ax.grid(alpha=0.2, lw=0.45, which="both")
    ax.tick_params(labelsize=7.0, direction="in")
    ax.set_title(title, fontsize=8.2, pad=4)
    # 成功率标注（<1 的柱上标出）
    for i, bg in enumerate(BGS):
        for pol in ("allcloud", "static"):
            if (bg, bu, pol) in R and R[(bg, bu, pol)][3] < 0.999:
                v = R[(bg, bu, pol)][0]
                ax.annotate("成功 %.0f%%" % (100 * R[(bg, bu, pol)][3]),
                            xy=(i, v), xytext=(i + 0.12, v * 1.25), fontsize=5.6,
                            color="0.25")
axes[0].legend(fontsize=6.2, frameon=False, ncol=2, loc="upper left")

# (c) 可用上行带宽 → 门限右移（解析：可用上行越小，云需更大粒度才划算）
ax = axes[2]
A1, A2 = 2.202, 0.088
GAM1 = 5.0
G20 = 19.0 * (A1 - A2) + GAM1 - 8 * 16 / 30 - 30


def g2star(bueff, C=16.0, rc=30.0):
    return (G20 + 8 * C / bueff + rc - GAM1) / (A1 - A2)


bs = np.linspace(2, 60, 300)
ax.plot(bs, [g2star(b) for b in bs], color="0.15", lw=1.2)
for bg in BGS:
    be = 30.0 - BG_UP[bg]
    if be <= 2:
        continue
    ax.plot([be], [g2star(be)], marker="o", ms=4.2, mfc="white", color="0.15", zorder=4)
    ax.annotate(bg, xy=(be, g2star(be)), xytext=(be + 1.5, g2star(be) + 1.2),
                fontsize=6.2, color="0.25")
ax.axhline(16, color="0.55", ls=(0, (3, 2)), lw=0.9)
ax.text(41, 16.6, "$g$=16 KB（本站观测点）", fontsize=6.2, color="0.4")
ax.set_xlabel("可用上行带宽 $B_u^{\\rm eff}$ / Mbps")
ax.set_ylabel("门限 $g_2^{*\\rm eff}$ / KB")
ax.grid(alpha=0.2, lw=0.45)
ax.tick_params(labelsize=7.0, direction="in")
ax.set_title("(c) 背景流挤占上行 → 门限右移", fontsize=8.2, pad=4)

for ax in axes:
    for s in ax.spines.values():
        s.set_linewidth(0.8)
fig.tight_layout(pad=0.6)
p = os.path.join(OUT, "fig07_mixed.png")
fig.savefig(p, dpi=300)
print("wrote", p)
