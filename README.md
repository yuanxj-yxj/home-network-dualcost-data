# NS-3.35 Simulation Datasets: Discovery–Execution Dual-Cost Measurements for Home-Network Multi-Agent Collaboration

Raw simulation output and analysis scripts for the manuscript *"The Carrying-Capacity Boundary of Home-Network Multi-Agent Collaboration: A Discovery–Execution Dual-Cost Model and Threshold Criteria"*.

All experiments are **real-forwarding NS-3.35 simulations**: subtask blocks and agent context data cross the topology as real bytes (no analytic shortcuts). Two custom scenario programs are included:

- `simulation/agent-sim.cc` — Wi-Fi full topology: cloud node — (WAN p2p, rate `B_u`, RTT `r_c`) — gateway — (home-bus CSMA, 100 Mbps) — home compute host (orchestrator + capability directory + execution host) — (AP-bridged 802.11n 5 GHz) — *N* terminal agents. Multicast discovery is realised as directed broadcast.
- `simulation/thread-edge.cc` — Thread/802.15.4 star PAN: *N* leaves + 1 border coordinator over lr-wpan (250 kbps) with 6LoWPAN + IPv6; the border node doubles as home host and WAN pivot.

## Repository layout

```
data/
  agentsim/          Wi-Fi experiments (one CSV per seed × configuration point)
  thread/            Thread/802.15.4 experiments
    disc/            T1: discovery under saturating offer (x_td_N<NNN>_be<0|1>_s<k>.csv)
    place/           T2: cross-address-family execution placement (probe_g<NNNN>_bc|lb.csv)
    hwcheck/         T2 hardware check: real Linux stack UDP ceiling vs. ns-3 model
simulation/          ns-3 scenario sources, build & run scripts, reproduction notes
analysis/            Python scripts that produced every figure/table in the paper
```

## Experiment suites → paper sections

| Suite | Directory(s) | Content (paper section) |
|---|---|---|
| **E1** discovery two-regime law | `agentsim/e1_v3` (pin + beb), `e1_pinCW_v2`, `e1_w0_v2` | Discovery latency vs. device density under pinned contention window vs. BEB (§5.1); `e1_sweep_*`, `e1_wsens*` are supporting sweeps/sensitivity runs |
| **E2** threshold band & comparative statics | `agentsim/e2v3` (primary), `e2_formal` (extended grid) | Placement threshold g₂* vs. g, B_u, r_c, C (§5.3–5.4) |
| **E3** carrying-amplification Λ(C), unimodal self-limitation | `agentsim/e3v3` (primary), `e3_wide` (extended C scan) | Λ(C) rise–peak–collapse, ψ∈{0,1} (§5.5) |
| **E4** mixed background load | `agentsim/e4v3` (CBR background), `e4tcp` (TCP-feedback background) | Threshold drift under three background flows, 160 runs each (§5.6, Table 4) |
| **E4b** threshold shift at four granularities | `agentsim/e4b_v4`, `e4b_thresh`, `e4bv3` | g₂* drift under background (§5.7) |
| **E5** gap to batch-level ORACLE | `agentsim/e5v3`, `e5_oracle` | Pointwise criterion vs. 3^m-enumeration ORACLE (§5.8) |
| **E6** intra-batch mixing | `agentsim/e6mix` | O(m log m) LPT-style mixing vs. pointwise criterion (§5.8) |
| **T1** Thread/802.15.4 discovery | `thread/disc` | Per-query latency & success vs. N on a second medium (§5.2) |
| **T2** cross-address-family execution placement | `thread/place`, `thread/hwcheck` | 802.15.4 + 6LoWPAN → dual-stack border → IPv4 WAN relay (§5.9) |

Directories named `*_probe`, `mode_probe`, `timing_probe`, `smoke2` are implementation probes and smoke tests; they are not used in the paper's figures and are included only for completeness.

## Data dictionary (Wi-Fi CSV, `agentsim/`)

One row per (seed × configuration). Key columns:

| Column | Meaning |
|---|---|
| `seed, N, m, g, ctxKB, psi` | RNG seed; device count; subtasks/task; subtask granularity (B); agent context (KB); placement preset (0 = default, 1 = all-cloud reference) |
| `rttMs, bwUpMbps` | WAN RTT (ms) and uplink rate (Mbps) |
| `discovery, policy` | discovery mode (`multicast` / `directory`); placement policy under test (`ours` / `allcloud` / ...) |
| `p50, p95` | task latency quantiles (ms) |
| `discP50, discP95` (and `…us`) | discovery latency quantiles (ms / µs); 360 ms cap reported as "≥" |
| `wanUpBytes, wanDnBytes, wanUpRealB, wanDnRealB` | WAN bytes (modelled vs. link-layer counted, incl. retransmission) |
| `lambda` | carrying-amplification ratio Λ |
| `retxTotal, rspTxTotal, rspPhyTxTotal` | retransmission accounting by answer-frame UID |
| `taskSent, taskDone, taskFailed` | task completion bookkeeping |

Thread CSVs: `disc/` has per-query rows (`N, seed, leafId, discMs, ok`); `place/` has per-send rows (`g, seed, owMs`); `hwcheck/` records per-send integrity (`send_ok, delivered, md5_ok, rtt_ms`).

## Statistical discipline

- 3–5 seeds per configuration point; 95% confidence intervals via *t*-distribution where reported.
- E1 dispatches no tasks (keeps discovery latency uncontaminated); retransmissions are counted by answer-frame UID; W=0 rows are the labelled "synchronous-send worst case" with 1 ms jitter.
- T2 medians reject reassembly-stall outliers (>5 s); the ≥32 KB points are ns-3-model failure cases, settled by `thread/hwcheck` (real Linux stack delivers to the 65507 B UDP ceiling).

## Reproducing

1. Install ns-3.35 (WSL2 Ubuntu 22.04 was used; module list in `simulation/REPRODUCTION_NOTES_zh.md`, Chinese, with step-by-step build/run commands).
2. Compile the scenario programs with `simulation/build_agentsim.sh` / `build_thread.sh`.
3. Run experiment grids with `simulation/run_*.sh`.
4. Regenerate figures/tables with `analysis/*.py` (Python ≥3.10, matplotlib, numpy). Paths inside the scripts point to the original run tree; point `BASE` at `data/agentsim` (or set `NS3DATA`) to reuse them on this repository's layout.

## License

Dataset and documents: CC-BY-4.0. Simulation and analysis code: MIT.
