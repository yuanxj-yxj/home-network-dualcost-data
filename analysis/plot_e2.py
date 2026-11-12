#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2 正式图（命题 2）：(a) 时延—粒度门限带；(b) 比较静态（16 KB 处各扰动）。

(a) 四条策略曲线 + 解析门限 g1*/g2* 竖线
(b) g=16 KB 时各扰动下的 P50，并用实心/空心标记区分"上云/留家庭"
数据：ns3_work/runs/agentsim/e2_formal/
"""
import glob
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.environ.get("NS3DATA", r"D://工作区//ns3_work//runs//agentsim//e2v3")
OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
        "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
        "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
        "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
COL = {h: i for i, h in enumerate(HEAD)}
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
    if not lines:
        return None
    r = lines[-1].split(",")
    return r if len(r) > 30 else None


A = {}   # (policy, g) -> [(p50, p95, wanUpReal)]
B = {}   # (pert, g) -> [...]
for f in glob.glob(os.path.join(BASE, "*.csv")):
    b = os.path.basename(f)
    r = read(f)
    if r is None:
        continue
    rec = (float(r[COL["p50"]]), float(r[COL["p95"]]), int(r[COL["wanUpRealB"]]))
    m = re.match(r"(?:x_)?(?:e2f_)?A_g(\d+)_(\w+)_s(\d+)\.csv$", b)
    if m:
        A.setdefault((m.group(2), int(m.group(1))), []).append(rec)
        continue
    m = re.match(r"(?:x_)?(?:e2f_)?B_([a-z0-9]+)_g(\d+)_s(\d+)\.csv$", b)
    if m:
        B.setdefault((m.group(1), int(m.group(2))), []).append(rec)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.1))

# ---------------- (a) 门限带 ----------------
STYLE = {"ours": ("0.10", "o", "-", "本文判据"), "allcloud": ("0.40", "s", "--", "全云"),
         "alllocal": ("0.62", "^", "-.", "全本地"),
         "static": ("0.80", "D", ":", r"静态 $\theta$=8 KB")}
GS = sorted({g for (_, g) in A})
for pol in ("ours", "allcloud", "alllocal", "static"):
    xs, ys, es = [], [], []
    for g in GS:
        rec = A.get((pol, g))
        if not rec:
            continue
        m, e = stat([x[0] for x in rec])
        if m <= 0:
            continue
        xs.append(g / 1024.0 if g >= 1024 else g / 1024.0)
        ys.append(m)
        es.append(e)
    c, mk, ls, lab = STYLE[pol]
    ax1.errorbar(xs, ys, yerr=es, color=c, marker=mk, ls=ls, ms=4.0, lw=1.1,
                 capsize=1.8, elinewidth=0.7,
                 mfc="white" if pol in ("allcloud", "static") else c, label=lab, zorder=3)

ax1.set_xscale("log", base=2)
ax1.set_yscale("log")
ax1.set_xticks([0.125, 0.5, 2, 8, 32])
ax1.set_xticklabels(["0.125", "0.5", "2", "8", "32"])
ax1.minorticks_off()
ax1.set_xlabel("子任务粒度 $g$ / KB")
ax1.set_ylabel("任务完成时延中位数 $T_{50}$ / ms")
ax1.axvline(12 / 1024.0, color="0.55", ls=":", lw=0.9)
ax1.axvline(19.0, color="0.55", ls=":", lw=0.9)
ax1.annotate("$g_1^*$", xy=(12 / 1024.0, 0.9), fontsize=7, color="0.45")
ax1.annotate("$g_2^*$", xy=(21, 0.9), fontsize=7, color="0.45")
ax1.grid(alpha=0.22, lw=0.5)
ax1.tick_params(labelsize=7.2, direction="in")
ax1.legend(fontsize=6.4, frameon=False, loc="upper left")
ax1.set_title("(a) 时延—粒度与门限带", fontsize=8.5, pad=4)

# ---------------- (b) 比较静态（g=16 KB） ----------------
ORDER = [("base", "基线"), ("rtt10", "$r_c$=10"), ("rtt60", "$r_c$=60"),
         ("bu10", "$B_u$=10"), ("bu100", "$B_u$=100"),
         ("c4", "$C$=4"), ("c64", "$C$=64"), ("m1", "$m$=1"), ("m5", "$m$=5")]
rows = []
for key, lab in ORDER:
    if key == "base":
        rec = A.get(("ours", 16384))
    else:
        rec = B.get((key, 16384))
    if not rec:
        continue
    p50, e = stat([x[0] for x in rec])
    up = sum(1 for x in rec if x[2] > 0) / len(rec)  # 上云比例
    rows.append((lab, p50, e, up))

xs = range(len(rows))
vals = [r[1] for r in rows]
for i, (lab, v, e, up) in enumerate(rows):
    ax2.bar(i, v, width=0.66, color="0.72" if up > 0.5 else "0.90",
            edgecolor="0.25", linewidth=0.7, hatch="//" if up > 0.5 else None,
            zorder=3)
    ax2.errorbar(i, v, yerr=e, color="0.2", lw=0.8, capsize=1.8, zorder=4)
    ax2.text(i, v + 4, "%.0f" % v, ha="center", fontsize=6.6, color="0.15")

ax2.set_xticks(list(xs))
ax2.set_xticklabels([r[0] for r in rows], fontsize=6.6, rotation=35)
ax2.set_ylabel("$T_{50}$ / ms（$g$=16 KB）")
ax2.set_xlabel("参数扰动（斜纹＝实际落点转为云）")
ax2.grid(axis="y", alpha=0.22, lw=0.5)
ax2.tick_params(labelsize=7.2, direction="in")
ax2.set_title("(b) 门限的比较静态", fontsize=8.5, pad=4)

for ax in (ax1, ax2):
    for s in ax.spines.values():
        s.set_linewidth(0.8)
fig.tight_layout(pad=0.6)
p = os.path.join(OUT, "fig2_threshold_band.png")
fig.savefig(p, dpi=300)
print("wrote", p)
for lab, v, e, up in rows:
    print("%-10s T50=%.1f ms  cloudFrac=%.1f" % (lab, v, up))
