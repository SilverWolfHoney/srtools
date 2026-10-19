#!/usr/bin/env python3
"""从 4.6.53 客户端 DesignData / 本地资源表构建编辑器用的数据目录（catalog.json）。

数据来源（全部本机离线，不联网）：

| catalog 段 | 来源 |
|---|---|
| avatars | `SilverWolfHoney/resources/AvatarConfig.json`（含联动角色） |
| avatar_promotions | `BakedConfig/ExcelOutputGameCore/AvatarPromotionConfig.bytes` |
| avatar_ranks | `BakedConfig/ExcelOutputGameCore/AvatarRankConfig.bytes` |
| skill_points | `SilverWolfHoney/resources/AvatarSkillTreeConfig.json` |
| lightcones | `BakedConfig/ExcelOutputGameCore/EquipmentConfig.bytes` |
| relic_sets | `BakedConfig/ExcelOutputGameCore/RelicSetConfig.bytes` |
| relics | `SilverWolfHoney/resources/RelicConfig.json` |
| relic_main_affixes / relic_sub_affixes | `BakedConfig/ExcelOutputGameCore/RelicMainAffixConfig.bytes` / `RelicSubAffixConfig.bytes` |
| monsters | `BakedConfig/ExcelOutputGameCore/MonsterConfig.bytes` |
| rogue_buffs | `BakedConfig/ExcelOutput/RogueBuff.bytes` |
| names | `SilverWolfHoney/dump_4.6.53/TextMap.json` |

用法：

    python build_catalog.py                  # 用默认路径生成 data/catalog.json
    python build_catalog.py --check          # 只统计不写盘
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SWH = Path(r"E:\HSRBetaPS\SilverWolfHoney")
DEFAULT_CLIENT = Path(r"F:\StarRail_4.6.53")
GAMECORE = "ExcelOutputGameCore/"
EXCEL = "ExcelOutput/"


def _rarity(value) -> int:
    """`CombatPowerAvatarRarityType4` -> 4；数字原样返回。"""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "")
    tail = text[-1:] if text else ""
    return int(tail) if tail.isdigit() else 0


def _fixed(value) -> float:
    """FixPoint 结构 / 数字 -> float。"""
    if isinstance(value, dict):
        return float(value.get("Value") or 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value, default=0) -> int:
    if isinstance(value, dict):
        value = value.get("Value", value.get("ID", default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Builder:
    def __init__(self, swh: Path, client: Path):
        self.swh = swh
        self.client = client
        sys.path.insert(0, str(swh))
        from tools.hsr_design import DesignConfig

        self.cfg = DesignConfig(client, swh / "dump_4.6.53" / "data.json")
        t = time.time()
        raw = json.loads((swh / "dump_4.6.53" / "TextMap.json").read_text(encoding="utf-8"))
        self.text_map: dict[int, str] = {}
        for row in raw:
            ident = row.get("ID") or {}
            h64 = ident.get("Hash64")
            if h64 is not None:
                self.text_map[int(h64)] = row.get("Text") or ""
        print(f"TextMap: {len(self.text_map)} 条，{time.time() - t:.1f}s")

    # ---------------------------------------------------------------- 工具
    def text(self, value) -> str:
        """TextID -> 本地化文本。"""
        if isinstance(value, dict):
            for key in ("Hash64", "Hash"):
                h = value.get(key)
                if h is not None and int(h) in self.text_map:
                    return self.text_map[int(h)]
            return ""
        if isinstance(value, int) and value in self.text_map:
            return self.text_map[value]
        return str(value or "")

    def table(self, path: str, row_type: str) -> list:
        t = time.time()
        rows = self.cfg.parse_excel(path, row_type)
        print(f"  {path.rsplit('/', 1)[-1]:42s} {len(rows):6d} 行  {time.time() - t:.1f}s")
        return rows

    def load_res(self, name: str, key: str) -> list:
        data = json.loads((self.swh / "resources" / name).read_text(encoding="utf-8"))
        return data[key]

    # ---------------------------------------------------------------- 各段
    def avatars(self) -> list:
        avatars = self.load_res("AvatarConfig.json", "avatar_config")
        ld = self.load_res("AvatarConfigLD.json", "avatar_config_ld") \
            if (self.swh / "resources/AvatarConfigLD.json").is_file() else []
        seen = {a["AvatarID"] for a in avatars}
        for a in ld:
            if a.get("AvatarID") not in seen:
                avatars.append(a)
        out = []
        for a in sorted(avatars, key=lambda x: x.get("AvatarID") or 0):
            out.append({
                "id": _int(a.get("AvatarID")),
                "name": self.text(a.get("AvatarName")),
                "full_name": self.text(a.get("AvatarFullName")),
                "rarity": _rarity(a.get("Rarity")),
                "path": str(a.get("AvatarBaseType") or ""),
                "damage": str(a.get("DamageType") or ""),
                "max_rank": _int(a.get("MaxRank"), 6),
                "max_promotion": _int(a.get("MaxPromotion"), 6),
                "sp_need": _fixed(a.get("SPNeed")),
                "release": a.get("Release"),
            })
        return out

    def skill_points(self) -> dict:
        rows = self.load_res("AvatarSkillTreeConfig.json", "avatar_skill_tree")
        by_avatar: dict[int, dict] = {}
        for row in rows:
            avatar_id = _int(row.get("AvatarID"))
            point_id = _int(row.get("PointID"))
            if not avatar_id or not point_id:
                continue
            item = by_avatar.setdefault(avatar_id, {}).setdefault(point_id, {
                "point_id": point_id,
                "anchor_type": str(row.get("AnchorType") or ""),
                "point_type": _int(row.get("PointType")),
                "max_level": 0,
                "icon": str(row.get("IconPath") or ""),
                "name": str(row.get("PointName") or ""),
                "desc": str(row.get("PointDesc") or ""),
                # 加强角色的行迹有两套：普通点 7 位（1212001），
                # 强化点为普通 +10,000,000（11212001）。10 个加强角色才有强化点。
                "enhanced": point_id >= 10_000_000,
            })
            item["max_level"] = max(item["max_level"], _int(row.get("MaxLevel"), 1))
            if not item["icon"]:
                item["icon"] = str(row.get("IconPath") or "")
        out = {}
        for avatar_id, points in by_avatar.items():
            items = []
            for point_id in sorted(points):
                item = dict(points[point_id])
                anchor = item["anchor_type"]
                item["anchor"] = int(anchor[-2:]) if anchor[-2:].isdigit() else 0
                items.append(item)
            out[str(avatar_id)] = items
        return out

    def avatar_promotions(self) -> dict:
        rows = self.table(GAMECORE + "AvatarPromotionConfig.bytes",
                          "RPG.GameCore.AvatarPromotionRow")
        out: dict[int, list] = {}
        for row in rows:
            avatar_id = _int(row.get("AvatarID"))
            out.setdefault(avatar_id, []).append({
                "promotion": _int(row.get("Promotion")),
                "max_level": _int(row.get("MaxLevel")),
                "attack": _fixed(row.get("AttackBase")),
                "hp": _fixed(row.get("HPBase")),
            })
        return out

    def avatar_ranks(self) -> dict:
        rows = self.table(GAMECORE + "AvatarRankConfig.bytes",
                          "RPG.GameCore.AvatarRankConfigRow")
        out: dict[int, list] = {}
        for row in rows:
            rank_id = _int(row.get("RankID"))
            avatar_id = rank_id // 100
            out.setdefault(avatar_id, []).append({
                "rank_id": rank_id,
                "rank": _int(row.get("Rank")),
                "name": self.text(row.get("Name")),
                "desc": self.text(row.get("Desc")),
            })
        for items in out.values():
            items.sort(key=lambda x: x["rank"])
        return out

    def lightcones(self) -> list:
        rows = self.table(GAMECORE + "EquipmentConfig.bytes",
                          "RPG.GameCore.EquipmentRow")
        out = []
        for row in sorted(rows, key=lambda r: _int(r.get("EquipmentID"))):
            out.append({
                "id": _int(row.get("EquipmentID")),
                "name": self.text(row.get("EquipmentName")),
                "rarity": _rarity(row.get("Rarity")),
                "path": str(row.get("AvatarBaseType") or ""),
                "max_rank": _int(row.get("MaxRank"), 5),
                "max_promotion": _int(row.get("MaxPromotion"), 6),
                "release": row.get("Release"),
            })
        return out

    def relic_sets(self) -> list:
        rows = self.table(GAMECORE + "RelicSetConfig.bytes",
                          "RPG.GameCore.RelicSetConfigRow")
        out = []
        for row in sorted(rows, key=lambda r: _int(r.get("SetID"))):
            out.append({
                "id": _int(row.get("SetID")),
                "name": self.text(row.get("SetName")),
                "icon": str(row.get("SetIconPath") or ""),
            })
        return out

    def relics(self) -> list:
        rows = self.load_res("RelicConfig.json", "relic_config")
        out = []
        for row in sorted(rows, key=lambda r: _int(r.get("ID"))):
            out.append({
                "id": _int(row.get("ID")),
                "set_id": _int(row.get("SetID")),
                "type": str(row.get("Type") or ""),
                "rarity": _rarity(row.get("Rarity")),
                "max_level": _int(row.get("MaxLevel"), 15),
                "main_group": _int(row.get("MainAffixGroup")),
                "sub_group": _int(row.get("SubAffixGroup")),
            })
        return out

    def relic_main_affixes(self) -> list:
        rows = self.table(GAMECORE + "RelicMainAffixConfig.bytes",
                          "RPG.GameCore.RelicMainAffixConfigRow")
        return [{
            "group": _int(row.get("GroupID")),
            "affix_id": _int(row.get("AffixID")),
            "property": str(row.get("Property") or ""),
            "base": _fixed(row.get("BaseValue")),
            "level_add": _fixed(row.get("LevelAdd")),
        } for row in rows]

    def relic_sub_affixes(self) -> list:
        rows = self.table(GAMECORE + "RelicSubAffixConfig.bytes",
                          "RPG.GameCore.RelicSubAffixConfigRow")
        return [{
            "group": _int(row.get("GroupID")),
            "affix_id": _int(row.get("AffixID")),
            "property": str(row.get("Property") or ""),
            "base": _fixed(row.get("BaseValue")),
            "step_value": _fixed(row.get("StepValue")),
            "step_num": _int(row.get("StepNum")),
        } for row in rows]

    def monsters(self) -> list:
        rows = self.table(GAMECORE + "MonsterConfig.bytes",
                          "RPG.GameCore.MonsterRow")
        out = []
        for row in rows:
            monster_id = _int(row.get("MonsterID"))
            if not monster_id:
                continue
            out.append({
                "id": monster_id,
                "name": self.text(row.get("MonsterName")),
                "template": _int(row.get("MonsterTemplateID")),
                "elite_group": _int(row.get("EliteGroup")),
            })
        out.sort(key=lambda x: x["id"])
        return out

    def rogue_buffs(self) -> list:
        rows = self.table(EXCEL + "RogueBuff.bytes", "RPG.GameCore.RogueBuffRow")
        out = []
        for row in rows:
            buff_id = _int(row.get("MazeBuffID"))
            if not buff_id:
                continue
            out.append({
                "id": buff_id,
                "level": _int(row.get("MazeBuffLevel"), 1),
                "type": _int(row.get("RogueBuffType")),
                "category": str(row.get("RogueBuffCategory") or ""),
                "tag": _int(row.get("RogueBuffTag")),
            })
        out.sort(key=lambda x: (x["id"], x["level"]))
        return out

    def ex_ranks(self) -> dict:
        """特殊星魂（EX）：4.6.53 只有景元 / 丹恒·饮月 / 黄泉各一个。

        客户端表里的唯一痕迹是 `AvatarSkillConfig.RelatedExRankIDList`
        （只有这三个角色的被动技能有值）。客户端方法表也印证了这套系统：
        `AvatarRowData::GetExRankRowMap` / `CheckHasExRank` /
        `AvatarDataComponent::_SetupExRankConfigAbility`，以及协议
        `AvatarPathData.IGDEHGIKFJA` / `BattleAvatar.IGDEHGIKFJA`
        （packed u32 列表）——**列表由服务端下发**，客户端只负责按 ID 解析。

        返回 `{avatar_id: [ex_rank_id, ...]}`。
        """
        rows = self.table(GAMECORE + "AvatarSkillConfig.bytes",
                          "RPG.GameCore.AvatarSkillRow")
        out: dict[str, list] = {}
        for row in rows:
            related = row.get("RelatedExRankIDList") or []
            if not related:
                continue
            skill_id = _int(row.get("SkillID"))
            if not skill_id:
                continue
            avatar_id = skill_id // 100
            ids = []
            for item in related:
                if isinstance(item, dict):
                    value = next((v for v in item.values()
                                  if isinstance(v, (int, float))), 0)
                else:
                    value = item
                if int(value or 0):
                    ids.append(int(value))
            if ids:
                bucket = out.setdefault(str(avatar_id), [])
                for value in ids:
                    if value not in bucket:
                        bucket.append(value)
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 4.6.53 数据目录 catalog.json")
    ap.add_argument("--swh", type=Path, default=DEFAULT_SWH, help="SilverWolfHoney 根目录")
    ap.add_argument("--client", type=Path, default=DEFAULT_CLIENT, help="4.6.53 客户端根目录")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "catalog.json")
    ap.add_argument("--check", action="store_true", help="只统计，不写盘")
    args = ap.parse_args()

    t0 = time.time()
    b = Builder(args.swh, args.client)
    print("解析资源表 ...")
    catalog = {
        "meta": {
            "version": "4.6.53",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "client": str(args.client),
            "swh": str(args.swh),
        },
        "avatars": [],
        "avatars_by_id": {},
        "skill_points": {},
        "lightcones": [],
        "relic_sets": [],
        "relics": [],
        "relic_main_affixes": [],
        "relic_sub_affixes": [],
        "monsters": [],
        "rogue_buffs": [],
        "ex_ranks": {},
    }

    avatars = b.avatars()
    skills = b.skill_points()
    promotions = b.avatar_promotions()
    ranks = b.avatar_ranks()
    for a in avatars:
        a["promotions"] = sorted(promotions.get(a["id"], []),
                                 key=lambda x: x["promotion"])
        a["ranks"] = ranks.get(a["id"], [])
        a["skill_points"] = skills.get(str(a["id"]), [])
    catalog["avatars"] = avatars
    catalog["avatars_by_id"] = {str(a["id"]): a for a in avatars}
    catalog["skill_points"] = skills

    catalog["lightcones"] = b.lightcones()
    catalog["relic_sets"] = b.relic_sets()
    catalog["relics"] = b.relics()
    catalog["relic_main_affixes"] = b.relic_main_affixes()
    catalog["relic_sub_affixes"] = b.relic_sub_affixes()
    catalog["monsters"] = b.monsters()
    catalog["rogue_buffs"] = b.rogue_buffs()
    catalog["ex_ranks"] = b.ex_ranks()

    size = len(json.dumps(catalog, ensure_ascii=False).encode("utf-8"))
    print(f"\n角色 {len(catalog['avatars'])}（含行迹点的 "
          f"{sum(1 for a in catalog['avatars'] if a['skill_points'])}）")
    print(f"光锥 {len(catalog['lightcones'])} / 遗器 {len(catalog['relics'])} / "
          f"套装 {len(catalog['relic_sets'])}")
    print(f"主词条 {len(catalog['relic_main_affixes'])} / 副词条 "
          f"{len(catalog['relic_sub_affixes'])} / 怪物 {len(catalog['monsters'])} / "
          f"祝福 {len(catalog['rogue_buffs'])}")
    ex = catalog["ex_ranks"]
    names = {str(a["id"]): a["name"] for a in catalog["avatars"]}
    print("特殊星魂（EX）: " + "、".join(
        f"{names.get(pid, pid)}({pid})={ids}" for pid, ids in sorted(ex.items())))
    print(f"catalog 大小 {size / 1e6:.1f} MB，总用时 {time.time() - t0:.1f}s")

    if args.check:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    print(f"写出 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
