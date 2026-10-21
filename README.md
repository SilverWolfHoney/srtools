# SRTools 4.6.53（本地版）

改自[srtools.neonteam.dev](https://srtools.neonteam.dev/) 用于在浏览器里编辑《崩坏：星穹铁道》私服的
`freesr-data.json`（角色 / 光锥 / 遗器 / 战斗配置）。


## 快速开始

```bat
start.bat             :: 或 python serve.py
```

本地运行时，浏览器打开 **http://127.0.0.1:21100**

服务器部署时，开启21100端口，本机用浏览器打开**http://你的服务器IP:21100**

**注：服务器部署时无法使用连接私服功能，但是该问题并非无法解决，不过你需要拥有一个域名**

## 功能

| 页 | 内容 |
|---|---|
| **角色** | 头像列表 + 命途/元素筛选；等级/晋阶/星魂/EX 星魂；游戏风格行迹树；光锥；遗器 |
| **战斗配置** | 混沌回忆 / 虚构叙事 / 末日幻影 / 异相仲裁 / 自定义战斗，只取最近 4 期 |
| **工具** | 待完善 |
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
