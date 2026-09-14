# Linger 截图 v0.1.0

Linux 桌面的 Snipaste 风格截图工具首个版本，面向 GNOME Wayland。

**F1 → 冻结全屏 → 拖动框选 → 悬浮标注 → 复制 / 保存 / 贴图**

## 功能

- **框选与调整**：拖动选区内部移动裁剪范围，八个控制点缩放；方向键微调，`Shift` + 方向键移动 10 像素。单击画面空白处、`Ctrl+A` 或工具栏“选取全屏”选中整张画面。
- **标注**：画笔、形状、文字、马赛克。文字插入后自动选中，可拖动移动、控制点缩放、双击改内容；`Esc` 取消选中，`Delete` 删除选中标注。
- **橡皮擦**：擦除画笔、形状、文字与马赛克标注，保留截图原图；工具栏可调笔头大小，马赛克擦除后恢复为原图。
- **历史**：`Ctrl+Z` 撤销，`Ctrl+Shift+Z` 重做。
- **输出**：`Enter` / `Ctrl+C` 复制，`Ctrl+S` 保存，`F2` 贴图（支持缩放与透明度），`Esc` / 右键取消。
- **托盘常驻**：主窗口隐藏，托盘菜单提供截图、系统窗口截图、打开主界面与退出。
- **系统窗口截图**：调用 GNOME 自带截图选择器，选择窗口并完成系统确认后进入标注层。

工具栏不占用图片布局，也不进入导出图片。

## 架构

- **前端**：Vue 3 + Konva + TypeScript（Vite 构建 / vitest 测试）
- **桌面壳**：Tauri 2（Rust），注册 GNOME 全局 F1 与托盘图标
- **后端**：Python GTK/D-Bus 子进程，经父子进程私有管道通信；通过系统 Screenshot Portal **每次请求单张截图**，无常驻屏幕流

## 下载

| 资源 | 说明 |
| --- | --- |
| `linger-snipaste-v0.1.0-x86_64-linux.tar.gz` | Linux x86_64 可执行文件 + Python 后端组件 |

```bash
tar -xzf linger-snipaste-v0.1.0-x86_64-linux.tar.gz
cd linger-snipaste-v0.1.0-x86_64-linux
sha256sum -c SHA256SUMS   # 校验
./linger-snipaste         # 运行
```

**请保持解压后的目录结构不变**，可执行文件会在自身所在目录旁查找 `service/daemon.py`。

### 系统依赖

本版本不是自包含安装包，需要系统提供 Python 3、GTK 与 D-Bus：

```bash
sudo apt install python3-gi python3-dbus python3-pil gir1.2-gtk-3.0
```

GNOME 全局 F1 需额外注册（脚本在源码仓库中）：

```bash
/usr/bin/python3 scripts/install-shortcut.py
```

## 验证情况

- 8 项 Python 后端用例（Portal 请求与取消、ID 越界防护、像素哈希与历史、私有管道协议）通过。
- 4 项 Vue 交互 / 像素导出用例（裁剪与八向缩放、文字拖拽缩放编辑与撤销、橡皮擦保留原图并支持撤销）通过。
- 发布包在源码仓库之外解压启动，后端组件按预期从包内 `service/daemon.py` 拉起。

## 已知边界

- 单显示器为主要使用场景；多屏、分数缩放、KDE、X11 尚未完成验证。
- 截图由系统 Screenshot Portal 提供，系统可能显示预览或“共享”提示；这里的“共享”表示把这一张截图交给本机应用，不是上传或链接分享。确认界面与出现频率由桌面系统决定。
- 尚未制作自包含安装包；F1 目前仅在应用与截图层内生效，系统级全局快捷键依赖注册脚本。
- 贴图缩放与透明度可用，是否允许置顶取决于窗口管理器。
- 选区接近全屏时工具栏会浮在画面边缘；可编辑的截图尺寸不会缩小，导出不含工具栏。
- 原图与编辑副本保存在 `${XDG_DATA_HOME:-~/.local/share}/linger-snipaste`，尚无自动清理策略；马赛克可被橡皮擦恢复为原图，请留意本地原始副本。

详细验证范围见 [docs/validation.md](https://github.com/921108257/linger-snipaste/blob/main/docs/validation.md)。
