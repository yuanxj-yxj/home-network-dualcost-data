#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_thread_t2.py — T2 执行放置 over Thread/802.15.4 的实测分析
输入：runs/thread/place/t2_g{G}_s{S}_lb.csv  (g,seed,leafId,owMs)
      runs/thread/place/t2_g{G}_s{S}_bc.csv  (g,seed,owMs)
模型（与 05_Thread边缘实测方案.md §5 一致）：
    T0(g) = κg/f0t                         # leaf 本地，无传输
    T1(g) = τ_lb(g) + κg/f1                # leaf→border 卸载（802.15.4 + 6LoWPAN）
    T2(g) = τ_lb(g) + τ_bc + C/Bu + κg/f2  # border 双栈 pivot → cloud
输出：τ_lb(g)/τ_bc(g) 中位数表、g1*(f0t) / g2*(Bu) 阈值表、图 fig11_thread_place.png
"""
import os, glob, csv, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, "runs/thread/place")
FIG  = os.path.join(BASE, "..", "家庭网络智能体协同承载边界论文", "figs", "fig11_thread_place.png")

# ---- 与论文一致的常数（E2 / §3.1） ----
KAPPA = 0.0043        # GFLOP / byte  (16KB ≈ 70 GFLOP)
F1    = 2000.0        # 家庭主机 TFLOP/s → GFLOP/s
F2    = 50000.0       # 云 GFLOP/s
C_KB  = 16.0          # 基础上下文 KB
BU    = 30.0          # 上行带宽 Mbps（默认设计点）
RC_MS = 30.0          # 云 RTT ms（仅用于 τ_bc 口径，已含在 τ_bc 实测）
# Wi-Fi 端→家庭主机单向传输（用于跨介质对比）：取 50 Mbps 有效速率
WIFI_EW_MBPS = 50.0

GSWEEP = [1024, 4096, 8192, 16384, 32768, 65536]

# 6LoWPAN 重组停滞 / 发送失败离群剔除阈值（ms）
# 大粒度（≥32KB）会触发 60s+ 重组停滞或 r=-1 发送失败，这些不是真实单向时延。
OUTLIER_MS = 5000.0

def load_lb_bc():
    lb, bc = {}, {}
    for f in glob.glob(os.path.join(OUT, "t2_g*_s*_lb.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try:
                    g = int(r["g"]); v = float(r["owMs"])
                except (ValueError, KeyError):
                    continue
                if v > OUTLIER_MS:   # 重组停滞离群，剔除
                    continue
                lb.setdefault(g, []).append(v)
    for f in glob.glob(os.path.join(OUT, "t2_g*_s*_bc.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try:
                    g = int(r["g"]); v = float(r["owMs"])
                except (ValueError, KeyError):
                    continue
                if v > OUTLIER_MS:
                    continue
                bc.setdefault(g, []).append(v)
    return lb, bc

def median(xs):
    return float(np.median(xs)) if xs else float("nan")

def thr_g1(kappa, f0t, f1, tbl_lb):
    """T0=T1 → κg/f0t = τ_lb(g) + κg/f1。
    注意单位：κg/f 给出秒，τ_lb 为毫秒，统一换算到毫秒比较。"""
    gs = sorted(tbl_lb)
    ggrid = np.linspace(64, 70000, 8000)
    def tau_lb_interp(g):
        return float(np.interp(g, gs, [tbl_lb[x] for x in gs]))
    ds = []
    for g in ggrid:
        t0 = 1000.0*kappa*g/f0t               # ms
        t1 = tau_lb_interp(g) + 1000.0*kappa*g/f1
        ds.append((g, t0 - t1))
    # 找变号点（真实阈值）
    for i in range(len(ds)-1):
        if ds[i][1] == 0:
            return ds[i][0]
        if ds[i][1]*ds[i+1][1] < 0:
            g0, d0 = ds[i]; g1, d1 = ds[i+1]
            return g0 - d0*(g1-g0)/(d1-d0)
    # 无变号：全为正 → 卸载主导（g1*≈0）；全为负 → 本地主导（g1*→∞）
    if ds[0][1] > 0:
        return 0.0
    return float("inf")

def thr_g2(kappa, f1, f2, tau_bc, C_KB, Bu):
    """T1=T2 → κg(1/f1 - 1/f2) = τ_bc + C/Bu  → g2* 解析。"""
    rhs = tau_bc/1000.0 + (C_KB*8.0)/(Bu*1e6)   # 秒
    lhs = kappa*(1.0/f1 - 1.0/f2)
    return rhs/lhs if lhs > 0 else float("inf")

def main():
    lb, bc = load_lb_bc()
    if not lb:
        print("NO DATA YET — T2 sweep CSVs not present."); return
    gs = sorted(set(list(lb)+list(bc)))
    print("=== τ_lb(g) / τ_bc(g) 实测中位数（干净区间 g≤16KB；>16KB 受 6LoWPAN 重组停滞污染，单列）===")
    print(f"{'g(B)':>8} {'τ_lb(ms)':>10} {'τ_bc(ms)':>10} {'τ_lb/τ_wifi':>10}  note")
    tau_lb_med, tau_bc_med = {}, {}
    for g in gs:
        tl = median(lb.get(g, [])); tc = median(bc.get(g, []))
        tau_lb_med[g] = tl; tau_bc_med[g] = tc
        tau_wifi = g*8.0/(WIFI_EW_MBPS*1e6)*1000.0
        note = "" if g <= 16384 else "REASSEMBLY-STALL / SEND-FAIL"
        print(f"{g:>8} {tl:>10.2f} {tc:>10.2f} {tl/tau_wifi:>10.1f}  {note}")

    tau_bc_def = median(bc.get(GSWEEP[2], [])) or tau_bc_med.get(GSWEEP[2], 17.0)
    print(f"\n=== g1*(f0t)  Thread leaf 本地 vs border (Bu={BU} Mbps) ===")
    for f0t in (0.02, 0.05, 0.1, 0.5, 1.0):
        g1 = thr_g1(KAPPA, f0t, F1, tau_lb_med)
        if g1 == 0.0:
            print(f"  f0t={f0t:>5} GFLOP/s  → g1* ≈ 0  (本地计算过慢，卸载主导全部 g)")
        elif g1 == float("inf"):
            print(f"  f0t={f0t:>5} GFLOP/s  → g1* → ∞ (τ_154 主导，本地主导全部 g)")
        else:
            print(f"  f0t={f0t:>5} GFLOP/s  → g1* ≈ {g1:,.0f} B ({g1/1024:.2f} KB)")
    print(f"\n=== g2*(Bu)  border vs cloud（f1={F1}, f2={F2}, τ_bc≈{tau_bc_def:.1f}ms @Bu={BU}）===")
    for bu in (10.0, 30.0, 100.0):
        # τ_bc 随带宽反比缩放
        tc = tau_bc_def * (BU/bu)
        g2 = thr_g2(KAPPA, F1, F2, tc, C_KB, bu)
        print(f"  Bu={bu:>6} Mbps → g2* ≈ {g2:,.0f} B ({g2/1024:.2f} KB)")

    # ---- 图：τ_lb(g) 实测 + Wi-Fi 对比（双对数） ----
    # 仅绘制 g ≤ 16KB 的"干净"曲线；32/64KB 受 6LoWPAN 重组停滞/发送失败污染，单独标注为失败案例。
    clean_gs = [g for g in gs if g <= 16384 and g in tau_lb_med]
    gg = np.array(clean_gs, float)
    tl = np.array([tau_lb_med[g] for g in clean_gs])
    tw = gg*8.0/(WIFI_EW_MBPS*1e6)*1000.0
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.loglog(gg, tl, "o-", color="#1f4e79", label="Thread/802.15.4 τ_lb(g) (measured, g≤16 KB)")
    ax.loglog(gg, tw, "s--", color="#c0392b", label="Wi-Fi end→home τ (50 Mbps, ref)")
    # 失败案例标注（合并为一段文字，置于两曲线之间的空白带）
    if 32768 in tau_lb_med:
        ax.plot(32768, tau_lb_med[32768], "x", color="#e67e22", ms=10, mew=2,
                label="32 KB: reassembly stall")
    fail_txt = ("Failure cases (ns-3 model, beyond clean range):\n"
                "  32 KB → 6LoWPAN reassembly stall (60 s+)\n"
                "  64 KB → send error r = −1\n"
                "Real Linux stack delivers up to 65507 B via\n"
                "two-level fragmentation (see hardware check)")
    ax.text(0.03, 0.42, fail_txt, transform=ax.transAxes, fontsize=8,
            color="#444444", va="top",
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#bbbbbb", lw=0.6))
    ax.set_ylim(0.04, 20000)
    ax.set_xlabel("subtask granularity g (bytes)")
    ax.set_ylabel("one-way transfer delay (ms)")
    ax.set_title("Cross-media execution placement: Thread leaf→border transfer cost")
    ax.grid(True, which="both", ls=":", lw=0.5)
    ax.legend(fontsize=9, loc="lower right")
    fig.tight_layout()
    os.makedirs(os.path.dirname(FIG), exist_ok=True)
    fig.savefig(FIG, dpi=300)
    print("\nfig saved:", os.path.abspath(FIG))

if __name__ == "__main__":
    main()
