#!/usr/bin/env python3
"""下载挑战数据（战斗配置的数据源，4.6.54）。

两个来源：
1) nanoka：https://static.nanoka.cc/hsr/<版本>/zh/<玩法>/<期>.json
   产出 data/site/nanoka/{maze,story,boss,peak}/<期>.json
        data/site/nanoka/{monster,relicset}.json
   —— 混沌/虚构/末日/异相仲裁的波次、stage、敌人词条、污染、赛季效果，
      以及怪物表、遗器套装描述

2) neonteam（原网站同源）：https://cdn.neonteam.dev/neonteam/<版本>/<文件>.json
   产出 data/site/neonteam/{moc,pure-fictions,ap-shadows,challenge-peak}.json
   —— 关卡等级 level、回合数 cycle_count、关卡基础机制 buff（turbulence_maze_buff_id）；
      这些字段 nanoka 没有，但原网站导出配置里带它们，缺了虚构会卡加载。
      注意：官网数据可能滞后（当前 Metadata.json 的 CurrentVersion 是 4.6.51），
      版本号以 https://cdn.neonteam.dev/neonteam/Metadata.json 的 CurrentVersion 为准。

用法：python fetch_battle_presets.py [--force]
      --force 覆盖已存在的文件（版本更新时用）；默认跳过已存在的文件。
版本更新时：改 NANOKA_VERSION / NEONTEAM_VERSION 与期号列表，重跑本脚本，再跑 build_catalog.py。
"""
import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NANOKA_OUT = ROOT / "data" / "site" / "nanoka"
NEONTEAM_OUT = ROOT / "data" / "site" / "neonteam"

NANOKA_VERSION = "4.6.54"
NANOKA_ROOT = f"https://static.nanoka.cc/hsr/{NANOKA_VERSION}"          # 角色/光锥/怪物/套装
NANOKA_BASE = f"{NANOKA_ROOT}/zh"                                       # 挑战数据（带语言）
NANOKA_EXTRA = ("monster.json", "relicset.json")   # 怪物表 / 遗器套装描述（在版本根目录下）
NEONTEAM_VERSION = "4.6.51-16704169"               # 官网当前版本（Metadata.CurrentVersion）
NEONTEAM_BASE = f"https://cdn.neonteam.dev/neonteam/{NEONTEAM_VERSION}"
NEONTEAM_FILES = ("moc", "pure-fictions", "ap-shadows", "challenge-peak")

# 各玩法最近 4 期（版本更新时改这里）
PLAN = {
    "maze": [1034, 1035, 1036, 1037],
    "story": [2025, 2026, 2027, 2028],
    "boss": [3020, 3021, 3022, 3023],
    "peak": [8, 9, 10, 11],
}


def get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def save(dst: Path, data: bytes, force: bool, label: str) -> None:
    if dst.is_file() and not force:
        print(f"{label} 已存在，跳过（--force 覆盖）")
        return
    json.loads(data.decode("utf-8"))  # 校验
    dst.write_bytes(data)
    print(f"{label}: {len(data)} bytes")


def main() -> int:
    ap = argparse.ArgumentParser(description="下载挑战数据")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件（版本更新时用）")
    args = ap.parse_args()

    for mode, periods in PLAN.items():
        d = NANOKA_OUT / mode
        d.mkdir(parents=True, exist_ok=True)
        for p in periods:
            dst = d / f"{p}.json"
            if dst.is_file() and not args.force:
                print(f"nanoka {mode}/{p}.json 已存在，跳过")
                continue
            try:
                save(dst, get(f"{NANOKA_BASE}/{mode}/{p}.json"), True, f"nanoka {mode}/{p}.json")
            except Exception as exc:  # noqa: BLE001
                print(f"nanoka {mode}/{p}.json 失败: {exc}")

    for name in NANOKA_EXTRA:
        try:
            save(NANOKA_OUT / name, get(f"{NANOKA_ROOT}/{name}"), args.force, f"nanoka {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"nanoka {name} 失败: {exc}")

    NEONTEAM_OUT.mkdir(parents=True, exist_ok=True)
    for name in NEONTEAM_FILES:
        try:
            save(NEONTEAM_OUT / f"{name}.json", get(f"{NEONTEAM_BASE}/{name}.json"),
                 args.force, f"neonteam {name}.json")
        except Exception as exc:  # noqa: BLE001
            print(f"neonteam {name}.json 失败: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
