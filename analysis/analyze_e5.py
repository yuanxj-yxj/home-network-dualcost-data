#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E5：ORACLE（3^m 穷举）上界 vs 本文判据 vs 全云

oracle 按批 makespan 最优指派（忽略通信与并发细节，纯解析）；ours 逐点按门限
放置。二者之差即"批内协同放置"的可回收增益，用于回答"本文判据离最优多远"。
"""
import glob
import os
import re
import statistics as st

from csvfix import read_rows

BASE = os.environ.get("NS3DATA", r"D:/工作区/ns3_work/runs/agentsim/e5v3")


def load(path):
    rows = read_rows(path)
    if not rows:
        return None
    r = rows[-1]
    try:
        p50 = float(r["p50"])
        sent = float(r["taskSent"])
        done = float(r["taskDone"])
        up = float(r["wanUpBytes"])
    except (KeyError, ValueError):
        return None
    if p50 <= 0 or sent <= 0:
        return None
    return p50, done / sent, up


def main():
    rec = {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        b = os.path.basename(f)
        m = re.match(r"x_e5_g(\d+)_(\w+)_s(\d+)\.csv$", b)
        if not m:
            continue
        g, pol = int(m.group(1)) / 1024.0, m.group(2)
        d = load(f)
        if d:
            rec.setdefault((g, pol), []).append(d)

    print(f"{'g/KB':>6s} {'policy':9s} {'P50':>8s} {'succ':>6s} {'agentUp/MB':>11s} {'n':>3s}")
    out = {}
    for (g, pol), ds in sorted(rec.items()):
        p50 = st.median([d[0] for d in ds])
        succ = st.mean([d[1] for d in ds])
        up = st.mean([d[2] for d in ds]) / 1e6
        print(f"{g:6.0f} {pol:9s} {p50:8.1f} {succ:6.3f} {up:11.2f} {len(ds):3d}")
        out[(g, pol)] = (p50, succ, up, [d[0] for d in ds])

    print("\n=== 相对 ORACLE 的间隙 ===")
    print(f"{'g/KB':>6s} {'ours':>8s} {'oracle':>8s} {'gap':>8s} {'gap%':>7s} {'allcloud':>9s}")
    for g in sorted({k[0] for k in out}):
        o = out.get((g, "ours"))
        r = out.get((g, "oracle"))
        c = out.get((g, "allcloud"))
        if not (o and r):
            continue
        gap = o[0] - r[0]
        print(f"{g:6.0f} {o[0]:8.1f} {r[0]:8.1f} {gap:+8.1f} "
              f"{gap / r[0] * 100:+7.1f} {(c[0] if c else float('nan')):9.1f}")

    # m=5 组
    print("\n=== m=5（组合空间 3^5=243）===")
    for pol in ("ours", "oracle"):
        ds = []
        for f in glob.glob(os.path.join(BASE, "x_e5_m5_%s_s*.csv" % pol)):
            d = load(f)
            if d:
                ds.append(d)
        if ds:
            print(f"  {pol:8s}: P50={st.median([d[0] for d in ds]):.1f} ms, "
                  f"succ={st.mean([d[1] for d in ds]):.3f}, n={len(ds)}")
    return [dict(g=g, pol=pol, p50=v[0], succ=v[1]) for (g, pol), v in out.items()]


def plot(rows):
    """图 8：ours / oracle / 全云 的 P50 随粒度变化 + m=5 对照"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["SimSun"]
    plt.rcParams["font.size"] = 9
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "stix"
    OUT = r"D://工作区//家庭网络智能体协同承载边界论文//figs"
    os.makedirs(OUT, exist_ok=True)

    fig, ax = plt.subplots(figsize=(3.5, 2.75))
    STYLE = {"ours": ("0.10", "o", "-", "本文判据"),
             "oracle": ("0.45", "s", "--", "ORACLE（$3^m$ 穷举）"),
             "allcloud": ("0.70", "^", ":", "全云")}
    gs = sorted({r["g"] for r in rows})
    for pol in ("ours", "oracle", "allcloud"):
        pts = [r for r in rows if r["pol"] == pol]
        pts.sort(key=lambda r: r["g"])
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax.plot([r["g"] for r in pts], [r["p50"] for r in pts], color=col, marker=mk,
                ls=ls, ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    # 标注两个方向：判据落后（中粒度）与判据反超（解析上界不含排队）
    ax.annotate("批内混排可回收\n$-41\\%$（16 KB）", xy=(16, 74), xytext=(1.6, 92),
                fontsize=6.4, color="0.15",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax.annotate("解析上界不含 WAN 批内排队：\n判据反超 $5\\%$（8 KB）", xy=(8, 37), xytext=(20, 30),
                fontsize=6.4, color="0.15",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(gs)
    ax.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax.minorticks_off()
    ax.set_xlabel("子任务粒度 $g$ / KB")
    ax.set_ylabel("任务完成时延 P50 / ms")
    ax.grid(alpha=0.22, lw=0.5)
    ax.legend(fontsize=6.4, frameon=False, loc="upper left")
    ax.tick_params(labelsize=7, direction="in")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig08_oracle.png"), dpi=300)
    print("wrote", os.path.join(OUT, "fig08_oracle.png"))


if __name__ == "__main__":
    rs = main()
    if rs:
        plot(rs)
