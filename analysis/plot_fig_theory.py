#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图 1（三层参考架构）与图 2（发现—执行二元开销分解 + 批到达修正）。

图 2 使用正文声明的解析参数（kappa/f_p 给出斜率，gamma 校准到
g1*=12 B、g2*=19 KB），并叠加修订 2a 的等效家庭代价 T1_eff(m=3)。
"""
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"
os.makedirs(OUT, exist_ok=True)

plt.rcParams["font.family"] = ["SimSun"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"


# =====================================================================
# 图 1：三层架构
# =====================================================================
def box(ax, x, y, w, h, text, fc="white", ec="0.25", fs=7.6, lw=0.9, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.004,rounding_size=0.012",
                                facecolor=fc, edgecolor=ec, linewidth=lw,
                                linestyle=ls, zorder=3))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                zorder=4, linespacing=1.55)


def arrow(ax, p, q, color="0.2", style="-|>", ls="-", rad=0.0, lw=0.9, ms=7):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=ms,
                                 linewidth=lw, color=color, linestyle=ls,
                                 connectionstyle="arc3,rad=%.2f" % rad,
                                 shrinkA=1.5, shrinkB=1.5, zorder=2))


fig, ax = plt.subplots(figsize=(7.2, 3.55))
ax.set_xlim(0, 1)
ax.set_ylim(0.18, 1.0)
ax.axis("off")

# ---------- 云 ----------
box(ax, 0.30, 0.865, 0.40, 0.115,
    "云执行宿主  $f_2=5\\times10^{4}$ GFLOP/s\n无状态：每次调用重传上下文 $C$",
    fc="#f2f2f2", fs=7.3)
ax.text(0.715, 0.922, "$\\gamma_2=\\gamma_2^{0}+\\frac{C}{B_u}+r_c$", fontsize=7.3,
        ha="left", va="center", color="0.15")

# ---------- WAN ----------
arrow(ax, (0.545, 0.865), (0.545, 0.745), style="<|-|>", lw=1.0)
ax.text(0.560, 0.815, "WAN：上行 $B_u$=30 Mbps，$r_c$=30 ms", fontsize=6.9,
        ha="left", va="center", color="0.15")
ax.text(0.560, 0.778, "上行受限（$B_u\\ll B_d$）", fontsize=6.3, ha="left",
        va="center", color="0.45")

# ---------- 家庭算力主机 ----------
box(ax, 0.055, 0.585, 0.345, 0.145, "", fc="white", ec="0.15", lw=1.1)
ax.text(0.2275, 0.696, "家庭算力主机  $f_1=2\\times10^{3}$ GFLOP/s", fontsize=7.3,
        ha="center", va="center")
for x, t in [(0.072, "编排器\n放置判据"), (0.176, "能力目录\n（常驻）"),
             (0.280, "执行宿主\n$f_1$")]:
    ax.add_patch(Rectangle((x, 0.600), 0.092, 0.068, facecolor="#f7f7f7",
                           edgecolor="0.35", lw=0.7, zorder=4))
    ax.text(x + 0.046, 0.634, t, ha="center", va="center", fontsize=6.5, zorder=5,
            linespacing=1.4)
ax.text(0.055, 0.572, "$\\gamma_1$：不含 $C$ 项（上下文常驻）", fontsize=6.4,
        ha="left", va="top", color="0.25")

# ---------- 网关 ----------
box(ax, 0.475, 0.600, 0.140, 0.115, "家庭网关\nAP 桥接", fc="#f2f2f2", fs=7.1)
arrow(ax, (0.400, 0.658), (0.475, 0.658), style="<|-|>", lw=1.1)
ax.text(0.4375, 0.640, "家庭总线\nCSMA", fontsize=5.9, ha="center", va="top",
        color="0.35", linespacing=1.45)

# ---------- 无线带 ----------
ax.add_patch(FancyBboxPatch((0.10, 0.452), 0.80, 0.070,
                            boxstyle="round,pad=0.003,rounding_size=0.01",
                            facecolor="#fbfbfb", edgecolor="0.6", lw=0.6,
                            linestyle=(0, (3, 2)), zorder=1))
ax.text(0.50, 0.487, "802.11n 5 GHz　·　多播发现帧按基本速率发送（不做速率自适应）",
        ha="center", va="center", fontsize=6.7, color="0.3", zorder=2)

# ---------- 终端 ----------
for i in range(4):
    x = 0.075 + i * 0.215
    box(ax, x, 0.245, 0.175, 0.125,
        "终端智能体 %s\n$f_0=100$ GFLOP/s\n$\\gamma_0\\leq\\gamma_1$"
        % ("$i$" if i == 3 else str(i + 1)), fc="white", fs=6.7)
    arrow(ax, (x + 0.0875, 0.370), (x + 0.0875, 0.452), style="<|-|>", color="0.45",
          lw=0.7, ls=(0, (2, 1.6)), ms=5)
ax.text(0.912, 0.300, "$\\vdots$\n共 $N$ 台", fontsize=7.2, ha="center", va="center",
        color="0.35", linespacing=1.5)

# ---------- 两个开销项 ----------
arrow(ax, (0.545, 0.600), (0.545, 0.522), color="0.15", lw=1.0)
ax.text(0.558, 0.560, "① 多播发现 $D(N)$", fontsize=6.8, ha="left", va="center",
        color="0.15")
ax.text(0.558, 0.532, "空口竞争，$N$ 依赖", fontsize=6.2, ha="left", va="center",
        color="0.45")

arrow(ax, (0.330, 0.370), (0.245, 0.585), color="0.15", rad=-0.25, style="<|-|>",
      lw=1.0)
ax.text(0.352, 0.430, "② 子任务执行", fontsize=6.8, ha="left", va="center", color="0.15")
ax.text(0.352, 0.402, "（数据经空中接口）", fontsize=6.2, ha="left",
        va="center", color="0.45")

# ---------- 左上说明 ----------
ax.text(0.012, 0.995, "① 发现开销：$N$ 依赖的独立代价项", fontsize=7.0, ha="left",
        va="top", color="0.2")
ax.text(0.012, 0.952, "② 执行开销：$g$ 依赖的三层仿射代价", fontsize=7.0, ha="left",
        va="top", color="0.2")

fig.tight_layout(pad=0.25)
p1 = os.path.join(OUT, "fig01_arch.png")
fig.savefig(p1, dpi=300, bbox_inches="tight")
plt.close(fig)
print("wrote", p1)


# =====================================================================
# 图 2：开销分解与门限
# =====================================================================
KAPPA = 0.0043          # GFLOP/B
F = (100.0, 2000.0, 50000.0)
A = [KAPPA / f * 1e3 * 1024 for f in F]      # ms / KB
G1 = 12.0 / 1024.0       # KB，解析门限 g1*
G2 = 19.0                # KB
GAMMA0 = 1.0             # ms
GAMMA1 = GAMMA0 + G1 * (A[0] - A[1])
GAMMA2 = GAMMA1 + G2 * (A[1] - A[2])

g = np.logspace(np.log10(0.02), np.log10(200), 600)
T0 = A[0] * g + GAMMA0
T1 = A[1] * g + GAMMA1
T2 = A[2] * g + GAMMA2
T1e = (3 + 1) / 2.0 * A[1] * g + GAMMA1        # m=3 的等效家庭代价
G2E = (GAMMA2 - GAMMA1) / ((3 + 1) / 2.0 * A[1] - A[2])

env = np.minimum(np.minimum(T0, T1), T2)

fig, ax = plt.subplots(figsize=(7.2, 3.5))
ax.plot(g, T0, color="0.15", lw=1.1, ls="-", label="$T_0$ 端：$a_0g+\\gamma_0$")
ax.plot(g, T1, color="0.35", lw=1.1, ls="--", label="$T_1$ 家庭主机：$a_1g+\\gamma_1$")
ax.plot(g, T1e, color="0.35", lw=1.1, ls=":", label="$T_1^{\\rm eff}$（$m{=}3$ 排队）")
ax.plot(g, T2, color="0.55", lw=1.1, ls="-.",
        label="$T_2$ 云：$a_2g+\\gamma_2^0+C/B_u+r_c$")
ax.plot(g, env, color="0.85", lw=4.0, alpha=0.55, zorder=0, solid_capstyle="round")

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(0.02, 200)
ax.set_ylim(0.5, 3000)
ax.set_xticks([0.1, 1, 10, 100])
ax.set_xticklabels(["0.1", "1", "10", "100"])
ax.minorticks_off()
ax.set_xlabel("子任务粒度 $g$ / KB")
ax.set_ylabel("单子任务时延 $T_p(g)$ / ms")
ax.grid(alpha=0.2, lw=0.45)

for x, lab, col in [(G1, "$g_1^*$=12 B", "0.15"), (G2E, "$g_2^{*\\rm eff}$=8.6 KB", "0.35"),
                    (G2, "$g_2^*$=19 KB", "0.55")]:
    ax.axvline(x, color=col, lw=0.9, ls=(0, (4, 2)))
    ax.text(x * 1.06, 700, lab, fontsize=7.0, color=col, rotation=90, va="top")

ax.annotate("", xy=(G2, 34), xytext=(G2E, 34),
            arrowprops=dict(arrowstyle="<|-|>", lw=0.8, color="0.25"))
ax.text((G2 + G2E) / 2, 58, "修订 2a：$g_2^*$ 左移", fontsize=6.8, ha="center",
        va="bottom", color="0.2")

ax.text(0.045, 5.0, "端", fontsize=7.6, color="0.25")
ax.text(1.35, 13, "家庭主机", fontsize=7.6, color="0.25")
ax.text(52, 5.4, "云", fontsize=7.6, color="0.45")

ax.legend(fontsize=6.6, frameon=False, loc="upper left", handlelength=2.2)
for s in ax.spines.values():
    s.set_linewidth(0.8)
ax.tick_params(labelsize=7.2, direction="in")
fig.tight_layout(pad=0.5)
p2 = os.path.join(OUT, "fig02_overhead.png")
fig.savefig(p2, dpi=300)
plt.close(fig)
print("wrote", p2)
print("a=%s ms/KB  gamma=%s  g2*eff=%.2f KB" % (["%.3f" % x for x in A],
                                                ["%.1f" % x for x in (GAMMA0, GAMMA1, GAMMA2)],
                                                G2E))
