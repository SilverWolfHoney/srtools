#!/usr/bin/env python3
"""下载 nanoka 4 玩法挑战数据（战斗配置的数据源，4.6.53）。

产出 data/site/nanoka/：
  maze/<期>.json   —— 混沌回忆（层含 event_id_list1/2 + 第三节点 event_id_list + invasion）
  story/<期>.json  —— 虚构叙事（dict.level）
  boss/<期>.json   —— 末日幻影（dict.level，含 boss_monster_id1/2）
  peak/<期>.json   —— 异相仲裁（pre_level + boss_level + boss_config，含 tag_list/invasion）

数据源：https://static.nanoka.cc/hsr/<版本>/zh/<玩法>/<期>.json
（nanoka.cc 每次版本更新都会跟进；客户端 Excel 里没有星启/入侵字段，故以它为准）

版本更新时：改 BASE 里的版本号 + 期号列表，重跑本脚本，再跑 build_catalog.py。
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "site" / "nanoka"
BASE = "https://static.nanoka.cc/hsr/4.6.53/zh"

# 各玩法最近 4 期（版本更新时改这里）
PLAN = {
    "maze": [1034, 1035, 1036, 1037],
    "story": [2025, 2026, 2027, 2028],
    "boss": [3020, 3021, 3022, 3023],
    "peak": [8, 9, 10, 11],
}


def main() -> int:
    for mode, periods in PLAN.items():
        d = OUT / mode
        d.mkdir(parents=True, exist_ok=True)
        for p in periods:
            url = f"{BASE}/{mode}/{p}.json"
            dst = d / f"{p}.json"
            if dst.is_file():
                print(f"{mode}/{p}.json 已存在，跳过")
                continue
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                json.loads(data.decode("utf-8"))  # 校验
                dst.write_bytes(data)
                print(f"{mode}/{p}.json: {len(data)} bytes")
            except Exception as exc:  # noqa: BLE001
                print(f"{mode}/{p}.json 失败: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
