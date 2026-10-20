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
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SWH = Path(r"E:\HSRBetaPS\SilverWolfHoney")
DEFAULT_CLIENT = Path(r"F:\StarRail_4.6.53")
GAMECORE = "ExcelOutputGameCore/"

# ---------------------------------------------------------------- xxh64
# 客户端 TextMap 的 Hash64 = xxh64(key)，用于把 SkillPointName_* 翻译成中文

_MASK = 0xFFFFFFFFFFFFFFFF
_P1 = 0x9E3779B185EBCA87
_P2 = 0xC2B2AE3D27D4EB4F
_P3 = 0x165667B19E3779F9
_P4 = 0x85EBCA77C2B2AE63
_P5 = 0x27D4EB2F165667C5

# 技能点（锚点 1-5）没有 PointName，按类型给固定名字
ANCHOR_NAME = {1: "普通攻击", 2: "战技", 3: "终结技", 4: "天赋", 5: "秘技"}


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & _MASK


def _round(acc: int, inp: int) -> int:
    return (_rotl((acc + inp * _P2) & _MASK, 31) * _P1) & _MASK


def _merge(acc: int, val: int) -> int:
    acc ^= _round(0, val)
    return (acc * _P1 + _P4) & _MASK


def xxh64(data: bytes, seed: int = 0) -> int:
    n = len(data)
    pos = 0
    if n >= 32:
        v1 = (seed + _P1 + _P2) & _MASK
        v2 = (seed + _P2) & _MASK
        v3 = seed & _MASK
        v4 = (seed - _P1) & _MASK
        while pos + 32 <= n:
            v1 = _round(v1, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v2 = _round(v2, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v3 = _round(v3, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v4 = _round(v4, struct.unpack_from("<Q", data, pos)[0]); pos += 8
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _MASK
        for v in (v1, v2, v3, v4):
            h = _merge(h, v)
    else:
        h = (seed + _P5) & _MASK

    h = (h + n) & _MASK
    while pos + 8 <= n:
        h ^= _round(0, struct.unpack_from("<Q", data, pos)[0])
        h = (_rotl(h, 27) * _P1 + _P4) & _MASK
        pos += 8
    if pos + 4 <= n:
        h ^= (struct.unpack_from("<I", data, pos)[0] * _P1) & _MASK
        h = (_rotl(h, 23) * _P2 + _P3) & _MASK
        pos += 4
    while pos < n:
        h ^= (data[pos] * _P5) & _MASK
        h = (_rotl(h, 11) * _P1) & _MASK
        pos += 1

    h ^= h >> 33
    h = (h * _P2) & _MASK
    h ^= h >> 29
    h = (h * _P3) & _MASK
    h ^= h >> 32
    return h

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


def _clean_text(text: str) -> str:
    """去掉客户端富文本标签（<unbreak>、<color=...> 等），并把 \\n 转成真换行。"""
    import re as _re
    out = _re.sub(r"<[^>]+>", "", text or "")
    return out.replace("\\n", "\n")


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
            h32 = ident.get("Hash")
            if h32 is not None:
                self.text_map[int(h32)] = row.get("Text") or ""
        print(f"TextMap: {len(self.text_map)} 条，{time.time() - t:.1f}s")

    # ---------------------------------------------------------------- 工具
    def text(self, value) -> str:
        """TextID -> 本地化文本（去富文本标签）。"""
        if isinstance(value, dict):
            for key in ("Hash64", "Hash"):
                h = value.get(key)
                if h is not None and int(h) in self.text_map:
                    return _clean_text(self.text_map[int(h)])
            return ""
        if isinstance(value, int) and value in self.text_map:
            return _clean_text(self.text_map[value])
        return _clean_text(str(value or ""))

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
                raw_name = item.get("name") or ""
                if raw_name:
                    # PointName 是 TextMap key（如 SkillPointName_1001201），xxh64 后查表
                    item["name_text"] = self.text(xxh64(raw_name.encode())) or ""
                else:
                    item["name_text"] = ANCHOR_NAME.get(item["anchor"], "")
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

    def battle_presets(self) -> dict:
        """4 玩法最近 4 期（数据以 nanoka.cc 4.6.53 为准）。

        nanoka 数据（data/site/nanoka/{maze,story,boss,peak}/<期>.json）：
        - maze/story/boss：每层有 event_id_list1（第一节点）、event_id_list2（第二节点）、
          event_id_list（第三节点=星启，含 invasion 贪饕污染）
        - peak：pre_level（关1-3）+ boss_level（关4）+ boss_config（绝境），带 tag_list/invasion
        关卡 buff（turbulence）nanoka 只有文本，buff id 从客户端 ChallengeMazeConfig 的
        MazeBuffID 按层 ID 合并（同版本 4.6.53）。
        """
        site = ROOT / "data" / "site" / "nanoka"

        # 客户端 turbulence buff id（按层 ID）
        twist: dict[int, int] = {}
        try:
            for r in self.table("ExcelOutput/ChallengeMazeConfig.bytes",
                                "RPG.GameCore.ChallengeMazeConfigRow"):
                rid = _int(r.get("ID"))
                bid = _int(r.get("MazeBuffID"))
                if rid and bid:
                    twist[rid] = bid
        except (OSError, KeyError, ValueError):
            twist = {}

        # 客户端 MazeBuff 表：id -> 名称/描述（关卡效果 _BindingMazeBuff 用）
        maze_buffs: dict[int, dict] = {}
        try:
            for r in self.table("ExcelOutputGameCore/MazeBuff.bytes",
                                "RPG.GameCore.MazeBuffRow"):
                bid = _int(r.get("ID"))
                if bid:
                    maze_buffs[bid] = {
                        "name": self.text(r.get("BuffName")),
                        "desc": self.text(r.get("BuffDesc")) or self.text(r.get("BuffDescBattle")),
                        "param": [_fixed(x.get("Value")) for x in (r.get("ParamList") or [])
                                  if isinstance(x, dict)],
                        # 战斗内挂载方式：StageAbilityBeforeCharacterBorn 类需要关卡 ability，
                        # 花萼那种普通战斗里下发会卡（客户端挂不上）；无绑定 / AfterCharacterBorn 可安全下发
                        "bind_type": str(r.get("InBattleBindingType") or ""),
                        "bind_key": self.text(r.get("InBattleBindingKey")),
                    }
        except (OSError, KeyError, ValueError):
            maze_buffs = {}

        buff_id_by_name: dict[str, int] = {}
        for _bid, _info in maze_buffs.items():
            if _info.get("name"):
                buff_id_by_name.setdefault(_info["name"], _bid)

        def fmt_desc(text, params) -> str:
            """把 #1[i]% / #1[i] 占位替换成实际数值。"""
            out = str(text or "")
            for i, v in enumerate(params or [], 1):
                try:
                    num = _fixed(v)
                except (TypeError, ValueError):
                    num = 0.0
                out = out.replace(f"#{i}[i]%", f"{num * 100:g}%")
                out = out.replace(f"#{i}[i]", f"{num:g}")
            return out

        def stage_buffs_of(ev) -> list:
            """从 stage_config_data 里取 _BindingMazeBuff（关卡效果）。"""
            out = []
            for item in (ev.get("stage_config_data") or []):
                vals = list(item.values())
                if "_BindingMazeBuff" not in vals:
                    continue
                i = vals.index("_BindingMazeBuff")
                if i + 1 >= len(vals):
                    continue
                bid = _int(vals[i + 1])
                if bid and bid in maze_buffs:
                    item_out = {"id": bid, "name": maze_buffs[bid]["name"],
                                "desc": fmt_desc(maze_buffs[bid]["desc"],
                                                 maze_buffs[bid].get("param"))}
                    if item_out not in out:
                        out.append(item_out)
            return out

        def wave_list(monster_list) -> list:
            out = []
            for m in monster_list or []:
                wave = [int(m.get(k) or 0) for k in
                        ("monster0", "monster1", "monster2", "monster3", "monster4")]
                out.append([x for x in wave if x])
            return [w for w in out if w]

        def wave_from_infinite(inf) -> list:
            """infinite_list: {wave_id: {monster_group_id_list}} -> 每波去重后的怪列表。"""
            if not isinstance(inf, dict):
                return []
            waves = []
            for wid in sorted(inf.keys(), key=lambda x: int(x)):
                ids = []
                for mid in (inf[wid].get("monster_group_id_list") or []):
                    try:
                        mid = int(mid)
                    except (TypeError, ValueError):
                        continue
                    if mid and mid not in ids:
                        ids.append(mid)
                if ids:
                    waves.append(ids)
            return waves

        def event_of(events) -> dict:
            return (events or [{}])[0]

        def invasion_of(inv) -> dict | None:
            if not inv:
                return None
            return {
                "level": int(inv.get("level") or 0),
                "desc": _clean_text(str(inv.get("desc") or "")),
                "buff": int(inv.get("maze_buff_id") or 0),
                "params": inv.get("maze_buff_param") or [],
                "monsters": [int(m.get("monster_id")) for m in (inv.get("monster_list") or [])
                             if m.get("monster_id")],
            }

        def floor_of(lv, mode: str, season=None, stage_extra=None, use_twist=False,
                     season_groups=None, use_infinite=False) -> dict:
            ev1 = event_of(lv.get("event_id_list1"))
            ev2 = event_of(lv.get("event_id_list2"))
            ev3 = event_of(lv.get("event_id_list"))
            invasion_top = invasion_of(ev1.get("invasion"))
            invasion_bot = invasion_of(ev2.get("invasion"))
            invasion_tierce = invasion_of(ev3.get("invasion"))
            inv = invasion_tierce or invasion_top or invasion_bot or None
            lid = int(lv.get("id") or 0)
            buff_ids = []
            buff_infos = []
            if use_twist and twist.get(lid):   # 混沌专有 Buff（记忆紊流）
                bid = twist[lid]
                info = maze_buffs.get(bid) or {}
                buff_ids.append(bid)
                buff_infos.append({"id": bid,
                                   "name": info.get("name", ""),
                                   "desc": fmt_desc(info.get("desc", ""), info.get("param"))})
            stage_buffs = []
            for ev in (ev1, ev2):
                for b in stage_buffs_of(ev):
                    if b not in stage_buffs:
                        stage_buffs.append(b)
            for b in (stage_extra or []):
                if not any(x.get("name") == b.get("name") for x in stage_buffs):
                    stage_buffs.append(b)
            top_w = ((wave_from_infinite(lv.get("infinite_list1")) if use_infinite else [])
                     or wave_list(ev1.get("monster_list")))
            bot_w = ((wave_from_infinite(lv.get("infinite_list2")) if use_infinite else [])
                     or wave_list(ev2.get("monster_list")))
            # 波次严格用关卡自己的 monster_list / infinite_list，不额外补 npc_monster_id_list
            # （nanoka 页面 WAVE 里也不显示它，补进去会多出一只怪）
            return {
                "floor": lid,
                "name": _clean_text(str(lv.get("name") or "")),
                "top": top_w,
                "bot": bot_w,
                "tierce": wave_from_infinite(lv.get("infinite_list")) if use_infinite else []
                          or wave_list(ev3.get("monster_list")),
                "has_tierce": bool(ev3.get("monster_list")),
                "stage_top": int(ev1.get("stage_id") or 0),
                "stage_bot": int(ev2.get("stage_id") or 0),
                "stage_tierce": int(ev3.get("stage_id") or 0),
                "invasion": inv,
                "invasion_top": invasion_top,
                "invasion_bot": invasion_bot,
                "invasion_tierce": invasion_tierce,
                "buff_ids": buff_ids,
                "buff_infos": buff_infos,
                "stage_buffs": stage_buffs,
                "season_buffs": season or [],
                "season_groups": season_groups or [],
                "cycle": int(lv.get("countdown") or 0) or 30,
            }

        def floors_of(levels, season=None, stage_extra=None, use_twist=False,
                     season_groups=None, use_infinite=False) -> list:
            """把 pre_id 节点3 层（如 5613=其十二的节点3）合并进前置层的 tierce/invasion。"""
            extra: dict[int, dict] = {}
            ordered = []
            for lv in levels:
                pre = int(lv.get("pre_id") or 0)
                if pre:
                    extra[pre] = lv
                else:
                    ordered.append(lv)
            out = []
            for lv in ordered:
                f = floor_of(lv, "maze", season, stage_extra, use_twist, season_groups, use_infinite)
                node3 = extra.get(f["floor"])
                if node3:
                    ev3 = event_of(node3.get("event_id_list"))
                    tierce = wave_from_infinite(node3.get("infinite_list")) if use_infinite else []
                    if not tierce:
                        tierce = wave_list(ev3.get("monster_list"))
                    if not tierce:
                        tierce = [[int(x) for x in (node3.get("npc_monster_id_list") or []) if x]]
                    if tierce:
                        f["tierce"] = tierce
                        f["has_tierce"] = True
                        f["stage_tierce"] = int(ev3.get("stage_id") or 0)
                    inv3 = invasion_of(ev3.get("invasion"))
                    if inv3:
                        f["invasion"] = inv3
                        f["invasion_tierce"] = inv3
                out.append(f)
            return out

        out = {}

        # 混沌（maze：list of 层）
        moc = {"name": "混沌回忆", "periods": []}
        out["moC"] = moc
        for f in sorted((site / "maze").glob("*.json"), key=lambda x: int(x.stem))[-4:]:
            data = json.loads(f.read_text(encoding="utf-8"))
            pname = ""
            for lv in data:
                if not pname:
                    pname = _clean_text(str(lv.get("group_name") or ""))
            moc["periods"].append({"period": int(f.stem), "name": pname,
                                   "floors": floors_of(data, use_twist=True)})

        # 虚构（story）/ 末日（boss）：dict.level
        for key, label, dname in (("pureFiction", "虚构叙事", "story"),
                                  ("apocalypticShadow", "末日幻影", "boss")):
            item = {"name": label, "periods": []}
            out[key] = item
            for f in sorted((site / dname).glob("*.json"), key=lambda x: int(x.stem))[-4:]:
                data = json.loads(f.read_text(encoding="utf-8"))
                buff = data.get("buff") or {}

                def norm(items) -> list:
                    out = []
                    for b in (items or []):
                        if b.get("name"):
                            nm = _clean_text(str(b["name"]))
                            out.append({"id": buff_id_by_name.get(nm, 0),
                                        "name": nm,
                                        "desc": fmt_desc(_clean_text(str(b.get("desc") or "")),
                                                         b.get("param")),
                                        "param": b.get("param") or []})
                    return out

                if dname == "story":
                    # 虚构：option = 玩家可选 Buff，sub_option = 固定关卡效果
                    season = norm(data.get("option"))
                    stage_extra = norm(data.get("sub_option"))
                    season_groups = []
                else:
                    # 末日：buff_list1/2/3 = 三路（节点1/2/3）各自的三选一；buff = 关卡效果
                    season_groups = [norm(data.get("buff_list1")),
                                     norm(data.get("buff_list2")),
                                     norm(data.get("buff_list3"))]
                    season = [b for g in season_groups for b in g]
                    stage_extra = norm([buff]) if buff.get("name") else []
                item["periods"].append({
                    "period": int(f.stem),
                    "name": _clean_text(str(data.get("name") or "")),
                    "buff": {
                        "name": _clean_text(str(buff.get("name") or "")),
                        "desc": _clean_text(str(buff.get("desc") or "")),
                        "param": buff.get("param") or [],
                    },
                    "floors": floors_of(data.get("level") or [], season, stage_extra,
                                        season_groups=season_groups,
                                        use_infinite=(dname == "story")),
                })

        # 异相仲裁（peak：pre_level + boss_level + boss_config）
        periods = []
        for f in sorted((site / "peak").glob("*.json"), key=lambda x: int(x.stem))[-4:]:
            data = json.loads(f.read_text(encoding="utf-8"))
            levels = list(data.get("pre_level") or [])
            boss_id = 0
            boss_buffs = []
            if data.get("boss_config"):
                boss_buffs = [
                    {"id": int(b.get("id") or 0),
                     "name": _clean_text(str(b.get("name") or "")),
                     "desc": fmt_desc(_clean_text(str(b.get("desc") or "")), b.get("param")),
                     "param": b.get("param") or []}
                    for b in (data["boss_config"].get("buff_list") or []) if b.get("name")
                ]
            if data.get("boss_level"):
                levels.append(data["boss_level"])
                boss_id = int(data["boss_level"].get("id") or 0)
            if data.get("boss_config"):
                bc = dict(data["boss_config"])
                if not bc.get("id"):
                    bc["id"] = boss_id + 1
                if not bc.get("name"):
                    bc["name"] = bc.get("hard_name") or "绝境"
                levels.append(bc)
            floors = []
            for lv in levels:
                ev = event_of(lv.get("event_id_list"))
                floors.append({
                    "floor": int(lv.get("id") or 0),
                    "name": _clean_text(str(lv.get("name") or "")),
                    "waves": wave_list(ev.get("monster_list")),
                    "tag_buffs": [
                        {"id": int(t.get("id") or 0),
                         "name": _clean_text(str(t.get("name") or "")),
                         "desc": fmt_desc(_clean_text(str(t.get("desc") or "")), t.get("param")),
                         "param": t.get("param") or []}
                        for t in (lv.get("tag_list") or []) if t.get("id")
                    ],
                    "season_buffs": (boss_buffs
                                     if (str(lv.get("name") or "").startswith("将杀王棋")
                                         or lv.get("hard_name")) else []),
                    "invasion": invasion_of(ev.get("invasion")),
                    "stage": int(ev.get("stage_id") or 0),
                })
            periods.append({"period": int(f.stem), "name": _clean_text(str(data.get("name") or "")),
                            "floors": floors})
        out["anomalyArbitration"] = {"name": "异相仲裁", "periods": periods}
        # 每个 buff 在战斗内的挂载方式：StageAbilityBeforeCharacterBorn 需要关卡 ability，
        # 普通战斗（花萼/大世界）里下发会卡，前端应用时据此过滤
        out["buff_bind"] = {
            str(k): {"type": v.get("bind_type") or "", "key": v.get("bind_key") or ""}
            for k, v in maze_buffs.items() if v.get("bind_type")
        }
        return out

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

    # 行迹树（命途布局 + 每角色节点/连线/图标），由 fetch_trace_assets.py 生成
    trace_file = ROOT / "data" / "trace_trees.json"
    if trace_file.is_file():
        catalog["trace_trees"] = json.loads(trace_file.read_text(encoding="utf-8"))

    catalog["lightcones"] = b.lightcones()
    catalog["relic_sets"] = b.relic_sets()
    catalog["relics"] = b.relics()
    catalog["relic_main_affixes"] = b.relic_main_affixes()
    catalog["relic_sub_affixes"] = b.relic_sub_affixes()
    catalog["monsters"] = b.monsters()
    catalog["battle_presets"] = b.battle_presets()
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
