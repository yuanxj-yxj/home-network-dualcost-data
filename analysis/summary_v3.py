#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3 数据一键汇总：E4 / E4b / E5 三张表，供论文取数。"""
import glob
import os
import re
import statistics as st

from csvfix import read_rows

R = r"D:/工作区/ns3_work/runs/agentsim"


def rows(d):
    return glob.glob(os.path.join(R, d, "*.csv"))


def pick(f):
    rs = read_rows(f)
    if not rs:
        return None
    r = rs[-1]
    try:
        p50, p95 = float(r["p50"]), float(r["p95"])
        sent, done = float(r["taskSent"]), float(r["taskDone"])
        up = float(r["wanUpBytes"])
    except (KeyError, ValueError):
        return None
    if p50 <= 0 or sent <= 0:
        return None
    return p50, p95, done / sent, up


def med(v):
    return st.median(v) if v else float("nan")


def e4():
    D = {}
    for f in rows("e4v3"):
        m = re.search(r"e4_(\w+?)_bu(\d+)_(\w+)_s(\d+)", os.path.basename(f))
        if not m:
            continue
        v = pick(f)
        if v:
            D.setdefault((m.group(1), int(m.group(2)), m.group(3)), []).append(v)
    print("\n### E4 混合负载（P50 / P95 / 成功率）")
    print(f"{'bg':7s}{'Bu':>4s} {'策略':9s}{'P50':>8s}{'P95':>8s}{'succ':>7s}{'n':>3s}")
    for (bg, bu, pol), vs in sorted(D.items()):
        print(f"{bg:7s}{bu:4d} {pol:9s}{med([v[0] for v in vs]):8.1f}"
              f"{med([v[1] for v in vs]):8.1f}{st.mean([v[2] for v in vs]):7.3f}{len(vs):3d}")
    return D


def e4b():
    D = {}
    for f in rows("e4bv3"):
        m = re.search(r"e4b_(\w+?)_g(\d+)_(\w+)_s(\d+)", os.path.basename(f))
        if not m:
            continue
        v = pick(f)
        if v:
            D.setdefault((m.group(1), int(m.group(2)) // 1024, m.group(3)), []).append(v)
    print("\n### E4b 门限位移（agentUp≈0 表示整轮不走云）")
    print(f"{'bg':7s}{'g/KB':>6s} {'策略':9s}{'P50':>8s}{'succ':>7s}{'agentUp/MB':>11s}{'云轮次%':>8s}")
    for (bg, g, pol), vs in sorted(D.items()):
        ncloud = 100.0 * sum(1 for v in vs if v[3] > 1e5) / len(vs)
        print(f"{bg:7s}{g:6d} {pol:9s}{med([v[0] for v in vs]):8.1f}"
              f"{st.mean([v[2] for v in vs]):7.3f}{st.mean([v[3] for v in vs]) / 1e6:11.2f}"
              f"{ncloud:8.0f}")
    return D


def e5():
    D = {}
    for f in rows("e5v3"):
        b = os.path.basename(f)
        m = re.search(r"e5_g(\d+)_(\w+)_s(\d+)", b)
        k = None
        if m:
            k = (int(m.group(1)) // 1024, m.group(2))
        else:
            m2 = re.search(r"e5_m5_(\w+)_s(\d+)", b)
            if m2:
                k = ("m5", m2.group(1))
        v = pick(f) if k else None
        if v:
            D.setdefault(k, []).append(v)
    print("\n### E5 ORACLE（相对最优的间隙）")
    print(f"{'g/KB':>6s} {'策略':9s}{'P50':>8s}{'succ':>7s}{'agentUp/MB':>11s}{'n':>3s}")
    for k, vs in sorted(D.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        print(f"{str(k[0]):>6s} {k[1]:9s}{med([v[0] for v in vs]):8.1f}"
              f"{st.mean([v[2] for v in vs]):7.3f}{st.mean([v[3] for v in vs]) / 1e6:11.2f}{len(vs):3d}")
    print("\n{'g':>6s} {'ours':>7s} {'oracle':>7s} {'gap%':>7s} {'allcloud':>9s}")
    for g in sorted({k[0] for k in D if isinstance(k[0], int)}):
        o = D.get((g, "ours"))
        r = D.get((g, "oracle"))
        c = D.get((g, "allcloud"))
        if o and r:
            po, pr = med([v[0] for v in o]), med([v[0] for v in r])
            print(f"{g:6d} {po:7.1f} {pr:7.1f} {(po - pr) / pr * 100:+7.1f} "
                  f"{(med([v[0] for v in c]) if c else float('nan')):9.1f}")
    return D


if __name__ == "__main__":
    e4()
    e4b()
    e5()
