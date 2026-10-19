# SRTools 4.6.53（本地版）

[srtools.neonteam.dev](https://srtools.neonteam.dev/) 的**离线替代品**：在浏览器里编辑
《崩坏：星穹铁道》私服的 `freesr-data.json`（角色 / 光锥 / 遗器 / 战斗配置），
一键写回本机私服。

与在线站的区别：

* **数据是 4.6.53 的**：角色、光锥、遗器、词条、怪物、祝福全部从本机 4.6.53
  客户端的 `BakedConfig` Excel 表 + `SilverWolfHoney/resources` 生成，
  新角色 / 新光锥 / 新遗器自动出现在下拉框；
* **完全本地**：只有一个网页 + 标准库 HTTP 服务，不联网、不上传任何数据；
* **直接对接本机私服**：写出的 `freesr-data.json` 与 srtools 同构，
  `SilverWolfHoney/gameserver/freesr.py` 能直接解析；保存后私服的配置监视线程
  会热重载并推送给在线玩家。

## 快速开始

```bat
start.bat            :: 或者手动: python serve.py
```

然后浏览器打开 **http://127.0.0.1:21100**。

默认读写的存档是 `E:\HSRBetaPS\SilverWolfHoney\freesr-data.json`。
改路径：

```bat
python serve.py --profile D:\somewhere\freesr-data.json
python serve.py --port 21101
```

## 功能

| 页 | 能做什么 |
|---|---|
| **角色** | 角色列表带**头像缩略图**（来自 srtools 网站 CDN，100 个角色），支持按**命途 / 元素**下拉筛选；等级 / 晋阶 / 星魂 / 能量；**特殊星魂（EX）**（4.6.53 的景元 / 丹恒·饮月 / 黄泉各一个，独立于普通 6 星魂，勾选后写入 `data.ex_rank_id_list`）；行迹（每个锚点独立等级，可一键满级）；光锥（按命途分组选择、等级/叠影/晋阶）；遗器（4 部位、主词条、4 条副词条 + 档位/强化次数、一键自动补齐 4 件）；添加/移除角色；「全量添加」把 4.6.53 全部 124 个角色加入存档 |
| **战斗配置** | 回合数、关卡 ID、怪物波次（4.6.53 怪物 2779 只）、祝福 buff（沿用旧 id，也可从模拟宇宙祝福表挑选） |
| **工具** | 批量满级 / 补光锥 / 补遗器；存档信息 |
| **上传 / 下载 / 同步** | 顶栏三个按钮：**上传 freesr-data.json**（选择本地存档载入工具）、**下载 freesr-data.json**（当前编辑结果导出，弹出系统保存位置对话框）、**同步到私服**（弹出 Connect 弹窗：Provider + Server URL + Connect，验证后把当前配置推送到私服） |

## 数据来源与重建

`data/catalog.json` 是构建产物（约 1.9 MB），由 `build_catalog.py` 生成：

| catalog 段 | 来源 |
|---|---|
| 角色 / 行迹 / 遗器 | `SilverWolfHoney/resources/AvatarConfig.json`、`AvatarSkillTreeConfig.json`、`RelicConfig.json`（4.6.53） |
| 光锥 / 遗器套装 / 主副词条 / 晋阶 / 星魂 / 怪物 | 客户端 `F:\StarRail_4.6.53` 的 `BakedConfig/ExcelOutputGameCore/*.bytes` |
| 祝福 | `BakedConfig/ExcelOutput/RogueBuff.bytes` |
| **特殊星魂（EX）** | 客户端 `AvatarSkillConfig.RelatedExRankIDList`（只有景元 1204 / 丹恒·饮月 1213 / 黄泉 1308 的被动技能有值） |
| 中文名 | `SilverWolfHoney/dump_4.6.53/TextMap.json` |
| 角色头像 | `https://cdn.neonteam.dev/neonteam/assets/spriteoutput/avatarshopicon/avatar/<id>.webp`（下载到 `web/avatars/`，缺失的角色显示文字占位） |

> 头像资源（游戏版权）不随仓库分发：克隆后运行 `python fetch_avatars.py` 即可下载到
> `web/avatars/`；缺失的角色会自动显示文字占位，不影响编辑功能。

客户端更新或换目录后重新生成：

```bat
python build_catalog.py                 :: 默认路径
python build_catalog.py --check         :: 只看统计
python build_catalog.py --client D:\StarRail_4.6.54 --swh E:\HSRBetaPS\SilverWolfHoney
```

> 依赖 `SilverWolfHoney/tools/hsr_design.py` 与 `dump_4.6.53/data.json`（IL2CPP 类型
> schema）。Excel 表在客户端里走 `ExcelOutputGameCore/` 路径，不是 `ExcelOutput/`。

## 与私服配合

1. **下载后手动放回**：点「下载 freesr-data.json」把存档导出到任意位置，再放回私服的
   `freesr-data.json`；私服 `gameserver/main.py` 里的配置监视线程发现文件变化后自动
   重载并向在线玩家推送，也可以在游戏里敲 `/sync`。
2. **同步到私服**：点顶栏「同步到私服」弹出「连接私服」弹窗，选服务端类型
   （SilverWolfHoney / 自定义）并填服务器地址（默认 `http://127.0.0.1:21000`），
   点「连接」通过后弹窗会变成「● 已连接 + 断开连接 + 同步」；之后编辑完成点
   「同步」才把当前配置推给私服。账号密码取 `SilverWolfHoney/server_config.json`
   的 `srtools` 段：

   ```json
   { "srtools": { "username": "your-user", "password": "your-pass" } }
   ```

   空凭据时私服端也留空即可（本机默认如此）。

## 目录

```
srtools/
├─ serve.py            # 本地 Web 服务（标准库，默认 127.0.0.1:21100）
├─ build_catalog.py    # 从 4.6.53 客户端/资源表构建 data/catalog.json
├─ start.bat           # 双击启动
├─ data/catalog.json   # 构建产物（角色/光锥/遗器/词条/怪物/祝福 + 中文名）
└─ web/
   ├─ index.html
   ├─ app.js
   └─ style.css
```

## 注意

* 服务只绑定 `127.0.0.1`，没有登录鉴权，**不要**改成对外监听；
* `internal_uid` 由工具按当前存档递增分配，保证光锥/遗器在客户端背包里的
  unique_id 不撞车；导入旧存档时会沿用原 uid；
* 从 4.6.53 数据目录里找不到的旧 ID 会原样保留（保存时给出警告，私服侧同样会
  过滤），不会静默丢弃你的数据。
