# CineCircuit 独立插件项目

具体插件源码、前端统计页面、配置编辑器和业务测试只维护在本目录。宿主项目 `../cinecircuit` 只提供通用 SDK、安装加载、权限和扩展插槽，不复制或打包这些源码。

## 构建和安装

先运行 `pnpm install` 安装锁定的 TypeScript、Vite 与 Vue SFC 工具链，再使用宿主开发环境的 Python 运行 `build.py`，生成 `dist/*.zip` 和带 SHA-256 的 `dist/packages.json`。插件可在 `frontend.ts` 中引入 `.vue` 单文件组件；构建器会把每个插件独立编译为单个浏览器 ESM `frontend.js`，将 scoped CSS 内联，并把 Vue 导入连接到宿主共享运行时。ZIP 不会包含 Vue、TypeScript、`.vue` 源码、额外 CSS、类型声明或 source map。构建时会检查每个独立 ZIP 的入口、相对导入与清单一致性。

所有带界面的正式插件都以 Vue SFC 实现页面或编辑器；`frontend.ts` 只负责扩展注册、SDK 请求桥接和宿主组件注入。无前端入口的纯后台插件不需要创建空的 Vue 页面。

## GitHub 插件库发布

`build.py` 同时生成仓库根目录的 `plugins.json` 和 `packages/*.zip`。在线索引包含完整插件清单、相对下载地址 `package_url` 和 ZIP 的 SHA-256，直接适配宿主的 GitHub 插件库接口。

将本项目源码、`plugins.json` 和 `packages/` 推送到 GitHub 仓库的 `main` 分支，再在应用的插件库中添加该仓库地址。使用公开且无需额外认证的仓库时，应用即可读取列表、下载和校验安装包。插件安装后默认停用，需要确认权限和信任后启用。

更新插件时重新运行构建并同时提交索引和对应 ZIP，避免索引摘要与安装包不一致。`dist/` 是本地构建和离线部署目录，不提交；NAS 专用部署脚本同样不提交。

安装后的代码位于容器内 `/app/plugin-runtime/installed/<插件ID>/`，不放进 `/config`、宿主源码、镜像或前端 bundle。根目录可通过 `PLUGIN_RUNTIME_DIR` 调整，但必须在 `CONFIG_DIR` 外。Compose 保持不变，不增加插件挂载。容器重启会保留运行文件；删除并重建容器后，需要恢复或重新安装独立插件包。更新插件独立发布 ZIP。

需要通过本地插件库展示时，将 `dist/packages.json` 和其中列出的 ZIP 独立放到容器内 `/app/plugin-runtime/catalog/`。先上传 ZIP，最后更新目录索引，宿主即可通过通用本地目录接口展示并校验安装。此目录不进入主项目或镜像，展示不会自动安装、信任或启用插件。也可使用宿主已有的 GitHub 插件库来源。

## CookieCloud 地址

CookieCloud 浏览器扩展服务地址填写 `http(s)://你的服务地址/plugin-public/cookiecloud`。

## 测试

从宿主目录运行 `.venv/Scripts/python.exe -m pytest ../cinecircuit-plugins/tests ../cinecircuit-plugins/cinecircuit_plugins`。插件仓库内运行 `npm run typecheck` 检查所有前端源码，运行 `npm run test:frontend` 编译并测试生成的浏览器 ESM。测试的显式注册仅存在于本项目测试夹具，生产宿主不自动发现或导入本项目。
