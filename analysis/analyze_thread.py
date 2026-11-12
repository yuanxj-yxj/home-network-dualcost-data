#!/usr/bin/env python3
# analyze_thread.py —— Thread 边缘实测 T1 发现扫描聚合
#
# 输入：runs/thread/disc/x_td_N{N}_be{B}_s{seed}.csv
#       列：N,seed,leafId,discMs,ok
# 输出：T1 汇总表（N, BEB/钉死, P50, P95, 成功率）+ 与 Wi-Fi E1 的对比提示
#
# 用法：python analyze_thread.py <disc_dir>

import glob, os, re, sys
import numpy as np

NQUERIES = 60  # 与 thread-edge.cc 默认 nQueries 一致：每 leaf 应发查询数

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "runs/thread/disc"
    pat = re.compile(r"x_td_N(\d+)_be(\d)_s(\d+)\.csv")
    rows = {}
    nfiles = {}
    for f in glob.glob(os.path.join(d, "x_td_N*_be*_s*.csv")):
        m = pat.search(os.path.basename(f))
        if not m:
            continue
        N, be, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            data = np.loadtxt(f, delimiter=",", skiprows=1, usecols=(3, 4))
        except Exception:
            continue
        if data.ndim == 1:
            data = data.reshape(1, -1)
        rtt = data[:, 0]
        key = (N, be)
        rows.setdefault(key, []).append(rtt)
        nfiles[key] = nfiles.get(key, 0) + 1
    print(f"{'N':>5} {'mode':>6} {'P50_ms':>9} {'P95_ms':>9} {'succ':>6}")
    for (N, be) in sorted(rows.keys()):
        allv = np.concatenate(rows[(N, be)])
        p50 = np.percentile(allv, 50)
        p95 = np.percentile(allv, 95)
        # 成功率 = 实际收到回复数 / (leaf数 × 每leaf应发数 × seed文件数)，封顶 100
        succ = min(100.0, len(allv) / (N * NQUERIES * nfiles[key]) * 100.0)
        mode = "BEB" if be == 0 else "pinBe"
        print(f"{N:>5} {mode:>6} {p50:>9.1f} {p95:>9.1f} {succ:>5.1f}%")

if __name__ == "__main__":
    main()
