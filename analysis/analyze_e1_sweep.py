# -*- coding: utf-8 -*-
"""
聚合 E1 扫描结果（sweepW{W}_N{N}_s{seed}.csv），输出按 (W, N) 分组的统计表
与 log-log 拟合指数，用于检验命题 1 的两段律。

用法：
  python analyze_e1_sweep.py <csv目录> [<csv目录2> ...]

输出列说明：
  discP50us  发现时滞中位数（µs）
  txBusyS    真实空口占用（PhyTxBegin/End 累加，含 AP 与全部终端，含重传）
  retx       平均每次成功应答的重传次数 = retxTotal / (rounds*N)
  missing    每轮平均缺失数
"""
import glob
import math
import os
import re
import sys

COL = {}
HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,"
        "wanUpBytes,wanDnBytes,payloadBytes,lambda,airtimeS,taskFailed,rounds,"
        "missingResp,discP50,discP95,discP50us,discP95us,txBusyS,retxTotal,"
        "rspTxTotal,rspPhyTxTotal").split(",")
for i, h in enumerate(HEAD):
    COL[h] = i

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def mean(xs):
    return sum(xs) / len(xs)


def ci95(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return T95.get(n, 2.262) * math.sqrt(var / n)


def main():
    LABEL = {"sweepW0": "BEB自适应 W=0",
             "sweepW20": "BEB自适应 W=20",
             "pin": "CW钉死(禁用BEB) W=0"}
    groups = {}
    for d in sys.argv[1:]:
        for f in glob.glob(os.path.join(d, "*.csv")):
            m = re.match(r"(sweepW\d+|pin)_N(\d+)_s(\d+)\.csv", os.path.basename(f))
            if not m:
                continue
            series, n, seed = m.group(1), int(m.group(2)), int(m.group(3))
            if series not in LABEL:
                continue
            w = series  # 组键用系列名
            with open(f, encoding="utf-8") as fh:
                lines = [l.strip() for l in fh if l.strip()]
            # 兼容两种形态：表头+数据行；仅有数据行（WriteCsv 在 seed>1 且文件
            # 为新建时不写表头）。逐行解析，取每个 seed 的最后一行。
            if lines and lines[0].split(",")[0] == "seed":
                lines = lines[1:]
            if not lines:
                continue
            row = lines[-1].split(",")
            if len(row) < len(HEAD):
                continue
            g = groups.setdefault((w, n), [])
            # retx 速率的分母：新版 CSV 有 rspTxTotal（应答帧应用层发送次数），
            # 旧版没有，退化用 rounds*N。
            rsptx = None
            if len(row) > COL.get("rspTxTotal", 10 ** 6):
                try:
                    rsptx = int(row[COL["rspTxTotal"]])
                except ValueError:
                    rsptx = None
            g.append(dict(seed=seed,
                          disc=float(row[COL["discP50us"]]),
                          disc95=float(row[COL["discP95us"]]),
                          busy=float(row[COL["txBusyS"]]),
                          retx=int(row[COL["retxTotal"]]),
                          rsptx=rsptx,
                          rounds=int(row[COL["rounds"]]),
                          missing=int(row[COL["missingResp"]]),
                          N=int(row[COL["N"]])))

    if not groups:
        print("未找到任何 sweepW*_N*_s*.csv")
        return

    for w in sorted(set(k[0] for k in groups)):
        print("\n=== %s ===" % LABEL.get(w, w))
        print("| N | seeds | discP50 µs (mean±95%%CI) | txBusyS | retx/resp | missing/轮 | 相邻档指数 γ |")
        print("|---|---|---|---|---|---|---|")
        ns = sorted(k[1] for k in groups if k[0] == w)
        prev = None
        fits = []
        for n in ns:
            rows = groups[(w, n)]
            disc = [r["disc"] for r in rows]
            resp_total = [r["rsptx"] if r["rsptx"] else max(r["rounds"] * r["N"], 1)
                          for r in rows]
            retxpp = [r["retx"] / rt for r, rt in zip(rows, resp_total)]
            miss = [r["missing"] / max(r["rounds"], 1) for r in rows]
            busy = [r["busy"] for r in rows]
            gtext = "—"
            if prev is not None:
                gamma = math.log(mean(disc) / prev[1]) / math.log(n / prev[0])
                gtext = "%.2f" % gamma
                fits.append((n, gamma))
            print("| %d | %d | %.0f ± %.0f | %.4f | %.2f | %.1f | %s |"
                  % (n, len(rows), mean(disc), ci95(disc), mean(busy),
                     mean(retxpp), mean(miss), gtext))
            prev = (n, mean(disc))
        # 整段 log-log 斜率（最小二乘，等权；只取本 W 的组）
        pts = sorted(set((math.log(k[1]),
                          math.log(mean([r["disc"] for r in groups[k]])))
                         for k in groups if k[0] == w))
        if len(pts) >= 3:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            mx, my = mean(xs), mean(ys)
            den = sum((x - mx) ** 2 for x in xs)
            if den > 0:
                slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
                print("\n整段 log-log 斜率（含最低 N 点）≈ %.2f" % slope)
        hi = [(n, g) for n, g in fits if n >= 16]
        if hi:
            print("高密度段（N≥16）平均指数 ≈ %.2f" % (sum(g for _, g in hi) / len(hi)))


if __name__ == "__main__":
    main()
