#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图 5：门限 g2* 对上下文 C、上行带宽 B_u、云侧 RTT r_c 的比较静态（推论 2.1）。

解析曲线：g2* = (gamma2 - gamma1) / (a1 - a2)，
  gamma2 = gamma2_0 + 8C/B_u + r_c，参数按 4.1 节标定
  （a1=2.202 ms/KB, a2=0.088 ms/KB, gamma1=5 ms, gamma2_0 校准使
   基线 (C=16 KB, B_u=30 Mbps, r_c=30 ms) 处 g2*=19 KB）。
实测标记：E2 B 部分扰动组在 g=16 KB 处的实际落点（P50，走云者以实心云形示出）。
"""
import glob
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = os.environ.get("NS3DATA", r"D://工作区//ns3_work//runs//agentsim//e2v3")
OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"

plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

A1, A2 = 2.202, 0.088          # ms/KB（kappa/f1、kappa/f2 + 传输斜率，取 4.1 节）
GAMMA1 = 5.0                   # ms
C0, BU0, RC0 = 16.0, 30.0, 30.0
G2_BASE = 19.0                 # KB（基线门限，与图 2/正文一致）
GAMMA20 = G2_BASE * (A1 - A2) + GAMMA1 - 8 * C0 / BU0 - RC0


def g2star(C=16.0, Bu=30.0, rc=30.0):
    gam2 = GAMMA20 + 8.0 * C / Bu + rc
    return (gam2 - GAMMA1) / (A1 - A2)


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


A, B = {}, {}
for f in glob.glob(os.path.join(BASE, "*.csv")):
    b = os.path.basename(f)
    r = read(f)
    if r is None:
        continue
    rec = (float(r[10]), float(r[11]), int(r[28]))   # p50, p95, wanUpRealB
    m = re.match(r"(?:e2f_)?A_g(\d+)_(\w+)_s(\d+)\.csv$", b)
    if m:
        A.setdefault((m.group(2), int(m.group(1))), []).append(rec)
        continue
    m = re.match(r"(?:e2f_)?B_([a-z0-9]+)_g(\d+)_s(\d+)\.csv$", b)
    if m:
        B.setdefault((m.group(1), int(m.group(2))), []).append(rec)

# 实测：各扰动下 g=16 KB 的 P50 与是否上云
MEAS = []
ORDER = [("base", None, None, None, "基线"),
         ("c4", "C", 4.0, None, "$C$=4"),
         ("c64", "C", 64.0, None, "$C$=64"),
         ("bu10", "B_u", None, None, "$B_u$=10"),
         ("bu100", "B_u", None, None, "$B_u$=100"),
         ("rtt10", "r_c", None, 10.0, "$r_c$=10"),
         ("rtt60", "r_c", None, 60.0, "$r_c$=60")]
for key, var, cval, rcval, lab in ORDER:
    rec = A.get(("ours", 16384)) if key == "base" else B.get((key, 16384))
    if not rec:
        continue
    p50, e = stat([x[0] for x in rec])
    up = sum(1 for x in rec if x[2] > 0) / len(rec)
    if key == "base":
        C, Bu, rc = C0, BU0, RC0
    elif var == "C":
        C, Bu, rc = cval, BU0, RC0
    elif var == "B_u":
        C, Bu, rc = C0, (10.0 if key == "bu10" else 100.0), RC0
    else:
        C, Bu, rc = C0, BU0, rcval
    MEAS.append((key, C, Bu, rc, p50, e, up > 0.5, lab))

fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.75))

# (a) g2* vs C
ax = axes[0]
cs = np.linspace(0, 128, 200)
ax.plot(cs, [g2star(C=c) for c in cs], color="0.15", lw=1.2)
ax.set_xlabel("上下文 $C$ / KB")
ax.set_ylabel("$g_2^*$ / KB")
# 实测落点
for key, C, Bu, rc, p50, e, up, lab in MEAS:
    if not lab.startswith("$C$") and lab != "基线":
        continue
    g2v = g2star(C=C, Bu=Bu, rc=rc)
    ax.errorbar(C, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                capsize=1.5, zorder=4)
    if key == "c4":
        continue
    ax.annotate(("%d ms" % p50) + ("→云" if up else "→家庭"), xy=(C, g2v),
                xytext=(C + 4, g2v + (2.5 if key == "base" else 1.5)),
                fontsize=5.8, color="0.25")
ax.text(0.97, 0.06, "$B_u{=}30$，$r_c{=}30$", transform=ax.transAxes, ha="right",
        fontsize=6.0, color="0.45")
ax.set_title("(a) $\\partial g_2^*/\\partial C>0$", fontsize=8.0, pad=3)

# (b) g2* vs B_u
ax = axes[1]
bus = np.linspace(5, 120, 200)
ax.plot(bus, [g2star(Bu=b) for b in bus], color="0.15", lw=1.2)
ax.set_xlabel("上行带宽 $B_u$ / Mbps")
for key, C, Bu, rc, p50, e, up, lab in MEAS:
    if not lab.startswith("$B_u$"):
        continue
    g2v = g2star(C=C, Bu=Bu, rc=rc)
    ax.errorbar(Bu, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                capsize=1.5, zorder=4)
    dx, dy = (-45, -2.6) if Bu > 50 else (4, -4.0)
    ax.annotate(("%d ms" % p50) + ("→云" if up else "→家庭"), xy=(Bu, g2v),
                xytext=(Bu + dx, g2v + dy), fontsize=5.8, color="0.25")
ax.text(0.97, 0.90, "$C{=}16$，$r_c{=}30$", transform=ax.transAxes, ha="right",
        fontsize=6.0, color="0.45")
ax.set_title("(b) $\\partial g_2^*/\\partial B_u<0$", fontsize=8.0, pad=3)

# (c) g2* vs r_c
ax = axes[2]
rcs = np.linspace(5, 90, 200)
ax.plot(rcs, [g2star(rc=r) for r in rcs], color="0.15", lw=1.2)
ax.set_xlabel("云侧 RTT $r_c$ / ms")
for key, C, Bu, rc, p50, e, up, lab in MEAS:
    if not lab.startswith("$r_c$"):
        continue
    g2v = g2star(C=C, Bu=Bu, rc=rc)
    ax.errorbar(rc, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                capsize=1.5, zorder=4)
    ax.annotate(("%d ms" % p50) + ("→云" if up else "→家庭"), xy=(rc, g2v),
                xytext=(rc + 3, g2v + 1.2), fontsize=5.8, color="0.25")
ax.text(0.97, 0.06, "$C{=}16$，$B_u{=}30$", transform=ax.transAxes, ha="right",
        fontsize=6.0, color="0.45")
ax.set_title("(c) $\\partial g_2^*/\\partial r_c>0$", fontsize=8.0, pad=3)

for ax in axes:
    ax.grid(alpha=0.2, lw=0.45)
    for s in ax.spines.values():
        s.set_linewidth(0.8)
    ax.tick_params(labelsize=6.8, direction="in")
    ax.margins(x=0.02)
axes[0].set_ylim(0, 30)
axes[1].set_ylim(13.5, 46)

fig.tight_layout(pad=0.6)
p = os.path.join(OUT, "fig05_g2star.png")
fig.savefig(p, dpi=300)
print("wrote", p)
print("gamma2_0 = %.1f ms" % GAMMA20)
for key, C, Bu, rc, p50, e, up, lab in MEAS:
    print("%-8s C=%-5g Bu=%-5g rc=%-4g  g2*=%.1f KB  measured T50=%.0f ms  cloud=%s"
          % (lab, C, Bu, rc, g2star(C, Bu, rc), p50, up))
