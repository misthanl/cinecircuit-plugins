# CineCircuit 插件库

本仓库维护 CineCircuit 的独立插件源码和可安装 ZIP。每个插件独立发布，通过宿主 SDK 使用媒体、存储、站点、通知及任务能力。

## 插件列表

| 插件 | 功能 |
| --- | --- |
| [站点签到管理](cinecircuit_plugins/auto_signin/README.md) | 自动登录并签到配置的 PT 站点 |
| [站点刷流](cinecircuit_plugins/brush_flow/README.md) | 根据站点与规则选种、下载和删种 |
| [演职员资料完善](cinecircuit_plugins/cast_profile_enricher/README.md) | 补全人物中文姓名、简介、角色与头像 |
| [CookieCloud 站点同步](cinecircuit_plugins/cookiecloud/README.md) | 同步浏览器 Cookie，验证并更新站点 |
| [豆瓣榜追更](cinecircuit_plugins/douban_rank/README.md) | 根据榜单与筛选条件添加影视订阅 |
| [猫眼榜追更](cinecircuit_plugins/maoyan_rank/README.md) | 根据猫眼影视榜单添加订阅 |
| [媒体库视觉工坊](cinecircuit_plugins/media_cover_generator/README.md) | 生成并上传媒体库静态或动态封面 |
| [网盘回收站清理](cinecircuit_plugins/storage_recycle_cleaner/README.md) | 定时清理所选网盘回收站 |
| [跨网盘复制](cinecircuit_plugins/cloud_copy/README.md) | 在不同网盘账号之间按策略秒传或中转复制，支持自动补齐和工作流交接 |
| [字幕自动管理](cinecircuit_plugins/subtitle_manager/README.md) | 搜索、匹配并下载媒体字幕 |

可用配置、所需权限和触发方式以各插件清单与应用界面为准。

## 安装与使用

在 CineCircuit 的插件库中添加本仓库地址：

```text
https://github.com/misthanl/cinecircuit-plugins
```

宿主读取根目录 `plugins.json`，下载其中指向的 `packages/*.zip` 并核对 SHA-256。也可下载对应 ZIP，在应用中离线安装。

安装后根据界面确认权限和信任，完成配置，再启用所需功能。定时任务和事件触发需要对应配置；安装插件不会自动填写外部服务账号。

CookieCloud 浏览器扩展的服务地址为：

```text
https://你的服务地址/plugin-public/cookiecloud
```

使用该地址前应先在宿主中安装并配置 CookieCloud 插件。

## 开发环境

需要 Python 3.12+、Node.js 22.18+、pnpm，以及同级的 CineCircuit 主项目作为 SDK 与测试环境：

```text
workspace/
├── cinecircuit/
└── cinecircuit-plugins/
```

主项目为私有仓库，开发者需要获得访问权限。先按主项目 README 创建 `.venv`、安装锁定依赖，再在本仓库执行：

```bash
pnpm install --frozen-lockfile
../cinecircuit/.venv/bin/python build.py --content-addressed
```

Windows 使用 `../cinecircuit/.venv/Scripts/python.exe`。

## 构建与发布

| 路径 | 用途 |
| --- | --- |
| `cinecircuit_plugins/` | 插件源码、清单、Vue 页面及资源 |
| `sdk/` | 前端 SDK 类型与声明 |
| `tests/` | 插件及宿主集成测试 |
| `.build/` | 可重建的前端编译中间产物 |
| `dist/` | 本地离线安装包与 `packages.json` |
| `packages/` | GitHub 发布用 ZIP |
| `plugins.json` | GitHub 插件库索引 |

`build.py --content-addressed` 使用内容摘要命名 ZIP，同时生成本地目录和 GitHub 索引。发布时应一起提交 `plugins.json` 与它引用的安装包，确保摘要一致。

默认 `build.py` 使用版本号文件名，会拒绝用不同内容覆盖已有同名版本包。内容摘要模式可区分同版本的不同构建；正式功能迭代仍应按发布策略维护版本号。保留正在使用的精确安装包，避免影响安装恢复。

带界面的插件使用 Vue 单文件组件。构建会生成独立浏览器 ESM、内联样式并复用宿主 Vue 运行时，不把开发依赖或完整宿主打进插件 ZIP。

## 宿主与插件的边界

宿主负责通用安装、加载、权限、调度、数据网关与扩展插槽；插件专属业务、页面、资源和测试只放在本仓库。

容器内默认位置：

- `/app/plugin-runtime/installed/<插件ID>/`：已安装代码。
- `/app/plugin-runtime/catalog/`：本地可安装包目录。

宿主镜像可以从本仓库的固定提交收集已校验 ZIP，作为离线目录；这不等于将插件实现合并到宿主源码。运行目录由 `PLUGIN_RUNTIME_DIR` 指定，应位于应用配置目录之外。

容器重启保留可写层，删除重建容器则不会。已安装记录的自动恢复要求原版本、原摘要对应的包仍可从镜像目录或记录的来源取得；不要随意移除仍被使用的发布包。

## 检查与测试

```bash
pnpm run quality:frontend
../cinecircuit/.venv/bin/python scripts/quality.py
../cinecircuit/.venv/bin/python -m pytest tests cinecircuit_plugins -q
```

测试与构建依赖同级宿主。公开插件仓库的 GitHub Actions 若要检出私有宿主，需要单独配置具有该宿主读取权限的凭据；默认 `GITHUB_TOKEN` 不提供跨私有仓库访问。

源码仓库不提交 `.env`、账号令牌、数据库、`node_modules`、缓存、`.build`、`dist` 和本地 NAS 部署备份。`packages/` 与 `plugins.json` 属于发布内容，需要上传。

## 开源许可

本项目有权授权的自有代码采用 **GNU General Public License v3.0 only（SPDX：`GPL-3.0-only`）**，仅适用第 3 版，不包含“或任何更新版本”的授权。完整条款见 [LICENSE](LICENSE)，适用范围见 [LICENSE_SCOPE.md](LICENSE_SCOPE.md)。

第三方代码、字体、图片及其他资源不因置于本仓库而改变原有许可。OpenCC 的 Apache-2.0 许可证与 NOTICE、字体各自的 OFL 或其他授权说明均予保留。对未明确取得再分发许可的资源，本项目不授予额外权利；使用或再分发前应单独核实。相关记录见各组件目录中的许可证和来源文件。

## 免责声明

使用者应遵守适用法律法规，尊重第三方合法权益，不得利用本软件从事违法活动，并依法承担自身使用行为产生的责任。

本软件按“原样”提供，在适用法律允许的范围内不提供任何担保。免责及责任限制以 GPL-3.0-only 第 15、16 条和适用法律为准。

本项目不提供影视内容，也不授予访问、下载、传播第三方内容或资源的权利。使用者应遵守适用法律、相关服务条款及内容授权要求。

插件可能执行下载、删除、整理文件或修改媒体库元数据等操作。启用前应核对配置与权限，备份重要数据；外部服务变化可能造成接口失效、任务失败或结果不完整。

本节不限制 GPL-3.0-only 授予的使用、修改及分发权利，也不排除法律规定不得排除的责任。
