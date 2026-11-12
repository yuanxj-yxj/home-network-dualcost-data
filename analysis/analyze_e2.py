# -*- coding: utf-8 -*-
"""E2 正式扫描聚合：门限带曲线（A）与比较静态（B）。

用法：python analyze_e2.py [目录]
文件名：A_g{g}_{pol}_s{s}.csv / B_{pert}_g{g}_s{s}.csv
"""
import glob
import math
import os
import re
import sys

HEAD = ("seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
        "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
        "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
        "wanUpRealB,wanDnRealB,taskSent,taskDone").split(",")
COL = {h: i for i, h in enumerate(HEAD)}
T95 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


def stat(v):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, 0.0
    s = sum((x - m) ** 2 for x in v) / (n - 1)
    return m, T95.get(n, 2.571) * math.sqrt(s / n)


def rows(d):
    for f in glob.glob(os.path.join(d, "*.csv")):
        b = os.path.basename(f)
        m = re.match(r"(?:e2f_)?(A)_g(\d+)_(\w+)_s(\d+)\.csv$", b)
        if not m:
            m = re.match(r"(?:e2f_)?(B)_([a-z0-9]+)_g(\d+)_s(\d+)\.csv$", b)
            if not m:
                continue
            yield ("B", m.group(2), int(m.group(3)), m.group(4), f)
            continue
        yield ("A", m.group(3), int(m.group(2)), m.group(4), f)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else r"D:\工作区\ns3_work\runs\agentsim\e2_formal"
    G = {}
    for part, key, g, seed, f in rows(d):
        lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
        if lines and lines[0].split(",")[0] == "seed":
            lines = lines[1:]
        if not lines:
            continue
        r = lines[-1].split(",")
        if len(r) < 26:
            continue
        G.setdefault((part, key, g), []).append(r)

    for part in ("A", "B"):
        ks = sorted(k for k in G if k[0] == part)
        if not ks:
            continue
        print("\n=== %s ===" % ("A 门限带曲线（基线参数）" if part == "A" else "B 比较静态（ours）"))
        print("| 条件 | g (KB) | seeds | P50 ms | P95 ms | 成功率 | 实测 λ | WAN up/down (MB) |")
        print("|---|---|---|---|---|---|---|---|")
        for k in ks:
            rr = G[k]
            p50, c50 = stat([float(r[COL["p50"]]) for r in rr])
            p95, _ = stat([float(r[COL["p95"]]) for r in rr])
            succ = []
            lam = []
            wup = []
            wdn = []
            for r in rr:
                # 成功率的分母必须是实际派发数：E2 用 directory 发现，
                # rounds 列（只在 multicast 分支计数）恒为 0，故用 taskSent/taskDone
                if len(r) > COL["taskSent"]:
                    ts = int(r[COL["taskSent"]])
                    if ts > 0:
                        succ.append(int(r[COL["taskDone"]]) / float(ts))
                lam.append(float(r[COL["lambda"]]))
                wup.append(int(r[COL["wanUpRealB"]]) / 1e6)
                wdn.append(int(r[COL["wanDnRealB"]]) / 1e6)
            sr = stat(succ)[0] if succ else float("nan")
            lr, _ = stat(lam)
            wu, _ = stat(wup)
            wd, _ = stat(wdn)
            label = k[1] if part == "A" else "%s g=%dKB" % (k[1], k[2] // 1024 or 1)
            gg = k[2] // 1024 if k[2] >= 1024 else k[2]
            gtxt = "%d KB" % gg if k[2] >= 1024 else "%d B" % k[2]
            print("| %s | %s | %d | %.1f ± %.1f | %.1f | %s | %.1f | %.2f / %.2f |"
                  % (label, gtxt, len(rr), p50, c50, p95,
                     ("%.2f" % sr) if sr == sr else "—", lr, wu, wd))


if __name__ == "__main__":
    main()
