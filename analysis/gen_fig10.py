#!/usr/bin/env python3
# gen_fig10.py —— 由 T1 CSV 生成论文图 10（Thread 发现两段律/容量悬崖）
# 双面板：(a) P50 / P95 时延 vs N；(b) 成功率 vs N。
# 风格：灰度、黑体标题、宋体标签（贴合中文期刊），300 dpi。
import glob, re, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib import font_manager as fm

# 注册黑体（SimHei），贴合中文期刊黑体标题/宋体标签规范
_f = "C:/Windows/Fonts/simhei.ttf"
if os.path.exists(_f):
    fm.fontManager.addfont(_f)
    rcParams["font.family"] = "SimHei"
else:
    rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.titlesize"] = 12
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 10
rcParams["ytick.labelsize"] = 10
rcParams["axes.unicode_minus"] = False

NQUERIES = 60
D = "runs/thread/disc"
pat = re.compile(r"x_td_N(\d+)_be(\d)_s(\d+)\.csv")

Ns = []
P50, P95, SUCC = [], [], []
for f in sorted(glob.glob(f"{D}/x_td_N*_be0_s*.csv")):
    m = pat.search(f)
    if not m:
        continue
    N, be, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    data = np.loadtxt(f, delimiter=",", skiprows=1, usecols=(3,))
    data = data[data > 0]
    if N not in Ns:
        Ns.append(N)
        P50.append([]); P95.append([]); SUCC.append([])
    idx = Ns.index(N)
    P50[idx].append(np.percentile(data, 50))
    P95[idx].append(np.percentile(data, 95))
    SUCC[idx].append(min(100.0, len(data) / (N * NQUERIES) * 100.0))

Ns = np.array(Ns)
# 按设备数升序重排（glob 字典序会把 128 排到 16 前，导致折线锯齿）
_order = np.argsort(Ns)
Ns = Ns[_order]
P50 = np.array([np.mean(x) for x in P50])[_order]
P95 = np.array([np.mean(x) for x in P95])[_order]
SUCC = np.array([np.mean(x) for x in SUCC])[_order]

# 打印结果表
print(f"{'N':>5} {'P50_ms':>8} {'P95_ms':>8} {'succ%':>7}")
for n, a, b, c in zip(Ns, P50, P95, SUCC):
    print(f"{n:>5} {a:>8.1f} {b:>8.1f} {c:>7.1f}")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.6))
ax1.plot(Ns, P50, "o-", color="black", label="P50")
ax1.plot(Ns, P95, "s--", color="black", label="P95")
ax1.set_xlabel("设备数 N（Thread leaf）")
ax1.set_ylabel("发现时延 (ms)")
ax1.set_title("(a) Thread 发现时延 vs N")
ax1.legend(loc="upper left", frameon=False)
ax1.grid(True, alpha=0.3)

ax2.plot(Ns, SUCC, "^-", color="black")
ax2.set_xlabel("设备数 N（Thread leaf）")
ax2.set_ylabel("发现成功率 (%)")
ax2.set_title("(b) Thread 发现成功率 vs N")
ax2.set_ylim(0, 105)
ax2.grid(True, alpha=0.3)

fig.tight_layout()
out = "D:/工作区/家庭网络智能体协同承载边界论文/figs/fig10_thread_disc.png"
fig.savefig(out, dpi=300, bbox_inches="tight")
print("saved:", out)
