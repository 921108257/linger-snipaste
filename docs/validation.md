# v0.4.1 剪贴板验证

2026-09-15，GNOME 46 Wayland。用户报告点击“复制并完成”后不能粘贴。

旧版 Python GTK worker 没有窗口和输入焦点，向 Wayland 设置 selection 时缺少对应输入序号。`set_image()` 无返回值，后端仍无条件返回 `copied: true`。该问题在隔离桌面中复现：后台进程返回成功，独立 GTK 接收进程得到空图片。

新版在原生窗口的 GTK 主线程上提供 `image/png`，先检查窗口焦点及 GTK 接管结果，再结束选区。图片保存在剪贴板回调中，由常驻桌面进程提供，不随截图窗口关闭而释放。后台写入接口明确报错，避免旧路径误用。

```bash
cargo build --manifest-path src-tauri/Cargo.toml --example clipboard_probe
/usr/bin/python3 scripts/check-clipboard.py
```

`clipboard_probe` 使用产品的同一剪贴板函数。脚本启动独立 D-Bus、临时 GNOME 46 桌面和虚拟键盘设备，不改变用户会话的剪贴板或输入。验证结果：

- 旧无窗口 worker 返回成功，但独立接收应用没有图片。
- 新实现连续两次复制 73×41 的不同图像并关闭源窗口，接收进程读取到匹配的尺寸和像素。
- 未显示、无焦点的窗口调用被拒绝。
- 前端测试确认复制请求成功前不会关闭选区，失败时选区保留并显示错误。
- 15 项 Python、10 项 Vue/TypeScript 测试通过，前端和 Rust release 构建及严格 Clippy 通过。

此测试验证实际 GNOME 剪贴板和跨进程读取；不等同于用户在所有目标应用中的物理粘贴验证。源窗口关闭后应用仍需后台运行，退出整个应用后的持久化由桌面剪贴板管理器决定。

# v0.4.0 验证记录

2026-09-15，Ubuntu 24.04 / GNOME 46 Wayland。

## 原因

v0.3.0 为处理后台 Portal 焦点拒绝，将 GNOME 截图强制设为 interactive=true。系统 ScreenshotUI 完成后才打开 Linger 选区，造成双重选择。09:14–09:22 系统日志多次记录 `InteractiveScreenshot didn't return a file`；这不等同于“权限拒绝”，旧版提示不准确。

普通进程直接调用 org.gnome.Shell.Screenshot 实测返回 `Screenshot is not allowed`。因此新版使用显式启用的 GNOME 扩展执行单次取图，不关闭系统安全检查，不使用录屏流。

## 实际桌面组件验证

`scripts/check-direct-capture.py` 在独立 D-Bus、临时设置和 1280×800 GNOME 46 headless 显示器中启动真正的 GNOME Shell、桌面扩展和原生 Linger。

- 扩展返回可解码的 1280×800 PNG，metadata source=gnome-extension，两次验证约 655–902 ms。
- 启动原生设置窗口后截图，GNOME 未记录窗口模糊 API 错误；这不替代真实桌面的磨砂视觉验收。
- 再次触发 --capture 仅聚焦现有窗口，图片总数保持 1。
- 普通 gdbus 客户端调用扩展时被拒绝，只有 Linger 的实际 worker 可调用。
- 测试配置和开发客户端路径只注入临时扩展 metadata，发布扩展不包含开发白名单。
- 不替换或重启用户的真实 GNOME 会话，不改用户的快捷键和扩展设置。

## 自动检查

15 项 Python 测试通过，覆盖存储、URI、取消、失败不重试交互、GNOME 直接路径不调用 Portal、错误提示、识别与快捷键持久化/冲突/回滚。8 项 Vue/TypeScript 测试通过，覆盖选区、文字、橡皮擦、导出像素和嵌套容器。

前端与 Rust release 构建、严格 Clippy 检查通过。打包依赖用 scripts/check-package.py 的 Python -S 检查，避免开发机系统 Python 包掩盖遗漏。

## 边界

安装新扩展后 GNOME 46 需要注销并重新登录才能发现它；由设置页的明确按钮启用。没有直接替换本机已安装的 v0.3.0。真实桌面的物理快捷键、磨砂视觉效果、多屏、分数缩放及非 GNOME 桌面仍需额外验证。
