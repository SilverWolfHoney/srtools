#!/usr/bin/env python3
"""下载 / 重建行迹树资源（游戏风格行迹树面板用）。

产出：
  data/trace_layout.json   —— 每个命途 Point01..Point18 的坐标（来自 srtools 网站 JS）
  data/trace_trees.json    —— 每个角色的行迹树节点（anchor / pre_points / 图标 / 等级上限 / 加成）
  web/trace-icons/*.webp   —— 行迹图标（游戏资源，不随仓库分发）
  web/trace-bg.jpg         —— 行迹树星空背景

数据源：srtools.neonteam.dev（版本 4.6.51-16704169，行迹结构与 4.6.53 一致）
  https://srtools.neonteam.dev/assets/index-*.js
  https://cdn.neonteam.dev/neonteam/4.6.51-16704169/avatars.json

用法：
    python fetch_trace_assets.py              # 全部重建（已存在的图标跳过）
    python fetch_trace_assets.py --no-icons   # 只更新 layout / trace_trees
"""
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WEB = ROOT / "web"
VERSION = "4.6.51-16704169"
SITE = "https://srtools.neonteam.dev"
CDN = "https://cdn.neonteam.dev/neonteam"
UA = {"User-Agent": "Mozilla/5.0"}


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def find_site_js() -> str:
    html = http_get(SITE + "/").decode("utf-8", "replace")
    m = re.search(r'src="(/assets/index-[^"]+\.js)"', html)
    if not m:
        raise SystemExit("找不到网站 JS 入口")
    return SITE + m.group(1)


def extract_layout(js_text: str) -> dict:
    """从网站 JS 提取按命途的 Point 坐标对象。"""
    m = re.search(r'\{Priest:\{Point01:\{class:"point main-trace"', js_text)
    if not m:
        raise SystemExit("JS 里找不到行迹树布局对象")
    start = m.start()

    def match_end(text: str, i: int) -> int:
        depth = 0
        in_str = None
        while i < len(text):
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ('"', "'"):
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError("unbalanced layout object")

    block = js_text[start:match_end(js_text, start)]
    fixed = re.sub(r'([{,])([A-Za-z_$][\w$]*):', r'\1"\2":', block)
    return json.loads(fixed)


def convert_tree(trees: dict, icon_urls: dict) -> dict:
    out = {}
    for pid, node in (trees or {}).items():
        url = node.get("icon") or ""
        name = url.rsplit("/", 1)[-1] if url else ""
        if url:
            icon_urls[name] = url
        out[str(pid)] = {
            "anchor": node.get("anchor") or "",
            "pre": [str(x) for x in (node.get("pre_points") or [])],
            "icon": name,
            "max": int(node.get("max_level") or 1),
            "adds": [
                {"type": a.get("type"), "value": a.get("value")}
                for a in (node.get("status_add_list") or [])
                if isinstance(a, dict)
            ],
        }
    return out


def main() -> int:
    no_icons = "--no-icons" in sys.argv
    DATA.mkdir(exist_ok=True)
    WEB.mkdir(exist_ok=True)

    print("1/3 提取行迹树布局 ...")
    js_url = find_site_js()
    print("    JS:", js_url)
    js_text = http_get(js_url).decode("utf-8", "replace")
    layout = extract_layout(js_text)
    (DATA / "trace_layout.json").write_text(
        json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print("    layout:", len(layout), "个命途 ->", DATA / "trace_layout.json")

    print("2/3 提取行迹树数据 ...")
    avatars = json.loads(http_get(f"{CDN}/{VERSION}/avatars.json").decode("utf-8"))
    icon_urls: dict = {}
    result = {"layout": layout, "avatars": {}}
    for aid, entry in avatars.items():
        tree = convert_tree(entry.get("skill_trees") or {}, icon_urls)
        if not tree:
            continue
        result["avatars"][str(aid)] = {"tree": tree}
        enh = convert_tree(entry.get("skill_trees_enhanced") or {}, icon_urls)
        if enh:
            result["avatars"][str(aid)]["tree_enhanced"] = enh
    (DATA / "trace_trees.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")
    enh_count = sum(1 for v in result["avatars"].values() if "tree_enhanced" in v)
    print(f"    角色 {len(result['avatars'])} 个（加强 {enh_count} 个），图标 {len(icon_urls)} 个")
    print("    ->", DATA / "trace_trees.json")

    if no_icons:
        print("3/3 跳过图标下载（--no-icons）")
        return 0

    print("3/3 下载图标与背景 ...")
    icons_dir = WEB / "trace-icons"
    icons_dir.mkdir(exist_ok=True)

    def fetch_icon(name: str) -> str:
        dst = icons_dir / name
        if dst.exists() and dst.stat().st_size > 200:
            return "cached"
        url = icon_urls.get(name)
        if not url:
            return "fail"
        try:
            data = http_get(url, timeout=20)
        except Exception:  # noqa: BLE001
            return "fail"
        if len(data) < 100:
            return "fail"
        dst.write_bytes(data)
        return "ok"

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        for status in pool.map(fetch_icon, sorted(icon_urls)):
            if status in ("ok", "cached"):
                ok += 1
            else:
                fail += 1
    print(f"    图标 {ok} 成功 / {fail} 失败 -> {icons_dir}")

    try:
        bg = http_get(SITE + "/bg.jpg")
        (WEB / "trace-bg.jpg").write_bytes(bg)
        print("    背景 ->", WEB / "trace-bg.jpg", len(bg), "bytes")
    except Exception as exc:  # noqa: BLE001
        print("    背景下载失败:", exc)

    print("4/4 下载命途底图 ...")
    traces_dir = WEB / "traces"
    traces_dir.mkdir(exist_ok=True)
    paths = ["Priest", "Warrior", "Mage", "Shaman", "Rogue", "Warlock",
             "Knight", "Memory", "Elation"]
    ok_paths = 0
    for name in paths:
        dst = traces_dir / f"{name}.svg"
        if dst.exists() and dst.stat().st_size > 500:
            ok_paths += 1
            continue
        try:
            data = http_get(f"{SITE}/traces/{name}.svg", timeout=20)
            dst.write_bytes(data)
            ok_paths += 1
        except Exception:  # noqa: BLE001
            pass
    print(f"    命途底图 {ok_paths}/{len(paths)} -> {traces_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
