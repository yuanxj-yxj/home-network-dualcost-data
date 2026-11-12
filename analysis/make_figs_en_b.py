#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""English figures part B: fig09_mix, fig10_thread_disc, fig1_discovery_law,
fig2_threshold_band.  PNG -> paper/figs_en/ ; TIF(300dpi LZW) -> paper/figs/.
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


# ---------------------------------------------------------------- fig09
def fig09():
    from csvfix import read_rows
    BASE = r"D:/工作区/ns3_work/runs/agentsim/e6mix"
    HDR = 512

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
            g = float(r["g"])
            ctx = float(r["ctxKB"]) * 1024.0
        except (KeyError, ValueError):
            return None
        if p50 <= 0 or sent <= 0:
            return None
        per_cloud = g + ctx + HDR
        frac = up / (sent * per_cloud) if per_cloud > 0 else 0.0
        return dict(p50=p50, succ=done / sent, up=up, frac=frac)

    rec = {}
    for f in glob.glob(os.path.join(BASE, "x_e6_g*_s*.csv")):
        m = re.match(r"x_e6_g(\d+)_(\w+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        g, pol = int(m.group(1)) / 1024.0, m.group(2)
        d = load(f)
        if d:
            rec.setdefault((g, pol), []).append(d)
    out = {}
    for (g, pol), ds in sorted(rec.items()):
        out[(g, pol)] = dict(p50=st.median([d["p50"] for d in ds]),
                             succ=st.mean([d["succ"] for d in ds]),
                             frac=st.median([d["frac"] for d in ds]))

    gs = sorted({k[0] for k in out})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.75))
    STYLE = {"ours": ("0.10", "o", "-", "ours (per-point)"),
             "mix": ("0.35", "D", "-", "intra-batch greedy $O(m\\log m)$"),
             "oracle": ("0.55", "s", "--", "ORACLE ($3^m$ search)"),
             "allcloud": ("0.75", "^", ":", "all-cloud")}
    for pol in ("ours", "mix", "oracle", "allcloud"):
        pts = [(g, out[(g, pol)]["p50"]) for g in gs if (g, pol) in out]
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax1.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, ls=ls,
                 ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    ax1.annotate("criterion ignores intra-batch\nqueueing: $+68\\%$ (16 KB)", xy=(16, 74),
                 xytext=(1.2, 60), fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax1.annotate("mixing recovers\n$\\approx-38\\%$", xy=(16, 46), xytext=(30, 34),
                 fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax1.set_xscale("log", base=2)
    ax1.set_xticks(gs)
    ax1.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax1.minorticks_off()
    ax1.set_xlabel("Subtask granularity $g$ / KB")
    ax1.set_ylabel("Task completion delay P50 / ms")
    ax1.grid(alpha=0.22, lw=0.5)
    ax1.legend(fontsize=6.2, frameon=False, loc="upper left")
    ax1.tick_params(labelsize=7, direction="in")
    ax1.set_title("(a) Completion delay", fontsize=8)

    for pol in ("ours", "mix", "oracle"):
        pts = [(g, out[(g, pol)]["frac"] * 100) for g in gs if (g, pol) in out]
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax2.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, ls=ls,
                 ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    ax2.axhline(100, color="0.75", lw=0.6, ls=":")
    ax2.annotate("greedy matches exhaustive\nassignment exactly", xy=(16, 33.3),
                 xytext=(1.4, 62), fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax2.set_xscale("log", base=2)
    ax2.set_xticks(gs)
    ax2.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax2.minorticks_off()
    ax2.set_xlabel("Subtask granularity $g$ / KB")
    ax2.set_ylabel("Cloud-executed subtask share / %")
    ax2.set_ylim(-4, 108)
    ax2.grid(alpha=0.22, lw=0.5)
    ax2.legend(fontsize=6.2, frameon=False, loc="center right")
    ax2.tick_params(labelsize=7, direction="in")
    ax2.set_title("(b) Placement structure", fontsize=8)
    fig.tight_layout()
    save(fig, "fig09_mix.png")


# ---------------------------------------------------------------- fig10
def fig10():
    D = r"D:\工作区\ns3_work\runs\thread\disc"
    NQUERIES = 60
    pat = re.compile(r"x_td_N(\d+)_be(\d)_s(\d+)\.csv")
    Ns, P50, P95, SUCC = [], [], [], []
    for f in sorted(glob.glob(os.path.join(D, "x_td_N*_be0_s*.csv"))):
        m = pat.search(f)
        if not m:
            continue
        N = int(m.group(1))
        data = np.loadtxt(f, delimiter=",", skiprows=1, usecols=(3,))
        data = data[data > 0]
        if N not in Ns:
            Ns.append(N)
            P50.append([]); P95.append([]); SUCC.append([])
        idx = Ns.index(N)
        P50[idx].append(np.percentile(data, 50))
        P95[idx].append(np.percentile(data, 95))
        SUCC[idx].append(min(100.0, len(data) / (N * NQUERIES) * 100.0))
    Ns = np.array(Ns)
    _order = np.argsort(Ns)
    Ns = Ns[_order]
    P50 = np.array([np.mean(x) for x in P50])[_order]
    P95 = np.array([np.mean(x) for x in P95])[_order]
    SUCC = np.array([np.mean(x) for x in SUCC])[_order]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.0))
    ax1.plot(Ns, P50, "o-", color="black", ms=3.6, lw=1.1, label="P50")
    ax1.plot(Ns, P95, "s--", color="black", ms=3.6, lw=1.1, label="P95")
    ax1.set_xlabel("Number of devices $N$ (Thread leaf)")
    ax1.set_ylabel("Discovery delay (ms)")
    ax1.set_title("(a) Thread discovery delay vs $N$", fontsize=8.5, pad=4)
    ax1.legend(loc="upper left", frameon=False, fontsize=6.6)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(labelsize=7.2, direction="in")

    ax2.plot(Ns, SUCC, "^-", color="black", ms=3.6, lw=1.1)
    ax2.set_xlabel("Number of devices $N$ (Thread leaf)")
    ax2.set_ylabel("Discovery success rate (%)")
    ax2.set_title("(b) Thread discovery success rate vs $N$", fontsize=8.5, pad=4)
    ax2.set_ylim(0, 105)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(labelsize=7.2, direction="in")
    for ax in (ax1, ax2):
        for s in ax.spines.values():
            s.set_linewidth(0.8)
    fig.tight_layout(pad=0.6)
    save(fig, "fig10_thread_disc.png")


# ---------------------------------------------------------------- fig1 (paper Fig.3)
def fig01():
    BASE = r"D:\工作区\ns3_work\runs\agentsim"
    OUTDIR = OUT_PNG
    HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,"
            "wanUpBytes,wanDnBytes,payloadBytes,lambda,airtimeS,taskFailed,rounds,"
            "missingResp,discP50,discP95,discP50us,discP95us,txBusyS,retxTotal,"
            "rspTxTotal,rspPhyTxTotal,wanUpRealB,wanDnRealB").split(",")
    COL = {h: i for i, h in enumerate(HEAD)}
    CENSOR_US = 360000.0

    def load(sub, prefix):
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
            if len(r) < 26:
                continue
            rounds = max(int(r[COL["rounds"]]), 1)
            nn = int(r[COL["N"]])
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

    pin = load("e1_v3/pin", "pin")
    beb = load("e1_v3/beb", "sweepW0")
    NS = sorted(set(pin) & set(beb))
    print("N points:", NS)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.0))
    for dat, lab, color, mk, ls in ((beb, "BEB adaptive", "0.20", "o", "-"),
                                    (pin, "pinned $CW_{\\min}$ (BEB off)", "0.55", "s", "--")):
        xs, ys, es = [], [], []
        for n in NS:
            m, e = stat([d for d, _, _ in dat[n]])
            xs.append(n)
            ys.append(m / 1000.0)
            es.append(e / 1000.0)
        ax1.errorbar(xs, ys, yerr=es, color=color, marker=mk, ls=ls, ms=4.2,
                     lw=1.2, capsize=2.0, elinewidth=0.8,
                     mfc="white" if mk == "s" else color, label=lab, zorder=3)
    if 112 in pin:
        ax1.scatter([112] * len(pin[112]), [d / 1000.0 for d, _, _ in pin[112]],
                    marker="x", s=16, color="0.35", lw=0.8, zorder=4,
                    label="pinned, $N{=}$112 per-seed")
    ax1.plot([128], [CENSOR_US / 1000.0], marker="s", ms=5.5, mfc="white",
             mec="0.55", mew=1.0, ls="none", zorder=5)
    ax1.annotate("$\\geq$360 (censored)", xy=(128, 360), xytext=(26, 300),
                 fontsize=7.5, color="0.35",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.45"))
    ax1.axvspan(96, 128, color="0.88", alpha=0.55, lw=0, zorder=1)
    ax1.text(108, 0.62, "$N^*$ critical band", fontsize=7.5, color="0.30", ha="center")
    ax1.set_xscale("log", base=2)
    ax1.set_yscale("log")
    ax1.set_xticks(NS)
    ax1.set_xticklabels([str(n) for n in NS], fontsize=6.2, rotation=45)
    ax1.minorticks_off()
    ax1.set_xlim(1.7, 170)
    ax1.set_ylim(0.5, 500)
    ax1.set_xlabel("Number of devices $N$")
    ax1.set_ylabel("Median discovery latency $D_{50}$ / ms")
    ax1.grid(alpha=0.22, lw=0.5, which="major")
    ax1.tick_params(labelsize=7.5, direction="in")
    ax1.legend(fontsize=6.6, frameon=False, loc="upper left")
    ax1.set_title("(a) Two-regime discovery latency vs density", fontsize=8.5, pad=4)

    for dat, lab, color, mk, ls in ((beb, "BEB adaptive", "0.20", "o", "-"),
                                    (pin, "pinned $CW_{\\min}$ (BEB off)", "0.55", "s", "--")):
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
    ax2.set_xlabel("Number of devices $N$")
    ax2.set_ylabel("Discovery-phase airtime occupancy $D_{\\mathrm{air}}$ / s")
    ax2.grid(alpha=0.22, lw=0.5)
    ax2.tick_params(labelsize=7.5, direction="in")
    ax2.legend(fontsize=6.6, frameon=False, loc="upper left")
    ax2.set_title("(b) Discovery carrying cost: airtime occupancy", fontsize=8.5, pad=4)
    for ax in (ax1, ax2):
        for s in ax.spines.values():
            s.set_linewidth(0.8)
    fig.tight_layout(pad=0.6)
    save(fig, "fig1_discovery_law.png")


# ---------------------------------------------------------------- fig2 (paper Fig.4)
def fig02():
    BASE = r"D:\工作区\ns3_work\runs\agentsim\e2v3"
    HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
            "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
            "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
            "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
    COL = {h: i for i, h in enumerate(HEAD)}
    A, B = {}, {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        b = os.path.basename(f)
        r = read_last(f)
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
    STYLE = {"ours": ("0.10", "o", "-", "ours (criterion)"),
             "allcloud": ("0.40", "s", "--", "all-cloud"),
             "alllocal": ("0.62", "^", "-.", "all-local"),
             "static": ("0.80", "D", ":", r"static $\theta{=}$8 KB")}
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
            xs.append(g / 1024.0)
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
    ax1.set_xlabel("Subtask granularity $g$ / KB")
    ax1.set_ylabel("Median task completion delay $T_{50}$ / ms")
    ax1.axvline(12 / 1024.0, color="0.55", ls=":", lw=0.9)
    ax1.axvline(19.0, color="0.55", ls=":", lw=0.9)
    ax1.annotate("$g_1^*$", xy=(12 / 1024.0, 0.9), fontsize=7, color="0.45")
    ax1.annotate("$g_2^*$", xy=(21, 0.9), fontsize=7, color="0.45")
    ax1.grid(alpha=0.22, lw=0.5)
    ax1.tick_params(labelsize=7.2, direction="in")
    ax1.legend(fontsize=6.4, frameon=False, loc="upper left")
    ax1.set_title("(a) Delay--granularity and threshold band", fontsize=8.5, pad=4)

    ORDER = [("base", "base"), ("rtt10", "$r_c$=10"), ("rtt60", "$r_c$=60"),
             ("bu10", "$B_u$=10"), ("bu100", "$B_u$=100"),
             ("c4", "$C$=4"), ("c64", "$C$=64"), ("m1", "$m$=1"), ("m5", "$m$=5")]
    rows = []
    for key, lab in ORDER:
        rec = A.get(("ours", 16384)) if key == "base" else B.get((key, 16384))
        if not rec:
            continue
        p50, e = stat([x[0] for x in rec])
        up = sum(1 for x in rec if x[2] > 0) / len(rec)
        rows.append((lab, p50, e, up))
    xs = range(len(rows))
    for i, (lab, v, e, up) in enumerate(rows):
        ax2.bar(i, v, width=0.66, color="0.72" if up > 0.5 else "0.90",
                edgecolor="0.25", linewidth=0.7, hatch="//" if up > 0.5 else None,
                zorder=3)
        ax2.errorbar(i, v, yerr=e, color="0.2", lw=0.8, capsize=1.8, zorder=4)
        ax2.text(i, v + 4, "%.0f" % v, ha="center", fontsize=6.6, color="0.15")
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([r[0] for r in rows], fontsize=6.6, rotation=35)
    ax2.set_ylabel("$T_{50}$ / ms ($g{=}$16 KB)")
    ax2.set_xlabel("Parameter perturbation (hatched = placed at cloud)")
    ax2.grid(axis="y", alpha=0.22, lw=0.5)
    ax2.tick_params(labelsize=7.2, direction="in")
    ax2.set_title("(b) Comparative statics of the threshold", fontsize=8.5, pad=4)
    for ax in (ax1, ax2):
        for s in ax.spines.values():
            s.set_linewidth(0.8)
    fig.tight_layout(pad=0.6)
    save(fig, "fig2_threshold_band.png")
    for lab, v, e, up in rows:
        print("%-10s T50=%.1f ms  cloudFrac=%.1f" % (lab, v, up))


if __name__ == "__main__":
    fig09()
    fig10()
    fig01()
    fig02()
