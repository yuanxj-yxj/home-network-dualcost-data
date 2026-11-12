#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 B 分析：② TCP 背景 vs CBR 背景（§5.7 三个百分比能否去引号）
④ 外部基线 thresh vs ours / allcloud / alllocal"""
import glob
import os
import statistics as st

BASE = r"D:\工作区\ns3_work\runs\agentsim"


def rows(path_glob):
    out = []
    for f in glob.glob(path_glob):
        lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
        if not lines:
            continue
        hdr = lines[0].split(",")
        if hdr[0] != "seed":
            continue
        out.append(dict(zip(hdr, lines[-1].split(","))))
    return out


def num(d, k):
    try:
        return float(d[k])
    except Exception:
        return float("nan")


def agg(rs):
    if not rs:
        return None
    return dict(
        p50=st.median([num(r, "p50") for r in rs]),
        p95=st.median([num(r, "p95") for r in rs]),
        succ=sum(num(r, "taskDone") for r in rs) / max(1, sum(num(r, "taskSent") for r in rs)),
        # 云份额只能用编排器计数（wanUpBytes，仅智能体流量）；
        # wanUpRealB 是 WAN 链路总字节，含背景流，不能用来判"是否上云"
        cloud=sum(1 for r in rs if num(r, "wanUpBytes") > 0) / len(rs),
        n=len(rs),
    )


print("=" * 88)
print("② ② TCP 背景 vs CBR 背景（g=16 KB, N=16, m=3, C=16 KB）")
print("=" * 88)
print(f"{'bg':8s} {'Bu':>3s} {'policy':9s} | {'CBR P50':>8s} {'TCP P50':>8s} {'Δ%':>7s} "
      f"| {'CBR P95':>8s} {'TCP P95':>8s} {'Δ%':>7s} | {'CBRsucc':>7s} {'TCPsucc':>7s}")
for bg in ("none", "video", "gaming", "backup"):
    for bu in (30, 10):
        for pol in ("ours", "allcloud", "alllocal", "static"):
            cbr = agg(rows(os.path.join(BASE, "e4v3", f"*e4_{bg}_bu{bu}_{pol}_s*.csv")))
            tcp = agg(rows(os.path.join(BASE, "e4tcp", f"*e4tcp_{bg}_bu{bu}_{pol}_s*.csv")))
            if not (cbr and tcp):
                continue
            d50 = (tcp["p50"] / cbr["p50"] - 1) * 100 if cbr["p50"] else float("nan")
            d95 = (tcp["p95"] / cbr["p95"] - 1) * 100 if cbr["p95"] else float("nan")
            print(f"{bg:8s} {bu:3d} {pol:9s} | {cbr['p50']:8.0f} {tcp['p50']:8.0f} {d50:+7.1f} "
                  f"| {cbr['p95']:8.0f} {tcp['p95']:8.0f} {d95:+7.1f} "
                  f"| {cbr['succ']:7.3f} {tcp['succ']:7.3f}")

print()
print("  -- 头两条百分比（§5.7 / §6.6 引用值）复核 --")
for pol in ("allcloud", "ours"):
    for bu, tag in ((30, "design point (+81%?)"), (10, "weak uplink, P95 (+110%?)")):
        base_c = agg(rows(os.path.join(BASE, "e4v3", f"*e4_none_bu{bu}_{pol}_s*.csv")))
        back_c = agg(rows(os.path.join(BASE, "e4v3", f"*e4_backup_bu{bu}_{pol}_s*.csv")))
        base_t = agg(rows(os.path.join(BASE, "e4tcp", f"*e4tcp_none_bu{bu}_{pol}_s*.csv")))
        back_t = agg(rows(os.path.join(BASE, "e4tcp", f"*e4tcp_backup_bu{bu}_{pol}_s*.csv")))
        if not (base_c and back_c and base_t and back_t):
            continue
        print(f"  {pol:9s} B_u={bu:2d} P50  CBR {base_c['p50']:6.0f}->{back_c['p50']:6.0f} "
              f"({(back_c['p50']/base_c['p50']-1)*100:+6.1f}%)   "
              f"TCP {base_t['p50']:6.0f}->{back_t['p50']:6.0f} "
              f"({(back_t['p50']/base_t['p50']-1)*100:+6.1f}%)")
        print(f"  {'':9s} {'':6s} P95  CBR {base_c['p95']:6.0f}->{back_c['p95']:6.0f} "
              f"({(back_c['p95']/base_c['p95']-1)*100:+6.1f}%)   "
              f"TCP {base_t['p95']:6.0f}->{back_t['p95']:6.0f} "
              f"({(back_t['p95']/base_t['p95']-1)*100:+6.1f}%)")

print()
print("=" * 88)
print("④ 外部基线 thresh（单阈值 + 网关实测上行） vs ours（门限带，标称上行）")
print("=" * 88)
print(f"{'bg':8s} {'g/KB':>6s} | {'ours':>8s} {'oursM':>8s} {'thresh':>8s} {'allcl':>9s} "
      f"| {'ours':>8s}{'oursM':>8s}{'thr':>8s}   (P50 ms / 上云份额)")
for bg in ("none", "backup"):
    for g in (128, 512, 2048, 4096, 8192, 16384, 24576, 32768, 65536):
        o = agg(rows(os.path.join(BASE, "e2v3", f"*A_g{g}_ours_s*.csv"))) \
            if g in (128, 512, 2048, 4096, 8192, 16384, 32768, 65536) else None
        if g == 24576:
            o = agg(rows(os.path.join(BASE, "e4b_thresh",
                                      f"*e4b_{bg}_g24576_ours_s*.csv")))
        m = agg(rows(os.path.join(BASE, "e2_oursmeas", f"*e2om_{bg}_g{g}_oursmeas_s*.csv")))
        t = agg(rows(os.path.join(BASE, "e2_thresh", f"*e2th_{bg}_g{g}_thresh_s*.csv")))
        c = agg(rows(os.path.join(BASE, "e2v3", f"*A_g{g}_allcloud_s*.csv"))) \
            if g in (128, 512, 2048, 4096, 8192, 16384, 32768, 65536) else None
        if not (t or m):
            continue
        fmt = lambda v, w: (f"{v['p50']:{w}.0f}" if v else f"{'-':>{w}s}")
        print(f"{bg:8s} {g:6d} | {fmt(o,8)} {fmt(m,8)} {fmt(t,8)} {fmt(c,9)} "
              f"| {(o['cloud']*100 if o else 0):7.0f}%{(m['cloud']*100 if m else 0):7.0f}%"
              f"{(t['cloud']*100 if t else 0):7.0f}%")

