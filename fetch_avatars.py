#!/usr/bin/env python3
"""下载角色头像（web/avatars/<id>.webp）。

头像来自 srtools 站点的 CDN（米哈游游戏资源），不随仓库分发；
公开仓库请保持 .gitignore 里的 `web/avatars/` 排除项。

用法：
    python fetch_avatars.py            # 下载 catalog 里所有角色
    python fetch_avatars.py --only 1204 1001

CDN 可用环境变量覆盖：SWH_ICON_CDN
"""
import argparse
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web" / "avatars"
DEFAULT_CDN = ("https://cdn.neonteam.dev/neonteam/assets/spriteoutput/"
               "avatarshopicon/avatar/{}.webp")


def fetch(aid: int, cdn: str) -> tuple:
    dst = OUT / f"{aid}.webp"
    if dst.exists() and dst.stat().st_size > 1000:
        return aid, "cached", dst.stat().st_size
    try:
        req = urllib.request.Request(cdn.format(aid),
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 1000 or data[:4] != b"RIFF":
            return aid, "invalid", len(data)
        OUT.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return aid, "ok", len(data)
    except Exception as exc:  # noqa: BLE001
        return aid, f"fail:{type(exc).__name__}", 0


def main() -> int:
    import os
    ap = argparse.ArgumentParser(description="下载 SRTools 角色头像")
    ap.add_argument("--only", type=int, nargs="*", help="只下载这些角色 id")
    args = ap.parse_args()

    cdn = os.environ.get("SWH_ICON_CDN", DEFAULT_CDN)
    catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    ids = args.only or sorted({int(a["id"]) for a in catalog["avatars"]})
    print(f"下载 {len(ids)} 个角色头像 -> {OUT}")

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for aid, status, size in pool.map(lambda i: fetch(i, cdn), ids):
            if status in ("ok", "cached"):
                ok += 1
            else:
                fail += 1
                print("  missing:", aid, status)
    total = sum(p.stat().st_size for p in OUT.glob("*.webp")) if OUT.is_dir() else 0
    print(f"完成: {ok} 成功 / {fail} 失败, 共 {total / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
