#!/usr/bin/env python3
"""SRTools 4.6.53 本地版 —— 在浏览器里编辑《崩坏：星穹铁道》私服的
`freesr-data.json`（角色 / 光锥 / 遗器 / 战斗配置），并一键同步到本机私服。

设计目标：

* **零第三方依赖**：只用 Python 标准库 + 原生 HTML/JS/CSS；
* **与现有私服完全兼容**：写出的 `freesr-data.json` 与 srtools 站点同构，
  `SilverWolfHoney/gameserver/freesr.py` 能直接解析；
* **数据是 4.6.53**：`data/catalog.json` 由 `build_catalog.py` 从本机
  4.6.53 客户端的 BakedConfig Excel 表 + `resources/` 生成。

用法：

    python serve.py                    # 打开 http://127.0.0.1:21100
    python serve.py --port 21101
    python serve.py --profile D:\\other\\freesr-data.json

同步有两种方式（界面上分别对应「保存」与「同步」）：

1. 保存：直接原子写 `freesr-data.json`。私服的配置监视线程会热重载并
   推送给在线玩家（`SilverWolfHoney/gameserver/main.py`）；
2. 同步：POST `http://127.0.0.1:21000/srtools`，与 srtools 网页端的
   "Connect PS" 走同一条端点（需要 `server_config.json` 里配好账号密码）。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CATALOG = ROOT / "data" / "catalog.json"
DEFAULT_SWH = Path(r"E:\HSRBetaPS\SilverWolfHoney")
DISPATCH = "http://127.0.0.1:21000"
MAX_BODY = 64 * 1024 * 1024  # 64 MB


class App:
    """进程级状态：路径配置 + 已载入的 catalog。"""

    def __init__(self, swh: Path, profile: Path | None):
        self.swh = swh
        self.profile = profile or (swh / "freesr-data.json")
        self.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.layout_file = ROOT / "data" / "trace_layout.json"
        self._known = {
            "avatars": {int(a["id"]) for a in self.catalog["avatars"]},
            "lightcones": {int(x["id"]) for x in self.catalog["lightcones"]},
            "relics": {int(x["id"]) for x in self.catalog["relics"]},
        }

    def catalog_live(self) -> dict:
        """catalog，行迹树布局以 data/trace_layout.json 为准（支持手动调整后热更新）。"""
        if self.layout_file.is_file() and isinstance(self.catalog.get("trace_trees"), dict):
            try:
                self.catalog["trace_trees"]["layout"] = json.loads(
                    self.layout_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return self.catalog

    def save_trace_layout(self, payload: dict) -> dict:
        """保存手动调整的行迹节点位置：{path: {"Point01": {"cx": 31, "cy": 55}}}。"""
        path = str(payload.get("path") or "").strip()
        points = payload.get("points") or {}
        if not path or not isinstance(points, dict):
            raise ValueError("缺少 path / points")
        layout: dict = {}
        if self.layout_file.is_file():
            try:
                layout = json.loads(self.layout_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                layout = {}
        cur = layout.setdefault(path, {})
        saved = 0
        for anchor, pos in points.items():
            if not isinstance(pos, dict):
                continue
            try:
                cx = round(float(pos.get("cx")), 2)
                cy = round(float(pos.get("cy")), 2)
            except (TypeError, ValueError):
                continue
            cur[str(anchor)] = {"cx": cx, "cy": cy}
            saved += 1
        self.layout_file.write_text(
            json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": path, "saved": saved,
                "file": str(self.layout_file)}


    # ---------------------------------------------------------------- 读
    def profile_raw(self) -> dict:
        if not self.profile.is_file():
            return {"avatars": {}, "lightcones": [], "relics": [], "battle_config": {}}
        return json.loads(self.profile.read_text(encoding="utf-8"))

    def server_config(self) -> dict:
        try:
            return json.loads((self.swh / "server_config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def state(self) -> dict:
        cfg = self.server_config()
        st = cfg.get("srtools") or {}
        raw = self.profile_raw()
        return {
            "catalog": {
                "version": (self.catalog.get("meta") or {}).get("version"),
                "generated_at": (self.catalog.get("meta") or {}).get("generated_at"),
                "avatars": len(self.catalog["avatars"]),
                "lightcones": len(self.catalog["lightcones"]),
                "relics": len(self.catalog["relics"]),
            },
            "profile": {
                "path": str(self.profile),
                "exists": self.profile.is_file(),
                "avatars": len(raw.get("avatars") or {}),
                "lightcones": len(raw.get("lightcones") or []),
                "relics": len(raw.get("relics") or []),
                "mtime": (datetime.fromtimestamp(self.profile.stat().st_mtime)
                          .isoformat(timespec="seconds") if self.profile.is_file() else None),
            },
            "sync": {
                "endpoint": DISPATCH + "/srtools",
                "username_set": bool(st.get("username")),
                "password_set": bool(st.get("password")),
            },
        }

    # ---------------------------------------------------------------- 写
    def validate(self, data: dict) -> list[str]:
        """返回警告列表；结构错误抛 ValueError。"""
        if not isinstance(data, dict):
            raise ValueError("数据必须是 JSON 对象")
        for key, kind in (("avatars", dict), ("lightcones", list), ("relics", list)):
            if not isinstance(data.get(key), kind):
                raise ValueError(f"缺少或类型错误: {key}")

        warnings: list[str] = []
        unknown = set()
        for key, item in (data.get("avatars") or {}).items():
            try:
                avatar_id = int(item.get("avatar_id") or key)
            except (TypeError, ValueError):
                raise ValueError(f"角色 id 非法: {key!r}")
            if avatar_id not in self._known["avatars"]:
                unknown.add(f"角色 {avatar_id}")
            if int(item.get("level") or 0) not in range(1, 81):
                warnings.append(f"角色 {avatar_id} 等级 {item.get('level')} 超出 1-80")
            data_block = item.get("data") or {}
            if int(data_block.get("rank") or 0) > 6:
                warnings.append(f"角色 {avatar_id} 星魂超过 6")
        for lc in data.get("lightcones") or []:
            if int(lc.get("item_id") or 0) not in self._known["lightcones"]:
                unknown.add(f"光锥 {lc.get('item_id')}")
            if int(lc.get("rank") or 1) > 5:
                warnings.append(f"光锥 {lc.get('item_id')} 叠影超过 5")
        for relic in data.get("relics") or []:
            if int(relic.get("relic_id") or 0) not in self._known["relics"]:
                unknown.add(f"遗器 {relic.get('relic_id')}")
            if not 0 <= int(relic.get("level") or 0) <= 15:
                warnings.append(f"遗器 {relic.get('relic_id')} 等级超出 0-15")
            for sub in relic.get("sub_affixes") or []:
                if not 0 <= int(sub.get("count") or 0) <= 5:
                    warnings.append(
                        f"遗器 {relic.get('relic_id')} 副词条档位 {sub.get('count')} 超出 0-5")
        if unknown:
            sample = "、".join(sorted(unknown)[:10])
            warnings.append(f"有 {len(unknown)} 个 ID 不在 4.6.53 数据目录里：{sample}")
        return warnings

    def save(self, data: dict) -> dict:
        warnings = self.validate(data)
        self.profile.parent.mkdir(parents=True, exist_ok=True)
        # 不生成 .bak 备份（用户不需要；写盘用 tmp + replace 保证原子性）
        tmp = self.profile.with_name(self.profile.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.profile)
        return {
            "ok": True,
            "path": str(self.profile),
            "warnings": warnings,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }

    def sync(self, data: dict) -> dict:
        """把数据推给正在运行的 dispatch（等价于 srtools 的 Connect PS）。"""
        cfg = self.server_config()
        st = cfg.get("srtools") or {}
        username, password = str(st.get("username") or ""), str(st.get("password") or "")
        if not username or not password:
            return {"ok": False,
                    "message": "server_config.json 的 srtools.username/password 为空 —— "
                               "先把保存好的数据交给私服（保存即可热重载），"
                               "或填好凭据后再用「同步」"}
        body = json.dumps({"username": username, "password": password,
                           "data": data}).encode("utf-8")
        req = urllib.request.Request(
            DISPATCH + "/srtools", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", "replace")
                return {"ok": resp.status == 200, "status": resp.status, "response": text}
        except urllib.error.HTTPError as exc:
            return {"ok": False, "status": exc.code,
                    "message": exc.read().decode("utf-8", "replace")}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False,
                    "message": f"连不上 dispatch（{DISPATCH}）：{exc} —— "
                               f"先启动 python main.py，或直接用「保存」"}

    def connect(self, payload: dict) -> dict:
        """连接私服（等价 srtools 网站的 Connect PS）。

        1) 用用户填的地址 + 账号密码先做一次握手（POST /srtools 不带 data）：
           200 = 连接成功、401 = 凭据错误、网络错误 = 私服没启动；
        2) 握手成功后，如果请求里带了当前编辑的数据，就把它推给私服。
        """
        url = str(payload.get("url") or DISPATCH).strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("私服地址必须以 http:// 或 https:// 开头")
        endpoint = url + "/srtools"
        username = str(payload.get("username") or "")
        password = str(payload.get("password") or "")
        if not username and not password:
            # 网页端 Connect PS 不填账号密码：从私服 server_config.json 的 srtools 段取
            st = self.server_config().get("srtools") or {}
            username = str(st.get("username") or "")
            password = str(st.get("password") or "")
        data = payload.get("data")

        def post(body: dict):
            raw = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                endpoint, data=raw, method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")

        # 1) 握手
        try:
            status, text = post({"username": username, "password": password})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 401:
                return {"ok": False, "stage": "auth", "status": 401,
                        "message": "认证失败：用户名/密码与私服 server_config.json 的 "
                                   "srtools 段不一致"}
            return {"ok": False, "stage": "handshake", "status": exc.code,
                    "message": detail or f"HTTP {exc.code}"}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "stage": "network",
                    "message": f"连不上 {endpoint}：{exc} —— 先启动私服"}
        if status != 200:
            return {"ok": False, "stage": "handshake", "status": status,
                    "message": text or f"HTTP {status}"}

        result = {"ok": True, "endpoint": endpoint, "synced": False,
                  "message": f"已连接 {endpoint}"}

        # 2) 推送当前编辑的数据
        if data is not None:
            try:
                warnings = self.validate(data)
            except ValueError as exc:
                result.update(ok=False, synced=False, stage="validate",
                              message=f"数据校验失败：{exc}")
                return result
            try:
                status2, text2 = post({"username": username, "password": password,
                                       "data": data})
                result["synced"] = status2 == 200
                result["status"] = status2
                result["warnings"] = warnings
                if not result["synced"]:
                    result.update(ok=False, stage="push",
                                  message=text2 or f"HTTP {status2}")
                else:
                    result["message"] = (f"已连接 {endpoint}，并同步 "
                                         f"{len((data.get('avatars') or {}))} 个角色"
                                         f" / {len(data.get('lightcones') or [])} 个光锥")
            except urllib.error.HTTPError as exc:
                result.update(ok=False, synced=False, stage="push", status=exc.code,
                              message=exc.read().decode("utf-8", "replace"))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                result.update(ok=False, synced=False, stage="push", message=str(exc))
        return result


APP: App


class Handler(BaseHTTPRequestHandler):
    server_version = "SRTools/4.6.53"

    def log_message(self, fmt, *args):  # 安静一点，只打印 API 调用
        if args and str(args[0]).startswith("API"):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ------------------------------------------------------------ 工具
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("空请求体")
        if length > MAX_BODY:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------ GET
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                return self._json(200, APP.state())
            if path == "/api/catalog":
                return self._json(200, APP.catalog_live())
            if path == "/api/profile":
                return self._json(200, {"ok": True, "data": APP.profile_raw(),
                                        "path": str(APP.profile)})
            return self._static(path)
        except Exception as exc:  # noqa: BLE001 - 统一 500，前端显示原因
            return self._json(500, {"ok": False, "message": f"{type(exc).__name__}: {exc}"})

    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB / rel).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            return self._json(404, {"ok": False, "message": "not found"})
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        return self._send(200, target.read_bytes(), ctype)

    # ------------------------------------------------------------ POST
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/save":
                body = self._body()
                data = body.get("data")
                return self._json(200, APP.save(data))
            if path == "/api/sync":
                body = self._body()
                return self._json(200, APP.sync(body.get("data")))
            if path == "/api/connect":
                body = self._body()
                return self._json(200, APP.connect(body))
            if path == "/api/trace-layout":
                body = self._body()
                return self._json(200, APP.save_trace_layout(body))
            return self._json(404, {"ok": False, "message": "not found"})
        except ValueError as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"ok": False, "message": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    ap = argparse.ArgumentParser(description="SRTools 4.6.53 本地版")
    ap.add_argument("--swh", type=Path, default=DEFAULT_SWH,
                    help="SilverWolfHoney 根目录（读 server_config 凭据）")
    ap.add_argument("--profile", type=Path, default=None,
                    help="freesr-data.json 路径（默认 <swh>/freesr-data.json）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=21100)
    args = ap.parse_args()

    global APP
    if not CATALOG.is_file():
        print(f"缺少 {CATALOG} —— 先运行: python build_catalog.py", file=sys.stderr)
        return 2
    APP = App(args.swh, args.profile)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SRTools 4.6.53: http://{args.host}:{args.port}/")
    print(f"  数据目录: {CATALOG}（{APP.state()['catalog']['version']}，"
          f"{len(APP.catalog['avatars'])} 角色 / {len(APP.catalog['lightcones'])} 光锥）")
    print(f"  存档文件: {APP.profile}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
