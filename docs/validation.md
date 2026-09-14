# 验证记录

2026-09-14，Ubuntu GNOME Wayland。

- 后端 8 项测试：PNG 存储与哈希、ID 路径约束、无效图像拒绝、本地 Portal URI 验证、每次截图读取新结果、取消与失败清理、私有子进程拒绝旧命令且随 stdin EOF 退出。
- Vue 组件 4 项测试：选区拖动与八向缩放；文字自动选中、拖动、控制点缩放、双击修改与撤销；导出只含选区像素；橡皮擦只擦除标注且可撤销。
- 组件测试在 jsdom 中派发 DOM 鼠标/指针事件，Konva 使用真实 Canvas 栅格化；不等同于原生 WebKit 或浏览器实机手势验证。
- 700×400 导出逐像素检查通过，不含遮罩、边框、控制点或工具栏。橡皮擦路径处恢复原图 RGB 与完整 alpha，路径外保留画笔颜色。
- 本版已移除常驻共享、旧帧缓存和对外截图接口，之前对旧版采集链路的验证不能作为本版实机验证。
- 最终 `npm test`、`npm run build`、`cargo build --manifest-path src-tauri/Cargo.toml --features tauri/custom-protocol` 均通过。重新注册 F1 时保留了其他已有绑定。

Web Interface Guidelines 复核：

- `src/components/IconButton.vue`：按钮名称、工具提示、按下状态、焦点状态通过。
- `src/components/CaptureOverlay.vue`：输入名称与焦点、输入法组合键保护、方向键移动对象/选区、Ctrl+A 全屏、Enter 完成、Esc 退出、错误提示已检查；绘图与八向缩放仍需指针输入。
- `src/components/PinWindow.vue`：图片 alt / 尺寸、缩放按钮、透明度输入标签、快捷键通过。
- `src/capture.css`：工具栏按实际尺寸定位、22px 选区命中区域、焦点状态、长错误换行已检查。

本次浏览器控制工具返回 `Codex auth token is unavailable`，因此未完成桌面/移动视口截图复核，也未完成新版 GNOME Screenshot Portal 的人工确认、窗口模式和 F1 实机闭环。后端 Portal 成功/取消测试使用替身，不宣称真实系统截图已通过。

未验证：KDE/X11、多显示器、分数缩放、全局 F2、自包含安装包。全局快捷键仅注册 F1。
