#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§5.8 权威数字表：e4b / alllocal_t6 / oursmeas / thresh 全量聚合（5 seeds）。"""
import glob
import os
import statistics as st

B = r"D:/工作区/ns3_work/runs/agentsim"
GS = (16384, 24576, 32768, 49152, 65536)


def med(pat, key="p50"):
    vs = []
    for f in glob.glob(pat):
        lines = [l.strip() for l in open(f) if l.strip()]
        if not lines:
            continue
        d = dict(zip(lines[0].split(","), lines[-1].split(",")))
        try:
            vs.append(float(d[key]))
        except Exception:
            pass
    return st.median(vs) if vs else None


def fmt(v):
    return ("%6.0f" % v) if v is not None else "    --"


print(f"{'g/KB':>5s} {'bg':>7s} | {'ours':>6s} {'allcl':>6s} {'endexec':>7s} "
      f"{'oursM':>6s} {'thresh':>6s}   (P50 ms)")
for g in GS:
    for bg in ("none", "backup"):
        ours = med(os.path.join(B, "e4b_thresh", f"x_e4b_{bg}_g{g}_ours_s*.csv")) \
            or med(os.path.join(B, "e4b_thresh", f"e4b_{bg}_g{g}_ours_s*.csv"))
        allc = med(os.path.join(B, "e4b_thresh", f"x_e4b_{bg}_g{g}_allcloud_s*.csv"))
        endx = med(os.path.join(B, "e4b_alllocal_t6", f"x_e4b_{bg}_g{g}_alllocal_t6_s*.csv"))
        oursm = med(os.path.join(B, "e2_oursmeas", f"e2om_{bg}_g{g}_oursmeas_s*.csv"))
        thr = med(os.path.join(B, "e2_thresh", f"e2th_{bg}_g{g}_thresh_s*.csv"))
        print(f"{g//1024:5d} {bg:>7s} | {fmt(ours)} {fmt(allc)} {fmt(endx)} "
              f"{fmt(oursm)} {fmt(thr)}")
