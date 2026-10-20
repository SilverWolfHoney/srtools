#!/usr/bin/env python3
"""下载挑战数据（战斗配置的数据源，4.6.53）。

两个来源：
1) nanoka：https://static.nanoka.cc/hsr/<版本>/zh/<玩法>/<期>.json
   产出 data/site/nanoka/{maze,story,boss,peak}/<期>.json
   —— 混沌/虚构/末日/异相仲裁的波次、stage、敌人词条、污染、赛季效果

2) neonteam（原网站同源）：https://cdn.neonteam.dev/neonteam/<版本>/<文件>.json
   产出 data/site/neonteam/{moc,pure-fictions,ap-shadows,challenge-peak}.json
   —— 关卡等级 level、回合数 cycle_count、关卡基础机制 buff（turbulence_maze_buff_id）；
      这些字段 nanoka 没有，但原网站导出配置里带它们，缺了虚构会卡加载

版本更新时：改 NANOKA_BASE / NEONTEAM_BASE 里的版本号 + 期号列表，重跑本脚本，再跑 build_catalog.py。
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NANOKA_OUT = ROOT / "data" / "site" / "nanoka"
NEONTEAM_OUT = ROOT / "data" / "site" / "neonteam"

NANOKA_BASE = "https://static.nanoka.cc/hsr/4.6.53/zh"
NEONTEAM_BASE = "https://cdn.neonteam.dev/neonteam/4.6.51-16704169"
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


def main() -> int:
    for mode, periods in PLAN.items():
        d = NANOKA_OUT / mode
        d.mkdir(parents=True, exist_ok=True)
        for p in periods:
            dst = d / f"{p}.json"
            if dst.is_file():
                print(f"nanoka {mode}/{p}.json 已存在，跳过")
                continue
            try:
                data = get(f"{NANOKA_BASE}/{mode}/{p}.json")
                json.loads(data.decode("utf-8"))  # 校验
                dst.write_bytes(data)
                print(f"nanoka {mode}/{p}.json: {len(data)} bytes")
            except Exception as exc:  # noqa: BLE001
                print(f"nanoka {mode}/{p}.json 失败: {exc}")

    NEONTEAM_OUT.mkdir(parents=True, exist_ok=True)
    for name in NEONTEAM_FILES:
        dst = NEONTEAM_OUT / f"{name}.json"
        if dst.is_file():
            print(f"neonteam {name}.json 已存在，跳过")
            continue
        try:
            data = get(f"{NEONTEAM_BASE}/{name}.json")
            json.loads(data.decode("utf-8"))
            dst.write_bytes(data)
            print(f"neonteam {name}.json: {len(data)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"neonteam {name}.json 失败: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
