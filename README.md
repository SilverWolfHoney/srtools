# SRTools 4.6.53（本地版）

[srtools.neonteam.dev](https://srtools.neonteam.dev/) 的离线替代品：在浏览器里编辑《崩坏：星穹铁道》私服的
`freesr-data.json`（角色 / 光锥 / 遗器 / 战斗配置），一键写回本机 SilverWolfHoney 私服。

- 数据是 **4.6.53** 的，从本机客户端的 `BakedConfig` Excel + `SilverWolfHoney/resources` 构建
- 完全本地（`127.0.0.1:21100`），不联网、不上传
- 输出的 `battle_config` 与原网站导出格式一致，私服 `gameserver/freesr.py` 直接解析并热重载

## 快速开始

```bat
start.bat             :: 或 python serve.py
```

浏览器打开 **http://127.0.0.1:21100**。默认存档 `E:\HSRBetaPS\SilverWolfHoney\freesr-data.json`，
可用 `python serve.py --profile <路径> --port 21101` 改。

## 功能

| 页 | 内容 |
|---|---|
| **角色** | 头像列表 + 命途/元素筛选；等级/晋阶/星魂/EX 星魂；游戏风格行迹树（10 个加强角色双形态）；光锥；遗器（主/副词条） |
| **战斗配置** | 混沌回忆 / 虚构叙事 / 末日幻影 / 异相仲裁 / 自定义怪，取最近 4 期，按期·层·节点选关并预览波次；切期/层/节点时下方「当前战斗配置」实时跟随；赛季效果用下拉选框（带描述）；点「应用为战斗配置」把 stage_id / 波次 / 祝福 / 回合数写进 `battle_config` |
| **工具** | 批量满级、补光锥、补遗器、存档信息 |
| **顶栏** | 上传/下载 `freesr-data.json`；「同步到私服」推送到 `http://127.0.0.1:21000` |

## 目录

```
srtools/
├─ serve.py              # 本地 Web 服务（标准库）
├─ build_catalog.py      # 构建 data/catalog.json
├─ fetch_battle_presets.py / fetch_avatars.py / fetch_trace_assets.py
├─ start.bat
├─ data/catalog.json     # 构建产物
├─ data/site/{nanoka,neonteam}/   # 挑战数据
└─ web/{index.html,app.js,style.css}
```

## 注意

- 只绑定 `127.0.0.1`，无鉴权，不要对外监听
- 找不到的旧 ID 会原样保留并给警告，不会静默丢弃
- 同步凭据取 `SilverWolfHoney/server_config.json` 的 `srtools` 段（本机默认为空）
