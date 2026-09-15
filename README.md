# Linger 截图

Linux 桌面的 Snipaste 风格截图工具，当前面向 GNOME Wayland。

**F1 → Linger 选区 → 悬停识别容器 / 拖动框选 → 标注 → 复制 / 保存 / 贴图**。启用配套 GNOME 扩展后只取一张图，不再打开第二个系统选区面板。工具栏不进入导出图片。

应用登录后静默驻留托盘；从应用菜单启动或点击托盘“设置…”打开偏好设置。关闭设置窗口继续后台运行，托盘“退出”才结束进程。

## 设置

- 默认全局 F1 截图、F2 贴图，可点击快捷键字段录入新组合后保存；Backspace 清除，Esc 取消。GNOME 内置快捷键和其他应用的自定义快捷键冲突会报错并保留旧设置。
- F2 在截图层内贴出当前选区，在其他位置贴出剪贴板图片。
- 可关闭“自动识别容器区域”或“登录后自动启动”。设置保存在 `${XDG_CONFIG_HOME:-~/.config}/linger-snipaste/settings.json`。
- 首次运行自动注册快捷键。非 GNOME 桌面可在系统快捷键设置中绑定 `/usr/bin/linger-snipaste --capture` 和 `/usr/bin/linger-snipaste --pin`。
- GNOME 46 的安装包包含 `capture@linger-snipaste` 扩展。首次安装后在设置中点击“启用直接截图”，然后注销并重新登录一次。扩展只允许 Linger 的后台子进程读取单张屏幕图，锁屏时拒绝截图。
- 设置窗口没有系统标题栏，可拖动内部标题区移动。“收起到托盘”位于“保存设置”左侧；配套扩展同时提供窗口背后的磨砂模糊。

## 操作

- 框选后拖动选区内部移动裁剪范围，拖动八个边角控制点调整大小。方向键微调，Shift 加方向键移动 10 个屏幕像素。
- 未框选时，鼠标悬停预览识别到的窗口内部容器区域；滚轮向下选更大的包围区域，向上选更小区域，单击确认。拖动始终使用自由框选。Ctrl+A 或工具栏“选取全屏”选择整张画面。
- 添加文字后自动选中文字。拖动文字移动，拖动文字外围的控制点缩放；双击修改内容。Esc 取消选中，Delete 删除选中的标注。
- 橡皮擦擦除画笔、形状、文字和马赛克等标注，保留截图原图；工具栏可调橡皮大小。
- v0.4.1 起，图片由原生窗口进程写入剪贴板，关闭截图选区后仍可粘贴到其他应用；失败会保留选区并显示错误。
- Ctrl+Z 撤销，Ctrl+Shift+Z 重做。Enter / Ctrl+C 复制完成，Ctrl+S 保存，F2 贴图，Esc 或右键取消。
- 容器识别使用 OpenCV 轮廓与多阈值表面检测，支持窗口内部面板、卡片和有明显边界的矩形元素，不依赖应用是否提供可访问性树。没有可见边界或复杂背景的区域可能无法识别，可拖动框选。

## 桌面截图通道

旧版通过持续屏幕共享取帧，已改为每次向系统请求一张截图。现在没有常驻屏幕流，不需要先连接显示器，也不再用旧帧缓存。

GNOME Wayland 不允许普通应用无授权直接截屏。v0.3.0 为处理焦点拒绝而使用交互 Portal，导致先系统选区、后 Linger 选区。v0.4.0 改为显式启用的 GNOME 扩展一次取图，未启用时提示设置，不偷偷回退到系统选区。其他桌面保留非交互 Portal 兼容路径，实际授权由桌面决定。

已移除 Agent 集成、MCP、截图命令行接口和公开 socket/HTTP 截图接口。桌面应用通过父子进程私有管道调用后端，GNOME 扩展的 D-Bus 接口核验调用进程和 Linger 父进程。`--capture` 只为系统快捷键唤起可见截图界面，不输出图片或 JSON。

## 运行与构建

### 安装 .deb（推荐）

从 [Releases](https://github.com/921108257/linger-snipaste/releases) 下载后：

```bash
sudo apt install ./linger-snipaste_0.4.1_amd64.deb
```

包内已附带 Python 后端及依赖（`gi` / `dbus` / `PIL` / `cairo` / NumPy / OpenCV，包括 D-Bus 原生扩展），无需安装对应系统 Python 包；GTK、WebKitGTK、类型库和桌面 Portal 由 `apt` 依据 `Depends` 自动补齐。升级后从旧版托盘退出，再打开新版；已运行的旧进程不会自动替换。

手动重新注册已保存的全局快捷键（可选，以桌面用户身份执行）：

```bash
/usr/lib/linger-snipaste/install-shortcut.py
```

自行打包：

```bash
npm install && npm run build
python3 -m pip install --target dist-deb/runtime -r service/requirements.txt
cargo build --manifest-path src-tauri/Cargo.toml --release --features tauri/custom-protocol
./scripts/build-deb.sh          # 产物：dist-deb/releases/linger-snipaste_0.4.1_amd64.deb
/usr/bin/python3 scripts/check-package.py dist-deb/linger-snipaste_0.4.1_amd64
```

包的 `Depends` 由 `dpkg-shlibdeps` 依据二进制及 Python 扩展真实链接关系推导。包内扩展锁定 Python 3.12（Ubuntu 24.04 默认版本）。构建识别依赖也需使用 Python 3.12；没有 pip 时先安装 `python3-pip`。

`dist/` 仅放前端资源，会被 Tauri 嵌入程序；不要把安装包复制到此目录。安装包输出到 `dist-deb/releases/`，避免后续构建递归嵌入旧安装包。

### 从源码运行

需要 Node.js 22+、Rust，以及系统桌面库：

```bash
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev \
  libayatana-appindicator3-dev python3-gi python3-dbus python3-pil gir1.2-gtk-3.0
npm install
python3 -m pip install --target dist-deb/runtime -r service/requirements.txt
npm run desktop
```

构建嵌入前端资源的原生可执行文件，并注册 GNOME 全局 F1：

```bash
npm run build
cargo build --manifest-path src-tauri/Cargo.toml --features tauri/custom-protocol
/usr/bin/python3 scripts/install-shortcut.py
```

可执行文件位于 `src-tauri/target/debug/linger-snipaste`。注册脚本保留其他已有快捷键；撤销注册可运行该脚本并加 `--remove`。`--background` 静默启动，`--settings` 打开设置。

`npm run dev` 提供浏览器图片编辑预览；可通过“打开图片”导入本地文件。浏览器预览没有桌面截图通道，图片保存在该浏览器的 IndexedDB。开发时 `?sample=1` 可打开内置测试图。

```bash
npm test              # Python 后端与 Vue 组件交互 / 像素导出测试
npm run build         # TypeScript 与前端构建
npm run desktop:build # 原生构建，不生成安装包
```

## 当前边界

- 单显示器为主要使用场景；多屏、分数缩放、KDE、X11 尚未完成验证。
- 自动容器识别依据可见图像边界，不是 DOM/控件语义解析，也不保证识别所有元素。仅本机处理，没有远程图像服务。
- 选区接近全屏时工具栏会浮在画面边缘；可编辑的截图尺寸不会缩小，导出不含工具栏。
- 贴图支持缩放与透明度；是否允许置顶取决于窗口管理器。
- 原图和编辑副本保存在 `${XDG_DATA_HOME:-~/.local/share}/linger-snipaste`，尚无自动清理策略。马赛克可被橡皮擦恢复为原图，请留意本地原始副本。
- 已提供自包含 `.deb`：二进制与 Python 依赖随包分发，系统 C 库经 `Depends` 由 `apt` 安装。当前仅打包 Ubuntu 24.04 / amd64，包内 Python 扩展锁定 3.12。

详细验证范围见 [docs/validation.md](docs/validation.md)。
