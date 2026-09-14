# v0.3.0 验证记录

2026-09-15，Ubuntu 24.04 / GNOME Wayland。

## 截图故障证据

系统日志在旧版失败时记录 `Only the focused app is allowed to show a system access dialog`。旧版先隐藏窗口，然后使用无父窗口的 Python 子进程发起非交互 Screenshot Portal，请求被 GNOME 拒绝。

新版 GNOME 使用交互 Screenshot Portal；非 GNOME 后端失败时仅重试一次交互模式。取消不重试、不弹错误窗口。安装包补上遗漏的 `_dbus_bindings`、`_dbus_glib_bindings`，同时声明 GTK 类型库和 Portal 后端依赖。

## 自动验证

- Python 14 项：存储、URI 与路径约束、Portal 成功/失败/取消清理、GNOME 交互选择、非交互失败重试、私有进程退出、普通及双倍分辨率嵌套容器、纯色图、快捷键持久化和冲突保护、写入失败时回滚、非法快捷键。
- Vue/TypeScript 8 项：选区移动与八向缩放、文字编辑与撤销、橡皮擦、像素导出、容器悬停与滚轮切换、手动框选优先、归一化命中与非法边界过滤。
- 700×400 普通裁剪逐像素一致；容器单击导出 360×304，边框、遮罩与工具栏不进入图片。
- 用户提供的旧界面截图识别出 6 个区域，包括内容容器和两个按钮区域，耗时约 30 ms。
- `npm test`、`npm run build` 和 Rust release 构建通过。
- `scripts/check-package.py` 使用 Python `-S` 禁用系统 site-packages，检查依赖确实来自安装包的 vendor，验证 OpenCV、GTK 导入及打包后端的状态/设置/私有协议。
- 安装包私有依赖与后端检查通过；`apt-get -s install` 确认可从 v0.2.0 升级到 v0.3.0，依赖可满足。没有直接修改本机已安装的旧版本。

## 浏览器验证

使用真实浏览器检查设置页；录入 Ctrl+Shift+F9 并保存，成功状态与禁用的保存按钮均正确。660×700 与 390×844 视口无横向溢出或控件重叠。

## 尚未验证

本次发起了真实系统截图请求，但系统确认未在 120 秒内完成，返回超时；不能把 Portal 替身测试视为真实截图成功。当前工具不能控制 GNOME 原生截图界面。安装后的系统确认、全局快捷键物理按键以及贴图仍需桌面端操作验证。

未验证 KDE/X11、多屏、分数缩放。识别依赖可见边界，不保证所有应用的内部元素都能被识别。
