#!/bin/bash
# E3 大上下文探针：C=128 / 1024 KB，检查编排器字节数(wanUpBytes) vs 链路实测(wanUpRealB) 是否偏离
NS3=/root/quic-research/ns-allinone-3.35/ns-3.35
BIN=$NS3/build/scratch/agent-sim
export LD_LIBRARY_PATH=$NS3/build/lib
OUT=/mnt/d/工作区/ns3_work/runs/agentsim/e3_probe
mkdir -p "$OUT"

for C in 128 1024; do
  for POL in allcloud ours; do
    S=$(date +%s)
    $BIN --mode=E3 --policy=$POL --ctxKB=$C --psi=0 --g=65536 --duration=60 \
         --seed=1 --out="$OUT/x_probe_C${C}_${POL}_s1" > /dev/null 2>&1
    E=$(date +%s)
    f="$OUT/x_probe_C${C}_${POL}_s1.csv"
    if [ -f "$f" ]; then
      python3 - "$f" "$C" "$POL" "$((E-S))" << 'PY'
import sys
f, c, pol, wall = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
lines = [l.strip() for l in open(f) if l.strip()]
hdr = lines[0].split(',')
row = lines[-1].split(',')
d = dict(zip(hdr, row))
def num(k):
    try: return float(d[k])
    except: return float('nan')
up, real = num('wanUpBytes'), num('wanUpRealB')
ratio = up/real if real else float('nan')
print(f"C={c}KB {pol:9s} wall={wall}s  p50={num('p50'):.0f}ms  done={num('taskDone'):.0f}/{num('taskSent'):.0f}  "
      f"wanUp={up/1e6:.2f}MB  real={real/1e6:.2f}MB  ratio={ratio:.3f}  lambda={num('lambda'):.1f}")
PY
    else
      echo "C=$C $POL NO OUTPUT (wall=$((E-S))s)"
    fi
  done
done
