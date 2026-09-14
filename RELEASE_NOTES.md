# Linger 截图 v0.2.0

Linux 桌面的 Snipaste 风格截图工具。**本版本提供自包含 .deb 安装包，安装即可使用，无需再编译或手动安装 Python 依赖。**

**F1 → 冻结全屏 → 拖动框选 → 悬浮标注 → 复制 / 保存 / 贴图**

## 安装（推荐）

```bash
sudo apt install ./linger-snipaste_0.2.0_amd64.deb
```

`apt` 会自动补齐 GTK / WebKitGTK 等系统库，随后：

- 应用随桌面会话**自动启动并常驻托盘**；
- 按 **F1** 截图，或使用托盘菜单；
- 如需注册 GNOME 全局 F1 快捷键，以桌面用户身份执行一次：

```bash
/usr/lib/linger-snipaste/install-shortcut.py
```

卸载：`sudo apt remove linger-snipaste`

## 这个包自带什么

打包时已把 Python 后端连同依赖一并放入包内，**不再需要 `python3-gi` / `python3-dbus` / `python3-pil`**：

| 包内路径 | 内容 |
| --- | --- |
| `/usr/bin/linger-snipaste` | 启动器（设置私有 `PYTHONPATH`） |
| `/usr/lib/linger-snipaste/linger-snipaste` | Tauri 主程序（Rust，已 strip） |
| `/usr/lib/linger-snipaste/service/` | Python 后端（Portal 截图 / 存储） |
| `/usr/lib/linger-snipaste/vendor/` | 私有依赖副本：`gi`、`dbus`、`PIL`、`cairo` |
| `/usr/share/applications/`、`/etc/xdg/autostart/` | 桌面入口与自启动 |

安装后占用约 13 MB。

### 关于系统库

GTK3 与 WebKitGTK 等 **C 系统库没有打进包里**，而是按 Debian 规范写进 `Depends`，由 `apt` 自动安装。这样做是刻意的：把 WebKitGTK 私有打进 `.deb` 会与发行版包管理冲突、体积暴涨且易碎，而依赖声明能达到同样的“一条命令装好”效果。

依赖由 `dpkg-shlibdeps` 依据二进制的真实链接关系自动推导，而非手工罗列：

```
python3 (>= 3.12), python3 (<< 3.13), libayatana-appindicator3-1,
libc6, libcairo2, libdbus-1-3, libgcc-s1, libgdk-pixbuf-2.0-0,
libglib2.0-0t64, libgtk-3-0t64, libjavascriptcoregtk-4.1-0,
libsoup-3.0-0, libwayland-client0, libwebkit2gtk-4.1-0
```

> **Python 版本限制**：包内的 `gi` / `PIL` 含 ABI 相关的 `cpython-312` 扩展，因此 `Depends` 锁定 **Python 3.12**（Ubuntu 24.04 默认版本）。在 Python 3.13 及以上的发行版上需重新打包。

## 从源码构建安装包

```bash
npm install
npm run build
cargo build --manifest-path src-tauri/Cargo.toml --release --features tauri/custom-protocol
./scripts/build-deb.sh          # 产物：dist/linger-snipaste_0.2.0_amd64.deb
```

## 相比 v0.1.0 的变化

- 新增 `.deb` 打包脚本 `scripts/build-deb.sh`，依赖由 `dpkg-shlibdeps` 推导。
- 主程序新增“可重定位”的后端查找：优先使用可执行文件旁的 `service/daemon.py`，不再依赖编译时的绝对路径（v0.1.0 的裸二进制在其他机器上无法找到后端）。
- `install-shortcut.py` 现在同时支持系统安装路径与源码路径。
- 版本号统一为 0.2.0。

## 功能

- **框选与调整**：拖动选区内部移动裁剪范围，八个控制点缩放；方向键微调，`Shift` + 方向键移动 10 像素。单击画面空白处、`Ctrl+A` 或工具栏“选取全屏”选中整张画面。
- **标注**：画笔、形状、文字、马赛克。文字插入后自动选中，可拖动移动、控制点缩放、双击改内容；`Esc` 取消选中，`Delete` 删除选中标注。
- **橡皮擦**：擦除画笔、形状、文字与马赛克标注，保留截图原图；工具栏可调笔头大小。
- **历史**：`Ctrl+Z` 撤销，`Ctrl+Shift+Z` 重做。
- **输出**：`Enter` / `Ctrl+C` 复制，`Ctrl+S` 保存，`F2` 贴图（支持缩放与透明度），`Esc` / 右键取消。
- **托盘常驻**：主窗口隐藏，托盘菜单提供截图、系统窗口截图、打开主界面与退出。

工具栏不占用图片布局，也不进入导出图片。

## 架构

- **前端**：Vue 3 + Konva + TypeScript（Vite 构建 / vitest 测试）
- **桌面壳**：Tauri 2（Rust），注册 GNOME 全局 F1 与托盘图标
- **后端**：Python GTK/D-Bus 子进程，经父子进程私有管道通信；通过系统 Screenshot Portal **每次请求单张截图**，无常驻屏幕流

## 验证情况

- 8 项 Python 后端用例（Portal 请求与取消、ID 越界防护、像素哈希与历史、私有管道协议）通过。
- 4 项 Vue 交互 / 像素导出用例（裁剪与八向缩放、文字拖拽缩放编辑与撤销、橡皮擦保留原图并支持撤销）通过。
- 从 `.deb` 解包后的真实安装布局启动，主程序从包内 `/usr/lib/linger-snipaste/service/daemon.py` 解析后端，无路径错误。
- 后端使用包内 `vendor/` 私有依赖（不借助系统 `python3-gi`）完成协议往返，返回 `{"state": "ready", "backend": "portal-screenshot"}`。

## 已知边界

- 打包环境为 Ubuntu 24.04 (noble)；其他发行版/架构需自行重新打包。
- 单显示器为主要使用场景；多屏、分数缩放、KDE、X11 尚未完成验证。
- 截图由系统 Screenshot Portal 提供，系统可能显示预览或“共享”提示；这里的“共享”表示把这一张截图交给本机应用，不是上传或链接分享。确认界面与出现频率由桌面系统决定。
- 尚未制作自包含安装包之外的其它格式（无 AppImage / Flatpak / rpm）。
- 贴图缩放与透明度可用，是否允许置顶取决于窗口管理器。
- 原图与编辑副本保存在 `${XDG_DATA_HOME:-~/.local/share}/linger-snipaste`，尚无自动清理策略；马赛克可被橡皮擦恢复为原图，请留意本地原始副本。

详细验证范围见 [docs/validation.md](https://github.com/921108257/linger-snipaste/blob/main/docs/validation.md)。
