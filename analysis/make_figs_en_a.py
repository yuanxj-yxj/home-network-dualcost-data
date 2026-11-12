#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""English figures part A: fig05_g2star, fig06_lambda, fig07_mixed, fig08_oracle.

PNG -> paper/figs_en/ ; TIF(300dpi LZW) -> paper/figs/ (overwrite CN set).
"""
import glob
import math
import os
import re
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

PAPER = r"D:\工作区\家庭网络智能体协同承载边界论文"
OUT_PNG = os.path.join(PAPER, "figs_en")
OUT_TIF = os.path.join(PAPER, "figs")
os.makedirs(OUT_PNG, exist_ok=True)

plt.rcParams["font.family"] = ["Times New Roman"]
plt.rcParams["font.size"] = 9
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "stix"

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


def stat(v):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, 0.0
    s = sum((x - m) ** 2 for x in v) / (n - 1)
    return m, T95.get(n, 2.571) * math.sqrt(s / n)


def save(fig, name):
    p = os.path.join(OUT_PNG, name)
    fig.savefig(p, dpi=300)
    t = os.path.join(OUT_TIF, os.path.splitext(name)[0] + ".tif")
    Image.open(p).save(t, compression="tiff_lzw", dpi=(300, 300))
    print("wrote", p, "and", t)
    plt.close(fig)


def read_last(f):
    lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
    if lines and lines[0].split(",")[0] == "seed":
        lines = lines[1:]
    return lines[-1].split(",") if lines else None


# ---------------------------------------------------------------- fig05
def fig05():
    BASE = r"D:\工作区\ns3_work\runs\agentsim\e2v3"
    A1, A2 = 2.202, 0.088
    GAMMA1 = 5.0
    C0, BU0, RC0 = 16.0, 30.0, 30.0
    G2_BASE = 19.0
    GAMMA20 = G2_BASE * (A1 - A2) + GAMMA1 - 8 * C0 / BU0 - RC0

    def g2star(C=16.0, Bu=30.0, rc=30.0):
        gam2 = GAMMA20 + 8.0 * C / Bu + rc
        return (gam2 - GAMMA1) / (A1 - A2)

    A, B = {}, {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        b = os.path.basename(f)
        r = read_last(f)
        if r is None or len(r) <= 30:
            continue
        rec = (float(r[10]), float(r[11]), int(r[28]))
        m = re.match(r"(?:e2f_)?A_g(\d+)_(\w+)_s(\d+)\.csv$", b)
        if m:
            A.setdefault((m.group(2), int(m.group(1))), []).append(rec)
            continue
        m = re.match(r"(?:e2f_)?B_([a-z0-9]+)_g(\d+)_s(\d+)\.csv$", b)
        if m:
            B.setdefault((m.group(1), int(m.group(2))), []).append(rec)

    ORDER = [("base", None, None, None, "base"),
             ("c4", "C", 4.0, None, "$C$=4"),
             ("c64", "C", 64.0, None, "$C$=64"),
             ("bu10", "B_u", None, None, "$B_u$=10"),
             ("bu100", "B_u", None, None, "$B_u$=100"),
             ("rtt10", "r_c", None, 10.0, "$r_c$=10"),
             ("rtt60", "r_c", None, 60.0, "$r_c$=60")]
    MEAS = []
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

    ax = axes[0]
    cs = np.linspace(0, 128, 200)
    ax.plot(cs, [g2star(C=c) for c in cs], color="0.15", lw=1.2)
    ax.set_xlabel("Context $C$ / KB")
    ax.set_ylabel("$g_2^*$ / KB")
    for key, C, Bu, rc, p50, e, up, lab in MEAS:
        if not lab.startswith("$C$") and lab != "base":
            continue
        g2v = g2star(C=C, Bu=Bu, rc=rc)
        ax.errorbar(C, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                    capsize=1.5, zorder=4)
        if key == "c4":
            continue
        dest = "$\\to$cloud" if up else "$\\to$home"
        ax.annotate(("%d ms " % p50) + dest, xy=(C, g2v),
                    xytext=(C + 4, g2v + (2.5 if key == "base" else 1.5)),
                    fontsize=5.8, color="0.25")
    ax.text(0.97, 0.06, "$B_u{=}30$, $r_c{=}30$", transform=ax.transAxes, ha="right",
            fontsize=6.0, color="0.45")
    ax.set_title("(a) $\\partial g_2^*/\\partial C>0$", fontsize=8.0, pad=3)

    ax = axes[1]
    bus = np.linspace(5, 120, 200)
    ax.plot(bus, [g2star(Bu=b) for b in bus], color="0.15", lw=1.2)
    ax.set_xlabel("Uplink bandwidth $B_u$ / Mbps")
    for key, C, Bu, rc, p50, e, up, lab in MEAS:
        if not lab.startswith("$B_u$"):
            continue
        g2v = g2star(C=C, Bu=Bu, rc=rc)
        ax.errorbar(Bu, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                    capsize=1.5, zorder=4)
        dest = "$\\to$cloud" if up else "$\\to$home"
        dx, dy = (-46, -2.8) if Bu > 50 else (4, -4.0)
        ax.annotate(("%d ms " % p50) + dest, xy=(Bu, g2v),
                    xytext=(Bu + dx, g2v + dy), fontsize=5.8, color="0.25")
    ax.text(0.97, 0.90, "$C{=}16$, $r_c{=}30$", transform=ax.transAxes, ha="right",
            fontsize=6.0, color="0.45")
    ax.set_title("(b) $\\partial g_2^*/\\partial B_u<0$", fontsize=8.0, pad=3)

    ax = axes[2]
    rcs = np.linspace(5, 90, 200)
    ax.plot(rcs, [g2star(rc=r) for r in rcs], color="0.15", lw=1.2)
    ax.set_xlabel("Cloud-side RTT $r_c$ / ms")
    for key, C, Bu, rc, p50, e, up, lab in MEAS:
        if not lab.startswith("$r_c$"):
            continue
        g2v = g2star(C=C, Bu=Bu, rc=rc)
        ax.errorbar(rc, g2v, color="0.15", marker="o", ms=3.5, mfc="white", lw=0.8,
                    capsize=1.5, zorder=4)
        dest = "$\\to$cloud" if up else "$\\to$home"
        ax.annotate(("%d ms " % p50) + dest, xy=(rc, g2v),
                    xytext=(rc + 3, g2v + 1.2), fontsize=5.8, color="0.25")
    ax.text(0.97, 0.06, "$C{=}16$, $B_u{=}30$", transform=ax.transAxes, ha="right",
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
    save(fig, "fig05_g2star.png")


# ---------------------------------------------------------------- fig06
def fig06():
    BASE = r"D:\工作区\ns3_work\runs\agentsim\e3v3"
    M, G_KB, RHO, ROUNDS = 3, 64.0, 0.5, 150
    HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
            "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
            "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
            "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
    COL = {h: i for i, h in enumerate(HEAD)}
    D = {}
    for f in glob.glob(os.path.join(BASE, "*e3_C*_p*_*.csv")):
        m = re.match(r"(?:x_)?e3_C(\d+)_p(\d)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        r = read_last(f)
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
    RES = {}
    for key in sorted(D):
        C, psi, pol = key
        rec = D[key]
        lam_r, e_r = stat([x["up"] + x["dn"] for x in rec])
        lam_r /= M * G_KB * 1024.0
        e_r /= M * G_KB * 1024.0
        p50, e50 = stat([x["p50"] for x in rec])
        RES[key] = (lam_r, e_r, p50, e50)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.0))
    CS = sorted({c for (c, _, _) in RES})
    STYLE = {("ours", 0): ("0.10", "o", "-", "ours, $\\psi{=}0$"),
             ("ours", 1): ("0.10", "o", "--", "ours, cache $\\psi{=}1$"),
             ("allcloud", 0): ("0.55", "s", "-.", "all-cloud, $\\psi{=}0$"),
             ("allcloud", 1): ("0.55", "s", ":", "all-cloud, cache $\\psi{=}1$")}
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
    ax1.set_xlabel("Context size $C$ / KB")
    ax1.set_ylabel("Amplification $\\Lambda$ (WAN bytes per $mg$ payload)")
    ax1.grid(alpha=0.22, lw=0.5)
    ax1.legend(fontsize=6.3, frameon=False)
    ax1.tick_params(labelsize=7.0, direction="in")
    ax1.set_title("(a) $\\Lambda(C)$ and cache gain", fontsize=8.3, pad=4)

    cs_key = 64
    if (cs_key, 0, "allcloud") in RES and (cs_key, 1, "allcloud") in RES:
        l0 = RES[(cs_key, 0, "allcloud")][0]
        l1 = RES[(cs_key, 1, "allcloud")][0]
        base = ROUNDS * G_KB * (1 + RHO) / (M * G_KB)
        c0, c1 = l0 - base, l1 - base
        ax2.bar([0, 1], [c0, c1], width=0.5, color=["0.75", "0.45"],
                edgecolor="0.2", lw=0.7, zorder=3)
        for i, v in enumerate([c0, c1]):
            ax2.text(i, v + 1.5, "%.1f" % v, ha="center", fontsize=7.0)
        ax2.annotate("", xy=(1, c1 + 9), xytext=(0, c0 + 9),
                     arrowprops=dict(arrowstyle="<|-|>", lw=0.8, color="0.25"))
        ax2.text(0.5, c0 + 11, "$\\Theta(m)$: ratio %.1f (analytic $m{=}3$)" % (c0 / c1),
                 ha="center", fontsize=6.8, color="0.2")
        ax2.set_xticks([0, 1])
        ax2.set_xticklabels(["$\\psi{=}0$", "$\\psi{=}1$"], fontsize=7.5)
        ax2.set_xlim(-0.6, 1.6)
        ax2.set_ylim(0, c0 * 1.35)
        ax2.set_ylabel("Context term of $\\Lambda$ ($C{=}$64 KB, all-cloud)")
        ax2.grid(axis="y", alpha=0.22, lw=0.5)
        ax2.tick_params(labelsize=7.0, direction="in")
        ax2.set_title("(b) Cache gain $\\Theta(m)$", fontsize=8.3, pad=4)

    for ax in (ax1, ax2):
        for s in ax.spines.values():
            s.set_linewidth(0.8)
    fig.tight_layout(pad=0.6)
    save(fig, "fig06_lambda.png")


# ---------------------------------------------------------------- fig07
def fig07():
    BASE = r"D:\工作区\ns3_work\runs\agentsim\e4v3"
    HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
            "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
            "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
            "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
    COL = {h: i for i, h in enumerate(HEAD)}
    BG_UP = {"none": 0.0, "video": 0.5, "gaming": 6.0, "backup": 24.0}
    BG_LAB = {"none": "no bg", "video": "video\n(0.5 Mbps)",
              "gaming": "gaming\n(6 Mbps)", "backup": "backup\n(24 Mbps)"}
    POL_LAB = {"ours": "ours (criterion)", "allcloud": "all-cloud",
               "alllocal": "all-local", "static": "static $\\theta{=}$8 KB"}

    D = {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        m = re.match(r"(?:x_)?e4_(\w+?)_bu(\d+)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        r = read_last(f)
        if r is None or len(r) < 32:
            continue
        key = (m.group(1), int(m.group(2)), m.group(3))
        D.setdefault(key, []).append((float(r[COL["p50"]]), float(r[COL["p95"]]),
                                      int(r[COL["taskSent"]]), int(r[COL["taskDone"]])))
    R = {}
    for (bg, bu, pol), rec in sorted(D.items()):
        p50, e50 = stat([x[0] for x in rec])
        p95, _ = stat([x[1] for x in rec])
        succ = sum(x[3] for x in rec) / max(1, sum(x[2] for x in rec))
        R[(bg, bu, pol)] = (p50, e50, p95, succ)

    BGS = ["none", "video", "gaming", "backup"]
    POLS = ["ours", "allcloud", "static", "alllocal"]
    STYLE = {"ours": ("0.10", "o", "-"), "allcloud": ("0.45", "s", "--"),
             "static": ("0.65", "D", ":"), "alllocal": ("0.82", "^", "-.")}

    fig, axes = plt.subplots(1, 3, figsize=(7.4, 3.0))
    for ax, bu, title in zip(axes[:2], (30, 10),
                             ("(a) Abundant uplink, $B_u{=}$30 Mbps",
                              "(b) Weak uplink, $B_u{=}$10 Mbps")):
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
        ax.set_xticklabels([BG_LAB[b] for b in BGS], fontsize=6.2)
        ax.set_yscale("log")
        ax.set_ylabel("Task completion delay $T_{50}$ / ms")
        ax.grid(alpha=0.2, lw=0.45, which="both")
        ax.tick_params(labelsize=7.0, direction="in")
        ax.set_title(title, fontsize=8.2, pad=4)
        for i, bg in enumerate(BGS):
            for pol in ("allcloud", "static"):
                # only annotate meaningful losses (<98%); "succ 100%" rounding is noise
                if (bg, bu, pol) in R and R[(bg, bu, pol)][3] < 0.98:
                    v = R[(bg, bu, pol)][0]
                    dy = 1.45
                    ax.annotate("succ %.0f%%" % (100 * R[(bg, bu, pol)][3]),
                                xy=(i, v), xytext=(i + 0.12, v * dy), fontsize=5.6,
                                color="0.25")
    axes[0].legend(fontsize=5.8, frameon=False, ncol=2, loc="upper left",
                   columnspacing=0.9, handletextpad=0.4)

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
        # staggered label positions to avoid mutual overlap
        pos = {"backup": (be + 1.5, g2star(be) + 1.4),
               "gaming": (be - 10.0, g2star(be) + 3.8),
               "video": (be + 1.5, g2star(be) + 2.2)}
        ax.annotate(bg, xy=(be, g2star(be)), xytext=pos.get(bg, (be + 1.5, g2star(be) + 1.2)),
                    fontsize=6.2, color="0.25")
    ax.axhline(16, color="0.55", ls=(0, (3, 2)), lw=0.9)
    ax.text(3, 16.6, "$g{=}$16 KB (operating point)", fontsize=6.2, color="0.4",
            ha="left")
    ax.set_xlabel("Available uplink $B_u^{\\rm eff}$ / Mbps")
    ax.set_ylabel("Threshold $g_2^{*\\rm eff}$ / KB")
    ax.grid(alpha=0.2, lw=0.45)
    ax.tick_params(labelsize=7.0, direction="in")
    ax.set_title("(c) Threshold under background load", fontsize=8.2, pad=4)

    for ax in axes:
        for s in ax.spines.values():
            s.set_linewidth(0.8)
    fig.tight_layout(pad=0.6)
    save(fig, "fig07_mixed.png")


# ---------------------------------------------------------------- fig08
def fig08():
    from csvfix import read_rows
    BASE = r"D:/工作区/ns3_work/runs/agentsim/e5v3"

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

    rec = {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        m = re.match(r"x_e5_g(\d+)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        g, pol = int(m.group(1)) / 1024.0, m.group(2)
        d = load(f)
        if d:
            rec.setdefault((g, pol), []).append(d)
    out = {}
    for (g, pol), ds in sorted(rec.items()):
        p50 = st.median([d[0] for d in ds])
        out[(g, pol)] = (p50, st.mean([d[1] for d in ds]),
                         st.mean([d[2] for d in ds]) / 1e6, [d[0] for d in ds])

    fig, ax = plt.subplots(figsize=(3.5, 2.75))
    STYLE = {"ours": ("0.10", "o", "-", "ours (criterion)"),
             "oracle": ("0.45", "s", "--", "ORACLE ($3^m$ search)"),
             "allcloud": ("0.70", "^", ":", "all-cloud")}
    gs = sorted({r[0] for r in out})
    for pol in ("ours", "oracle", "allcloud"):
        pts = [(g, out[(g, pol)][0]) for g in gs if (g, pol) in out]
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk,
                ls=ls, ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    # annotations kept clear of the legend (upper left)
    ax.annotate("intra-batch mixing recovers $-41\\%$ (16 KB)", xy=(16, 74),
                xytext=(1.5, 77), fontsize=6.4, color="0.15",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax.annotate("analytic bound omits WAN\nintra-batch queueing:\nours beats it by 5% (8 KB)",
                xy=(8, 37), xytext=(19, 27), fontsize=6.4, color="0.15",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(gs)
    ax.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax.minorticks_off()
    ax.set_xlabel("Subtask granularity $g$ / KB")
    ax.set_ylabel("Task completion delay P50 / ms")
    ax.grid(alpha=0.22, lw=0.5)
    ax.legend(fontsize=6.4, frameon=False, loc="upper left")
    ax.tick_params(labelsize=7, direction="in")
    fig.tight_layout()
    save(fig, "fig08_oracle.png")


if __name__ == "__main__":
    fig05()
    fig06()
    fig07()
    fig08()
