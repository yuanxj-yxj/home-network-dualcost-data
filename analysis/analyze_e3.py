#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E3（命题 3）：承载放大系数 Lambda(C) 与缓存增益 Theta(m)。

口径与仿真 CSV 一致：Lambda = (wanUpRealB + wanDnRealB) / (m*g)，
即"每轮有效载荷 m*g 所对应的全程 WAN 字节倍数"。
解析：全云 psi=0 时 Lambda = R*(C+g+rho*g)/(m*g)，psi=1 时 C 项降为 C/m。
单峰自限：当 g2*(C) 左移越过 g 时，ours 改走家庭，Lambda 塌回 ~0。
"""
import glob
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = os.environ.get("NS3DATA", r"D://工作区//ns3_work//runs//agentsim//e3v3")
OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"

plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

M, G_KB, RHO, ROUNDS = 3, 64.0, 0.5, 150
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


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


HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
        "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
        "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
        "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
COL = {h: i for i, h in enumerate(HEAD)}

D = {}   # (C, psi, pol) -> list of dict
for f in glob.glob(os.path.join(BASE, "*e3_C*_p*_*.csv")):
    m = re.match(r"(?:x_)?e3_C(\d+)_p(\d)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
    if not m:
        continue
    r = read(f)
    if r is None or len(r) < 32:
        continue
    key = (int(m.group(1)), int(m.group(2)), m.group(3))
    D.setdefault(key, []).append({
        "p50": float(r[COL["p50"]]),
        "up": int(r[COL["wanUpRealB"]]),
        "dn": int(r[COL["wanDnRealB"]]),
        "lam": float(r[COL["lambda"]]),
        "done": int(r[COL["taskDone"]]),
    })

print("%-6s %-4s %-9s %-14s %-14s %-9s %-7s" %
      ("C", "psi", "policy", "Lambda_real", "Lambda_csv", "T50", "done"))
RES = {}
for key in sorted(D):
    C, psi, pol = key
    rec = D[key]
    lam_r, e_r = stat([x["up"] + x["dn"] for x in rec])
    lam_r /= M * G_KB * 1024.0
    e_r /= M * G_KB * 1024.0
    lam_c, _ = stat([x["lam"] for x in rec])
    p50, e50 = stat([x["p50"] for x in rec])
    done = sum(x["done"] for x in rec) / len(rec)
    RES[key] = (lam_r, e_r, p50, e50)
    ana = ROUNDS * ((C / (M if psi else 1.0)) + G_KB * (1 + RHO)) / (M * G_KB)
    print("%-6d %-4d %-9s %-14.1f %-14.1f %-9.1f %-7.0f  (解析 %.1f)"
          % (C, psi, pol, lam_r, lam_c, p50, done, ana))

# ---------------- 图 6 ----------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.0))

CS = sorted({c for (c, _, _) in RES})
STYLE = {("ours", 0): ("0.10", "o", "-", "ours，$\\psi{=}0$"),
         ("ours", 1): ("0.10", "o", "--", "ours，缓存 $\\psi{=}1$"),
         ("allcloud", 0): ("0.55", "s", "-.", "全云，$\\psi{=}0$"),
         ("allcloud", 1): ("0.55", "s", ":", "全云，缓存 $\\psi{=}1$")}
for pol in ("ours", "allcloud"):
    for psi in (0, 1):
        xs, ys, es = [], [], []
        for c in CS:
            if (c, psi, pol) not in RES:
                continue
            v, e, _, _ = RES[(c, psi, pol)]
            xs.append(c)
            ys.append(v)
            es.append(e)
        col, mk, ls, lab = STYLE[(pol, psi)]
        ax1.errorbar(xs, ys, yerr=es, color=col, marker=mk, ls=ls, ms=3.6, lw=1.1,
                     capsize=1.8, elinewidth=0.7,
                     mfc="white" if (pol, psi) != ("ours", 0) else col, label=lab,
                     zorder=3)

ax1.set_xlabel("上下文体积 $C$ / KB")
ax1.set_ylabel("承载放大系数 $\\Lambda$（每 $mg$ 载荷的 WAN 字节）")
ax1.grid(alpha=0.22, lw=0.5)
ax1.legend(fontsize=6.3, frameon=False)
ax1.tick_params(labelsize=7.0, direction="in")
ax1.set_title("(a) $\\Lambda(C)$ 与缓存增益", fontsize=8.3, pad=4)

# (b) 缓存增益：C=128 处 psi0/psi1 之比 vs 解析 m；以及 C 项分解
cs_key = 64   # C=128 档存在 UDP 发送缓冲溢出（编排器计数比链路实测高 ~11%），缓存增益改用 C=64 干净档
if (cs_key, 0, "allcloud") in RES and (cs_key, 1, "allcloud") in RES:
    l0 = RES[(cs_key, 0, "allcloud")][0]
    l1 = RES[(cs_key, 1, "allcloud")][0]
    # Lambda = R*(C_eff + g(1+rho))/(m g)：C 项 = Lambda - R*g(1+rho)/(m g)
    base = ROUNDS * G_KB * (1 + RHO) / (M * G_KB)
    c0, c1 = l0 - base, l1 - base
    bars = [("无缓存 $C$ 项", c0), ("缓存 $C/m$ 项", c1)]
    ax2.bar([0, 1], [c0, c1], width=0.5, color=["0.75", "0.45"],
            edgecolor="0.2", lw=0.7, zorder=3)
    for i, (_, v) in enumerate(bars):
        ax2.text(i, v + 1.5, "%.1f" % v, ha="center", fontsize=7.0)
    ax2.annotate("", xy=(1, c1 + 9), xytext=(0, c0 + 9),
                 arrowprops=dict(arrowstyle="<|-|>", lw=0.8, color="0.25"))
    ax2.text(0.5, c0 + 11, "$\\Theta(m)$：比值 %.1f（解析 $m{=}3$）" % (c0 / c1),
             ha="center", fontsize=6.8, color="0.2")
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["$\\psi{=}0$", "$\\psi{=}1$"], fontsize=7.5)
    ax2.set_xlim(-0.6, 1.6)
    ax2.set_ylim(0, c0 * 1.35)
    ax2.set_ylabel("$\\Lambda$ 的上下文项（$C{=}$64 KB，全云）")
    ax2.grid(axis="y", alpha=0.22, lw=0.5)
    ax2.tick_params(labelsize=7.0, direction="in")
    ax2.set_title("(b) 缓存增益 $\\Theta(m)$", fontsize=8.3, pad=4)

for ax in (ax1, ax2):
    for s in ax.spines.values():
        s.set_linewidth(0.8)
fig.tight_layout(pad=0.6)
p = os.path.join(OUT, "fig06_lambda.png")
fig.savefig(p, dpi=300)
print("wrote", p)
