#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 读取修正（2026-10-21）

背景：agent-sim 的 WriteCsv 原实现把"seed>1"当作 append 信号，导致批量脚本
（每个 seed 独立文件名）产生的 seed>=2 文件**只有数据行、没有表头**。
数据本身完好，仅缺首行。本模块在读入时按列数判定并补表头，
从而无需重跑 500+ 次实验。

用法：
    from csvfix import read_rows
    rows = read_rows(path)      # list[dict]，列名来自 CSV 或补入的 HEADER
"""
import os

HEADER = (
    "seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,"
    "wanUpBytes,wanDnBytes,payloadBytes,lambda,airtimeS,taskFailed,rounds,"
    "missingResp,discP50,discP95,discP50us,discP95us,txBusyS,retxTotal,"
    "rspTxTotal,rspPhyTxTotal,wanUpRealB,wanDnRealB,taskSent,taskDone"
).split(",")


def read_rows(path, min_bytes=0):
    """返回 list[dict]；自动补表头，并能容忍空文件/半截文件。"""
    if min_bytes and os.path.getsize(path) < min_bytes:
        return []
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            lines = [ln.rstrip("\r\n") for ln in f if ln.strip()]
    except OSError:
        return []
    if not lines:
        return []
    first = [x.strip() for x in lines[0].split(",")]
    if first[:3] == ["seed", "N", "m"]:
        names, body = first, lines[1:]
    else:
        names, body = HEADER, lines
    out = []
    for ln in body:
        parts = ln.split(",")
        if len(parts) < len(names):
            continue
        out.append(dict(zip(names, parts)))
    return out


def last_row(path):
    rows = read_rows(path)
    return rows[-1] if rows else None


if __name__ == "__main__":
    import glob
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else "runs/agentsim"
    bad = 0
    tot = 0
    for f in glob.glob(os.path.join(root, "**", "*.csv"), recursive=True):
        tot += 1
        if not read_rows(f):
            bad += 1
    print(f"扫描 {tot} 个 CSV，无法解析 {bad} 个")
