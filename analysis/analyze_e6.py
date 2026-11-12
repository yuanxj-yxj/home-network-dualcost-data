#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E6：批内混排贪心（mix）vs 逐点判据（ours）vs ORACLE（3^m 穷举）vs 全云

回答四个问题：
  Q1 贪心指派是否复现 3^m 穷举指派——判据是上云份额（wanUpBytes 是编排器按最终
     执行位置计的确定性字节数，与分配逐位对应），逐 seed 比对；
  Q2 mix 把 ours→oracle 的间隙回收多少（P50 口径，与 e5v3 同参数可比）；
  Q3 收益的粒度区间（8 KB 处 ours 曾反超 oracle 5.1%，看 mix 是否同样回落）；
  Q4 异构批（lognormal）下贪心的排序是否带来额外收益。
"""
import glob
import os
import re
import statistics as st

from csvfix import read_rows

BASE = os.environ.get("NS3DATA", r"D:/工作区/ns3_work/runs/agentsim/e6mix")
HDR = 512  # h_hdr，与 agent-sim.cc 默认值一致


def load(path, ctx_bytes):
    rows = read_rows(path)
    if not rows:
        return None
    r = rows[-1]
    try:
        p50 = float(r["p50"])
        p95 = float(r["p95"])
        sent = float(r["taskSent"])
        done = float(r["taskDone"])
        up = float(r["wanUpBytes"])
        g = float(r["g"])
        m = float(r["m"])
        ctx = float(r["ctxKB"]) * 1024.0
    except (KeyError, ValueError):
        return None
    if p50 <= 0 or sent <= 0:
        return None
    per_cloud = g + ctx + HDR  # 单个上云子任务消耗的 WAN 上行字节（编排器口径）
    frac = up / (sent * per_cloud) if per_cloud > 0 else 0.0
    return dict(p50=p50, p95=p95, succ=done / sent, up=up, frac=frac, sent=sent)


def collect(pat, ctx_bytes):
    rec = {}
    for f in glob.glob(os.path.join(BASE, pat)):
        b = os.path.basename(f)
        m = re.match(pat.replace("*", "(\\w+)") + r"$", b)
        if not m:
            continue
        d = load(f, ctx_bytes)
        if d:
            d["file"] = b
            rec.setdefault(m.group(1), []).append(d)
    return rec


def agg(ds):
    return dict(p50=st.median([d["p50"] for d in ds]),
                p95=st.median([d["p95"] for d in ds]),
                succ=st.mean([d["succ"] for d in ds]),
                frac=st.median([d["frac"] for d in ds]),
                n=len(ds))


def main():
    print("=" * 78)
    print("E6 主组：g 扫描 × {ours, mix, oracle, allcloud} × 5 seeds（N=16 m=3 C=16KB）")
    print("=" * 78)
    rec = {}
    for f in glob.glob(os.path.join(BASE, "x_e6_g*_s*.csv")):
        b = os.path.basename(f)
        m = re.match(r"x_e6_g(\d+)_(\w+)_s(\d+)\.csv$", b)
        if not m:
            continue
        g, pol, s = int(m.group(1)) / 1024.0, m.group(2), int(m.group(3))
        d = load(f, 16384)
        if d:
            rec.setdefault((g, pol), {})[s] = d

    gs = sorted({k[0] for k in rec})
    pols = ["ours", "mix", "oracle", "allcloud"]
    print(f"{'g/KB':>6s} {'policy':9s} {'P50':>7s} {'P95':>7s} {'succ':>6s} {'上云份额':>8s} {'n':>3s}")
    out = {}
    for g in gs:
        for pol in pols:
            ds = list(rec.get((g, pol), {}).values())
            if not ds:
                continue
            a = agg(ds)
            out[(g, pol)] = a
            print(f"{g:6.0f} {pol:9s} {a['p50']:7.1f} {a['p95']:7.1f} {a['succ']:6.3f} "
                  f"{a['frac']:8.3f} {a['n']:3d}")

    print("\n=== Q1：贪心指派 vs 穷举指派（逐 seed 上云份额）===")
    print(f"{'g/KB':>6s} {'seed':>4s} {'mix':>8s} {'oracle':>8s} {'一致?':>5s}")
    all_match = True
    for g in gs:
        for s in sorted({k for (gg, p), v in rec.items() if gg == g for k in v}):
            dm = rec.get((g, "mix"), {}).get(s)
            do = rec.get((g, "oracle"), {}).get(s)
            if not (dm and do):
                continue
            ok = abs(dm["frac"] - do["frac"]) < 1e-6 and abs(dm["up"] - do["up"]) < 1
            all_match &= ok
            print(f"{g:6.0f} {s:4d} {dm['frac']:8.3f} {do['frac']:8.3f} {'是' if ok else '否':>5s}")
    print(f"全部一致: {'是' if all_match else '否'}")

    print("\n=== Q2/Q3：间隙（P50 口径，ms）===")
    print(f"{'g/KB':>6s} {'ours':>7s} {'mix':>7s} {'oracle':>7s} "
          f"{'ours-mix':>9s} {'%':>7s} {'mix-oracle':>11s} {'%':>7s}")
    for g in gs:
        o, x, r = out.get((g, "ours")), out.get((g, "mix")), out.get((g, "oracle"))
        if not (o and x and r):
            continue
        d1 = x["p50"] - o["p50"]
        d2 = r["p50"] - x["p50"]
        print(f"{g:6.0f} {o['p50']:7.1f} {x['p50']:7.1f} {r['p50']:7.1f} "
              f"{d1:+9.1f} {d1 / o['p50'] * 100:+7.1f} {d2:+11.1f} "
              f"{(d2 / x['p50'] * 100) if x['p50'] else 0:+7.1f}")

    print("\n=== 种子级细节（16 KB 主组与 m=5 组，支撑正文的稳健性表述）===")
    for g, keys in [(16.0, [(16.0, "ours"), (16.0, "mix"), (16.0, "oracle")])]:
        for gg, pol in keys:
            vs = [rec[(gg, pol)][s]["p50"] for s in sorted(rec[(gg, pol)])]
            p95s = [rec[(gg, pol)][s]["p95"] for s in sorted(rec[(gg, pol)])]
            print(f"  g={gg:.0f}KB {pol:7s} P50 seeds={vs}  P95 seeds={p95s}")
    for tag, gpat, rpat in [("m5", "x_e6_m5_*_s*.csv", r"x_e6_m5_(\w+)_s(\d+)\.csv"),
                            ("ln", "x_e6_ln_*_s*.csv", r"x_e6_ln_(\w+)_s(\d+)\.csv")]:
        for pol in ("ours", "mix", "oracle"):
            vs = []
            for f in glob.glob(os.path.join(BASE, gpat)):
                m = re.match(rpat, os.path.basename(f))
                if m and m.group(1) == pol:
                    d = load(f, 16384)
                    if d:
                        vs.append((int(m.group(2)), d["p50"], d["p95"]))
            if vs:
                vs.sort()
                print(f"  {tag} {pol:7s} " + "  ".join(f"s{s}:{p:.0f}/{q:.0f}" for s, p, q in vs))

    for tag, label, gpat, rpat in [
            ("m5", "m=5（16 KB，组合空间 243）", "x_e6_m5_*_s*.csv",
             r"x_e6_m5_(\w+)_s(\d+)\.csv"),
            ("ln", "异构批（lognormal σ=0.8，16 KB 中位，m=3）", "x_e6_ln_*_s*.csv",
             r"x_e6_ln_(\w+)_s(\d+)\.csv")]:
        print(f"\n=== {label} ===")
        rec2 = {}
        eg = 16384.0 * pow(2.718281828, 0.32) if tag == "ln" else None  # E[g]，ln 组用
        for f in glob.glob(os.path.join(BASE, gpat)):
            b = os.path.basename(f)
            m = re.match(rpat, b)
            if not m:
                continue
            d = load(f, 16384)
            if d:
                if eg:  # 异构批：按 E[g] 修正单个上云任务的字节期望
                    d["frac"] = d["up"] / (d["sent"] * (eg + 16384 + HDR))
                rec2.setdefault(m.group(1), []).append(d)
        print(f"{'policy':9s} {'P50':>7s} {'P95':>7s} {'succ':>6s} {'上云份额':>8s} {'n':>3s}")
        for pol in ["ours", "mix", "oracle", "allcloud"]:
            ds = rec2.get(pol)
            if not ds:
                continue
            a = agg(ds)
            print(f"{pol:9s} {a['p50']:7.1f} {a['p95']:7.1f} {a['succ']:6.3f} "
                  f"{a['frac']:8.3f} {a['n']:3d}")
        if "ours" in rec2 and "mix" in rec2:
            po = agg(rec2["ours"])["p50"]
            px = agg(rec2["mix"])["p50"]
            print(f"  ours→mix: {px - po:+.1f} ms ({((px - po) / po * 100):+.1f}%)")
    return out


def plot(out):
    """图 9：(a) P50 随粒度变化（ours/mix/oracle）；(b) 上云份额（指派结构）"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["SimSun"]
    plt.rcParams["font.size"] = 9
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "stix"
    OUT = r"D://工作区//家庭网络智能体协同承载边界论文//figs"
    os.makedirs(OUT, exist_ok=True)

    gs = sorted({k[0] for k in out})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.75))

    STYLE = {"ours": ("0.10", "o", "-", "本文判据（逐点）"),
             "mix": ("0.35", "D", "-", "批内混排贪心 $O(m\\log m)$"),
             "oracle": ("0.55", "s", "--", "ORACLE（$3^m$ 穷举）"),
             "allcloud": ("0.75", "^", ":", "全云")}
    for pol in ("ours", "mix", "oracle", "allcloud"):
        pts = [(g, out[(g, pol)]["p50"]) for g in gs if (g, pol) in out]
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax1.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, ls=ls,
                 ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    ax1.annotate("判据未计批内排队：\n$+68\\%$（16 KB）", xy=(16, 74), xytext=(1.3, 88),
                 fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax1.annotate("混排回收\n$\\approx-38\\%$", xy=(16, 46), xytext=(30, 34),
                 fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax1.set_xscale("log", base=2)
    ax1.set_xticks(gs)
    ax1.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax1.minorticks_off()
    ax1.set_xlabel("子任务粒度 $g$ / KB")
    ax1.set_ylabel("任务完成时延 P50 / ms")
    ax1.grid(alpha=0.22, lw=0.5)
    ax1.legend(fontsize=6.2, frameon=False, loc="upper left")
    ax1.tick_params(labelsize=7, direction="in")
    ax1.set_title("(a) 完成时延", fontsize=8)

    for pol in ("ours", "mix", "oracle"):
        pts = [(g, out[(g, pol)]["frac"] * 100) for g in gs if (g, pol) in out]
        if not pts:
            continue
        col, mk, ls, lab = STYLE[pol]
        ax2.plot([p[0] for p in pts], [p[1] for p in pts], color=col, marker=mk, ls=ls,
                 ms=3.6, lw=1.1, mfc="white", label=lab, zorder=3)
    ax2.axhline(100, color="0.75", lw=0.6, ls=":")
    ax2.annotate("混排与穷举指派逐位相同", xy=(16, 33.3), xytext=(1.4, 62),
                 fontsize=6.4, color="0.15",
                 arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
    ax2.set_xscale("log", base=2)
    ax2.set_xticks(gs)
    ax2.set_xticklabels([("%d" % g) for g in gs], fontsize=7)
    ax2.minorticks_off()
    ax2.set_xlabel("子任务粒度 $g$ / KB")
    ax2.set_ylabel("上云子任务份额 / %")
    ax2.set_ylim(-4, 108)
    ax2.grid(alpha=0.22, lw=0.5)
    ax2.legend(fontsize=6.2, frameon=False, loc="center right")
    ax2.tick_params(labelsize=7, direction="in")
    ax2.set_title("(b) 放置结构", fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig09_mix.png"), dpi=300)
    print("wrote", os.path.join(OUT, "fig09_mix.png"))


if __name__ == "__main__":
    rs = main()
    if rs:
        plot(rs)
