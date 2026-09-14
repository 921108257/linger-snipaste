# Linger 截图

Linux 桌面的 Snipaste 风格截图工具，当前面向 GNOME Wayland。

**F1 → 冻结全屏 → 拖动框选 → 悬浮标注 → 复制 / 保存 / 贴图**。工具栏不占用图片布局，也不进入导出图片。

## 操作

- 框选后拖动选区内部移动裁剪范围，拖动八个边角控制点调整大小。方向键微调，Shift 加方向键移动 10 个屏幕像素。
- 单击未框选的画面、Ctrl+A 或工具栏“选取全屏”选择整张画面。
- 添加文字后自动选中文字。拖动文字移动，拖动文字外围的控制点缩放；双击修改内容。Esc 取消选中，Delete 删除选中的标注。
- 橡皮擦擦除画笔、形状、文字和马赛克等标注，保留截图原图；工具栏可调橡皮大小。
- Ctrl+Z 撤销，Ctrl+Shift+Z 重做。Enter / Ctrl+C 复制完成，Ctrl+S 保存，F2 贴图，Esc 或右键取消。
- “系统窗口截图”打开 GNOME 自带的截图选择器。选择窗口并完成系统确认后，进入标注层。它依赖桌面提供的交互模式；当前没有自定义的悬停窗口识别。

## 为什么系统仍可能显示“共享”或确认窗口

旧版通过持续屏幕共享取帧，已改为每次向系统请求一张截图。现在没有常驻屏幕流，不需要先连接显示器，也不再用旧帧缓存。

GNOME Wayland 限制普通应用直接读取其他窗口。应用通过系统 Screenshot Portal 请求截图，系统可能显示截图预览及“共享”按钮；这里表示把这一张截图交给本机应用，不是上传或链接分享。确认界面和出现频率由桌面系统决定，不能承诺免确认或毫秒级唤起。

已移除 Agent 集成、MCP、截图命令行接口和公开 socket/HTTP 截图接口。桌面应用仅通过父子进程私有管道调用系统组件。`--capture` 只为系统快捷键唤起可见截图界面，不输出图片或 JSON。

## 运行与构建

### 安装 .deb（推荐）

从 [Releases](https://github.com/921108257/linger-snipaste/releases) 下载后：

```bash
sudo apt install ./linger-snipaste_0.2.0_amd64.deb
```

包内已附带 Python 后端及其依赖（`gi` / `dbus` / `PIL` / `cairo`），无需安装 `python3-gi` 等系统 Python 包；GTK 与 WebKitGTK 等系统库由 `apt` 依据 `Depends` 自动补齐。安装后应用随会话自启动并常驻托盘，按 F1 截图。

注册 GNOME 全局 F1（以桌面用户身份执行一次）：

```bash
/usr/lib/linger-snipaste/install-shortcut.py
```

自行打包：

```bash
npm install && npm run build
cargo build --manifest-path src-tauri/Cargo.toml --release --features tauri/custom-protocol
./scripts/build-deb.sh          # 产物：dist/linger-snipaste_0.2.0_amd64.deb
```

包的 `Depends` 由 `dpkg-shlibdeps` 依据二进制真实链接关系推导，新增系统库依赖会自动体现。包内 `gi` / `PIL` 含 `cpython-312` 扩展，因此锁定 Python 3.12（Ubuntu 24.04 默认版本）。

### 从源码运行

需要 Node.js 22+、Rust，以及系统桌面库：

```bash
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev \
  libayatana-appindicator3-dev python3-gi python3-dbus python3-pil gir1.2-gtk-3.0
npm install
npm run desktop
```

构建嵌入前端资源的原生可执行文件，并注册 GNOME 全局 F1：

```bash
npm run build
cargo build --manifest-path src-tauri/Cargo.toml --features tauri/custom-protocol
/usr/bin/python3 scripts/install-shortcut.py
```

可执行文件位于 `src-tauri/target/debug/linger-snipaste`。F1 注册脚本保留其他已有快捷键；移动项目后需重新运行脚本。撤销注册可运行该脚本并加 `--remove`。F2 当前仅在应用和截图层内生效。

`npm run dev` 提供浏览器图片编辑预览；可通过“打开图片”导入本地文件。浏览器预览没有桌面截图通道，图片保存在该浏览器的 IndexedDB。开发时 `?sample=1` 可打开内置测试图。

```bash
npm test              # Python 后端与 Vue 组件交互 / 像素导出测试
npm run build         # TypeScript 与前端构建
npm run desktop:build # 原生构建，不生成安装包
```

## 当前边界

- 单显示器为主要使用场景；多屏、分数缩放、KDE、X11 尚未完成验证。
- 选区接近全屏时工具栏会浮在画面边缘；可编辑的截图尺寸不会缩小，导出不含工具栏。
- 贴图支持缩放与透明度；是否允许置顶取决于窗口管理器。
- 原图和编辑副本保存在 `${XDG_DATA_HOME:-~/.local/share}/linger-snipaste`，尚无自动清理策略。马赛克可被橡皮擦恢复为原图，请留意本地原始副本。
- 已提供自包含 `.deb`：二进制与 Python 依赖随包分发，系统 C 库经 `Depends` 由 `apt` 安装。当前仅打包 Ubuntu 24.04 / amd64，包内 Python 扩展锁定 3.12。

详细验证范围见 [docs/validation.md](docs/validation.md)。
