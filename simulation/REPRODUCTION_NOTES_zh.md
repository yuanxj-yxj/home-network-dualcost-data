# 实验环境安装与复现说明

本文全部实验在 **WSL2 (Ubuntu 22.04) + ns-3.35** 上完成，两个自研场景程序（Wi-Fi 全拓扑 `agent-sim.cc`、Thread/802.15.4 PAN `thread-edge.cc`）做**真实转发仿真**（任务与上下文数据以真实字节穿过拓扑）。以下步骤可从零复现。

## 1. 环境安装

1. **系统**：Windows 11 + WSL2，发行版 `Ubuntu2204`（`wsl -l -v` 确认，注意不是 `Ubuntu`）。
2. **ns-3.35**：下载 `ns-allinone-3.35.tar.bz2`，`./build.py` 或进 `ns-3.35/` 用 waf 编译。启用模块集（超集即可）：
   ```
   core, network, internet, point-to-point, applications, flow-monitor,
   traffic-control, csma, mobility, wifi, spectrum, propagation, antenna,
   energy, lr-wpan, sixlowpan
   ```
   （`quic` 模块为可选，本文实验不依赖；配置备份见 ns-3 源树根 `.wafconfigure` 输出。）
3. **依赖**：`g++`、`python3`（绘图侧另需 Windows 侧 Python ≥3.10 + `matplotlib`、`numpy`、`python-docx`、`pypdf`、`latex2mathml`、`math2docx`、`pywin32`）。

## 2. 编译场景程序

```bash
cd ~/ns3_work
# 场景源码放入 ns-3.35/scratch/ 后：
bash build_agentsim.sh    # 编译 agent-sim.cc -> build/scratch/agent-sim
bash build_thread.sh      # 编译 thread-edge.cc -> build/scratch/thread-edge
```

注意：
- 运行二进制需要 `LD_LIBRARY_PATH` 指向 ns-3 构建库目录（脚本内已处理）；
- `scratch/` 里任何编译不过的文件都会拖垮整个 waf 构建——放入前确认无残留旧文件；
- 线程场景 lr-wpan 用默认 O-QPSK 250 kbps；`LrWpanMac` 无退避参数接口（论文 §7 披露的限制）。

## 3. 运行实验（对应论文与数据目录）

| 实验 | 运行脚本 | 数据目录（`06_实验数据/agentsim/`） | 论文位置 |
|---|---|---|---|
| E1 发现两段律（固定 CW vs BEB，W 敏感性） | `run_agentsim_e1.sh` | `e1_v3/`（另有 e1_pinCW*/e1_sweep_*/e1_wsens* 过程批） | §5.1 |
| E2 阈值带 + 比较静态（含 B_u∈{2,4}、thresh 基线、oursmeas） | 批处理脚本（`run_remaining_*.sh` 系列） | `e2v3/ e2_bu_low/ e2_thresh/ e2_oursmeas/` | §5.3–5.4 |
| E3 Λ(C) 单峰 + 缓存增益（扩展至 512 KB） | 批处理脚本 | `e3v3/ e3_wide/` | §5.5 |
| E4 混合背景（CBR + TCP 两个生成器，各 160 runs） | 批处理脚本 | `e4v3/ e4tcp/` | §5.6 |
| E4b 阈值漂移直测（含强制端执行 t6、云侧 backup 重测） | 批处理脚本 | `e4bv3/ e4b_alllocal_t6/ e4b_v4/ e4b_thresh/` | §5.7 |
| E5 判据 vs ORACLE | 批处理脚本 | `e5v3/` | §5.8 |
| E6 批内 mixing | 批处理脚本 | `e6mix/` | §5.8 |
| T1 Thread 发现（10 N × 5 seeds） | `run_thread.sh` | `../thread/disc/` | §5.2 |
| T2 Thread 放置（g 512 B–64 KB + 真机栈 hwcheck） | `run_thread_t2.sh`（精简 `run_thread_t2_small.sh`） | `../thread/place/ ../thread/hwcheck/` | §5.9 |

批次约定：每个实验点 5 seeds（个别 3 seeds，正文已注明）；单次 60 s 仿真 wall 约 3–5 s，14 核可 7 路并行。已知陷阱：`taskTimeoutMs` 默认 2 s，g≥48 KB 强制端执行需 6 s（脚本已带参数，正文 §4.3 披露）。

## 4. 分析与出图

```bash
# 分析（生成表格数字）
python3 analysis/analyze_e3.py runs/agentsim/e3v3/        # 以此类推 e1..e6
python3 analysis/analyze_thread.py   ../thread/disc/
python3 analysis/analyze_thread_t2.py ../thread/place/
# 绘图（PNG -> figs_en/，TIF 300dpi -> figs/）
python3 analysis/plot_e1_law.py; python3 analysis/plot_e2.py
python3 analysis/plot_fig5_g2star.py; python3 analysis/plot_fig_theory_en.py
python3 analysis/gen_fig10.py; python3 analysis/plot_fig_theory_en.py   # Fig 1/2
# 英文图批量重绘（主稿 7 图 + 附件 4 图）
python3 make_figs_en_a.py; python3 make_figs_en_b.py
```

## 5. 论文构建（MD -> IEEE 双栏 DOCX -> PDF）

```powershell
# Windows 侧（需 Word + pywin32）
python build_en_docx.py     # 04_论文初稿_v1_EN.md -> DOCX（图/公式/表自动嵌入）
python build_supp_docx.py   # 05_投稿补充说明_Supplementary_EN.md -> DOCX
# PDF 用 Word COM 导出（ExportAsFixedFormat, 格式 17）
```

构建脚本要点：作者行在 `build_en_docx.py` 常量处维护；`FIGMAP` 定义图号→文件映射（正文 1–7）；正文中的 `Fig. N` 引用触发就近插图，`[[FIG:path|caption]]` 触发附件插图。

## 6. 硬件核查（T2 finding 2）

`runs/thread/hwcheck/` 来自真机栈对照：Linux `mac802154_hwsim` 虚拟 radio × 2（两个 netns），主线 6LoWPAN + RFC 4944，UDP echo + md5 校验，512 B–64 KB 每点 6 发——用于证明 ≥32 KB 复原停滞是 ns-3 模型行为而真实栈可送达 65507 B UDP 上限。
