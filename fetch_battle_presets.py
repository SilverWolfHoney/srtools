#!/usr/bin/env python3
"""下载 4 玩法挑战数据（战斗配置的怪物/星启来源）。

产出 data/site/：
  moc.json            —— 混沌回忆（期数 -> 层 -> 怪物波次 / 星启 monster_ids_tierce）
  pure-fictions.json  —— 虚构叙事
  ap-shadows.json     —— 末日幻影
  challenge-peak.json —— 异相仲裁

数据源（网站 srtools 已整理好的挑战数据，含星启模式；客户端 4.6.53 表里没有
星启字段，因此统一用网站数据）：
  https://cdn.neonteam.dev/neonteam/4.6.51-16704169/<name>.json

用法：python fetch_battle_presets.py
"""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "site"
VERSION = "4.6.51-16704169"
CDN = "https://cdn.neonteam.dev/neonteam"
FILES = ("moc.json", "pure-fictions.json", "ap-shadows.json", "challenge-peak.json")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dst = OUT / name
        try:
            req = urllib.request.Request(f"{CDN}/{VERSION}/{name}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            dst.write_bytes(data)
            print(f"{name}: {len(data)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"{name} 失败: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
