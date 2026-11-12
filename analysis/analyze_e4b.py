#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E4b：背景流下的门限位移（直接实测）

判据落点用 wanUpBytes（仅智能体流量）判定：
  wanUpBytes ≈ 0  → 整轮落在家庭/端（不走云）
  wanUpBytes > 0  → 存在云放置
注意：wanUpRealB 含背景流字节，不能用作落点判据。
"""
import glob
import os
import re
import statistics as st

from csvfix import read_rows

BASE = os.environ.get("NS3DATA", r"D:/工作区/ns3_work/runs/agentsim/e4bv3")


def load(path):
    rows = read_rows(path)
    if not rows:
        return None
    r = rows[-1]
    try:
        p50 = float(r["p50"])
        p95 = float(r["p95"])
        up = float(r["wanUpBytes"])
        sent = float(r["taskSent"])
        done = float(r["taskDone"])
    except (KeyError, ValueError):
        return None
    if p50 <= 0 or sent <= 0:
        return None
    return dict(p50=p50, p95=p95, up=up, succ=done / sent)


def main():
    rec = {}
    for f in glob.glob(os.path.join(BASE, "*.csv")):
        m = re.search(r"e4b_(none|backup)_g(\d+)_(\w+)_s(\d+)", os.path.basename(f))
        if not m:
            continue
        bg, g, pol = m.group(1), int(m.group(2)) / 1024.0, m.group(3)
        d = load(f)
        if not d:
            continue
        rec.setdefault((bg, g, pol), []).append(d)

    print(f"{'bg':7s} {'g/KB':>6s} {'policy':9s} {'P50':>8s} {'P95':>8s} "
          f"{'succ':>6s} {'agentUp/MB':>11s} {'cloud%':>7s}")
    rows = []
    for (bg, g, pol), ds in sorted(rec.items()):
        p50 = st.median([d["p50"] for d in ds])
        p95 = st.median([d["p95"] for d in ds])
        succ = st.mean([d["succ"] for d in ds])
        up = st.mean([d["up"] for d in ds]) / 1e6
        ncloud = sum(1 for d in ds if d["up"] > 1e5) / len(ds) * 100
        print(f"{bg:7s} {g:6.0f} {pol:9s} {p50:8.1f} {p95:8.1f} "
              f"{succ:6.3f} {up:11.2f} {ncloud:7.0f}")
        rows.append(dict(bg=bg, g=g, pol=pol, p50=p50, p95=p95, succ=succ,
                         up=up, ncloud=ncloud, n=len(ds)))

    # 关键判别点：g=24 KB（解析 g2*=19 KB vs 有效上行下 28.6 KB）
    print("\n=== 判别点 g=24 KB：无背景应走云、备份应仍走家庭 ===")
    for bg in ("none", "backup"):
        for pol in ("ours", "allcloud"):
            r = [x for x in rows if x["bg"] == bg and x["g"] == 24 and x["pol"] == pol]
            if r:
                r = r[0]
                print(f"  {bg:6s} {pol:8s}: agentUp={r['up']:.2f} MB, "
                      f"云放置轮次占比={r['ncloud']:.0f}%, P50={r['p50']:.1f} ms")
    return rows


if __name__ == "__main__":
    main()
