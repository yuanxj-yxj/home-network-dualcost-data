# -*- coding: utf-8 -*-
"""应答窗口 W 敏感性分析：量化"W=0 同步齐发"对发现时滞与重传的影响。

读取 e1_wsens/ws_W{W}_N{N}_s{seed}.csv，按 (W, N) 聚合。
用法：python analyze_e1_wsens.py [目录]
"""
import glob
import math
import os
import re
import sys

HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,"
        "wanUpBytes,wanDnBytes,payloadBytes,lambda,airtimeS,taskFailed,rounds,"
        "missingResp,discP50,discP95,discP50us,discP95us,txBusyS,retxTotal,"
        "rspTxTotal,rspPhyTxTotal").split(",")
COL = {h: i for i, h in enumerate(HEAD)}
T95 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


def stat(v):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, 0.0
    s = sum((x - m) ** 2 for x in v) / (n - 1)
    return m, T95.get(n, 2.571) * math.sqrt(s / n)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else r"D:\工作区\ns3_work\runs\agentsim\e1_wsens"
    G = {}
    for f in glob.glob(os.path.join(d, "ws*_W*_N*_s*.csv")):
        m = re.search(r"ws\d*_W(\d+)_N(\d+)_s(\d+)\.csv$", os.path.basename(f))
        if not m:
            continue
        W, N, sd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
        if lines and lines[0].split(",")[0] == "seed":
            lines = lines[1:]
        if not lines:
            continue
        r = lines[-1].split(",")
        if len(r) < len(HEAD):
            continue
        G.setdefault((W, N), []).append(
            (float(r[COL["discP50us"]]), float(r[COL["discP95us"]]),
             int(r[COL["retxTotal"]]), int(r[COL["rspTxTotal"]]),
             float(r[COL["txBusyS"]]), int(r[COL["missingResp"]])))

    print("| W/ms | N | seeds | discP50 µs | discP95 µs | r̄（重传/次应答） | txBusyS | 缺失/轮 |")
    print("|---|---|---|---|---|---|---|---|")
    for (W, N) in sorted(G):
        rows = G[(W, N)]
        d50, c50 = stat([x[0] for x in rows])
        d95, _ = stat([x[1] for x in rows])
        rr = [x[2] / x[3] for x in rows if x[3] > 0]
        rb, _ = stat(rr) if rr else (0, 0)
        busy, _ = stat([x[4] for x in rows])
        miss, _ = stat([x[5] / 50.0 for x in rows])
        print("| %d | %d | %d | %.0f ± %.0f | %.0f | %.2f | %.4f | %.1f |"
              % (W, N, len(rows), d50, c50, d95, rb, busy, miss))


if __name__ == "__main__":
    main()
