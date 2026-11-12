#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 A 结果分析：E4b 强制 home、B_u=2/4 Mbps、E3 C 扫到 512 KB。"""
import glob
import os
import re
import statistics as st

BASE = r"D:\工作区\ns3_work\runs\agentsim"


def load(f):
    lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
    hdr = lines[0].split(",")
    if hdr[0] != "seed":
        return None
    row = lines[-1].split(",")
    return dict(zip(hdr, row))


def num(d, k):
    try:
        return float(d[k])
    except Exception:
        return float("nan")


print("=" * 78)
print("① E4b：24/32/48 KB 强制家庭执行（alllocal）实测 P50/P95")
print("=" * 78)
print(f"{'bg':8s} {'g/KB':>5s} {'n':>3s} {'P50':>8s} {'P95':>8s} {'done/sent':>12s}")
for bg in ("none", "backup"):
    for g in (24576, 32768, 49152):
        fs = glob.glob(os.path.join(BASE, "e4b_thresh", f"*e4b_{bg}_g{g}_alllocal_s*.csv"))
        recs = [load(f) for f in fs]
        recs = [r for r in recs if r]
        if not recs:
            print(f"{bg:8s} {g//1024:5d}  --  no data")
            continue
        p50 = st.median([num(r, "p50") for r in recs])
        p95 = st.median([num(r, "p95") for r in recs])
        done = sum(num(r, "taskDone") for r in recs) / max(1, sum(num(r, "taskSent") for r in recs))
        print(f"{bg:8s} {g//1024:5d} {len(recs):3d} {p50:8.0f} {p95:8.0f} {done:12.3f}")

print()
print("=" * 78)
print("⑤ B_u = 2/4 Mbps：门限带行为（推论 2.2，B_u^min≈5.7 Mbps 以下）")
print("=" * 78)
print(f"{'Bu':>3s} {'g/KB':>5s} {'pol':9s} {'P50':>7s} {'P95':>7s} {'succ':>6s} {'cloudUp%':>9s}")
for bu in (2, 4):
    for g in (8192, 16384, 32768, 65536):
        for pol in ("ours", "allcloud", "alllocal"):
            fs = glob.glob(os.path.join(BASE, "e2_bu_low", f"*bu{bu}_g{g}_{pol}_s*.csv"))
            recs = [load(f) for f in fs]
            recs = [r for r in recs if r]
            if not recs:
                continue
            p50 = st.median([num(r, "p50") for r in recs])
            p95 = st.median([num(r, "p95") for r in recs])
            succ = sum(num(r, "taskDone") for r in recs) / max(
                1, sum(num(r, "taskSent") for r in recs))
            up = sum(1 for r in recs if num(r, "wanUpRealB") > 0) / len(recs) * 100
            print(f"{bu:3d} {g//1024:5d} {pol:9s} {p50:7.0f} {p95:7.0f} {succ:6.3f} {up:9.0f}")

print()
print("=" * 78)
print("③ E3：Λ(C) 扫到 512 KB + 链路/编排器字节比（重传放大诊断）")
print("=" * 78)
print(f"{'C/KB':>5s} {'psi':>3s} {'pol':9s} {'P50':>7s} {'Lam_real':>9s} {'Lam_ana':>9s} "
      f"{'real/up':>8s} {'done':>6s}")
M, G_KB, RHO, ROUNDS = 3, 64.0, 0.5, 150
for C in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
    for psi in (0, 1):
        for pol in ("allcloud", "ours"):
            fs = glob.glob(os.path.join(BASE, "e3_wide", f"*e3_C{C}_p{psi}_{pol}_s*.csv"))
            recs = [load(f) for f in fs]
            recs = [r for r in recs if r]
            if not recs:
                continue
            p50 = st.median([num(r, "p50") for r in recs])
            lam = st.median([(num(r, "wanUpRealB") + num(r, "wanDnRealB")) for r in recs])
            lam /= M * G_KB * 1024.0
            ana = ROUNDS * ((C / (M if psi else 1.0)) + G_KB * (1 + RHO)) / (M * G_KB)
            ra = st.median([num(r, "wanUpRealB") / num(r, "wanUpBytes")
                            if num(r, "wanUpBytes") > 0 else float("nan") for r in recs])
            done = sum(num(r, "taskDone") for r in recs) / max(
                1, sum(num(r, "taskSent") for r in recs))
            print(f"{C:5d} {psi:3d} {pol:9s} {p50:7.0f} {lam:9.1f} {ana:9.1f} "
                  f"{ra:8.2f} {done:6.3f}")
