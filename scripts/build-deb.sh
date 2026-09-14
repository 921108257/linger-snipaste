#!/usr/bin/env bash
# 构建自包含 .deb 安装包：二进制 + Python 后端 + 私有 Python 依赖副本。
# 系统库（GTK/WebKitGTK 等）按 Debian 惯例声明为依赖，由 apt 自动满足。
set -euo pipefail

VERSION="${VERSION:-0.2.0}"
MAINTAINER="${MAINTAINER:-921108257 <74404890+921108257@users.noreply.github.com>}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/dist-deb"
PKG="$BUILD/linger-snipaste_${VERSION}_amd64"
BIN_SRC="$ROOT/src-tauri/target/release/linger-snipaste"
PY_DIST=/usr/lib/python3/dist-packages
OUT="$ROOT/dist/linger-snipaste_${VERSION}_amd64.deb"

fail() { echo "错误：$*" >&2; exit 1; }

[ -x "$BIN_SRC" ] || fail "找不到 release 二进制 $BIN_SRC，请先运行 npm run build 与 cargo build --release --features tauri/custom-protocol"

echo "==> 清理并准备目录"
rm -rf "$PKG"
install -d "$PKG/DEBIAN" \
  "$PKG/usr/bin" \
  "$PKG/usr/lib/linger-snipaste/service" \
  "$PKG/usr/lib/linger-snipaste/vendor" \
  "$PKG/usr/share/applications" \
  "$PKG/usr/share/icons/hicolor/256x256/apps" \
  "$PKG/etc/xdg/autostart"

echo "==> 安装主程序与后端"
install -m755 "$BIN_SRC" "$PKG/usr/lib/linger-snipaste/linger-snipaste"
install -m644 "$ROOT"/service/*.py "$PKG/usr/lib/linger-snipaste/service/"
install -m755 "$ROOT/scripts/install-shortcut.py" "$PKG/usr/lib/linger-snipaste/install-shortcut.py"

echo "==> 复制 Python 依赖（gi / dbus / PIL / cairo）"
for mod in gi dbus PIL cairo; do
  [ -e "$PY_DIST/$mod" ] || fail "系统缺少 $PY_DIST/$mod，请先安装 python3-gi python3-dbus python3-pil"
  cp -rL "$PY_DIST/$mod" "$PKG/usr/lib/linger-snipaste/vendor/"
done
# 离线字节码缓存，加快首次启动
/usr/bin/python3 -m compileall -q "$PKG/usr/lib/linger-snipaste/vendor" >/dev/null 2>&1 || true

echo "==> 生成启动器（私有 PYTHONPATH）"
cat > "$PKG/usr/bin/linger-snipaste" <<'LAUNCHER'
#!/bin/sh
# Linger 截图启动器：使用随包附带的 Python 依赖，不依赖系统的 python3-gi/dbus/pil。
# LINGER_ROOT 仅为测试预留，正式安装时为空，即使用 /usr。
set -e
ROOT="${LINGER_ROOT:-}"
export PYTHONPATH="$ROOT/usr/lib/linger-snipaste/vendor"
exec "$ROOT/usr/lib/linger-snipaste/linger-snipaste" "$@"
LAUNCHER
chmod 755 "$PKG/usr/bin/linger-snipaste"

echo "==> 生成桌面入口与图标"
ICON_SRC="$ROOT/src-tauri/icons/icon.png"
[ -f "$ICON_SRC" ] || fail "找不到图标 $ICON_SRC"
install -m644 "$ICON_SRC" "$PKG/usr/share/icons/hicolor/256x256/apps/linger-snipaste.png"

cat > "$PKG/usr/share/applications/linger-snipaste.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Linger 截图
Comment=Linux 桌面的 Snipaste 风格截图标注工具
Exec=/usr/bin/linger-snipaste
Icon=linger-snipaste
Terminal=false
Categories=Graphics;
Keywords=screenshot;capture;annotate;snipaste;截图;
StartupWMClass=linger-snipaste
DESKTOP

cat > "$PKG/etc/xdg/autostart/linger-snipaste.desktop" <<'AUTOSTART'
[Desktop Entry]
Type=Application
Name=Linger 截图
Comment=常驻托盘并注册 F1 截图
Exec=/usr/bin/linger-snipaste
Icon=linger-snipaste
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
AUTOSTART

echo "==> 安装后脚本"
cat > "$PKG/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
  cat <<'MSG'

Linger 截图已安装。

  * 命令：/usr/bin/linger-snipaste（已随会话自动启动并常驻托盘）
  * 截图：按 F1，或使用托盘菜单

如需注册 GNOME 全局 F1 快捷键，请以桌面用户身份执行一次：

  /usr/lib/linger-snipaste/install-shortcut.py

MSG
fi
exit 0
POSTINST
chmod 755 "$PKG/DEBIAN/postinst"

echo "==> 计算并写入依赖"
{
  echo "Source: linger-snipaste"
  echo "Package: linger-snipaste"
  echo "Version: $VERSION"
  echo "Architecture: amd64"
  echo "Maintainer: $MAINTAINER"
  echo "Installed-Size: 0"
  echo "Section: graphics"
  echo "Priority: optional"
  echo "Depends: DEPENDS_PLACEHOLDER"
  echo "Homepage: https://github.com/921108257/linger-snipaste"
  echo "Description: Linux 桌面的 Snipaste 风格截图标注工具"
  echo " F1 唤起冻结全屏，拖动框选后进入悬浮标注层，支持画笔、形状、"
  echo " 文字、马赛克与橡皮擦，可复制、保存与贴图。"
  echo " ."
  echo " 随包附带私有 Python 依赖副本（gi/dbus/PIL/cairo），无需额外"
  echo " 安装 python3-gi 等系统 Python 包；GTK 与 WebKitGTK 等系统库"
  echo " 按 Debian 惯例声明为依赖，由 apt 自动安装。"
} > "$PKG/DEBIAN/control"

# dpkg-shlibdeps 依据二进制真实链接关系推导系统库依赖
mkdir -p "$BUILD/debian"
cp "$PKG/DEBIAN/control" "$BUILD/debian/control"
SHLIB_DEPS="$(cd "$BUILD" && dpkg-shlibdeps -O \
  "$PKG/usr/lib/linger-snipaste/linger-snipaste" \
  | sed -n 's/^shlibs:Depends=//p')"
[ -n "$SHLIB_DEPS" ] || fail "dpkg-shlibdeps 未能推导出依赖"

# 私有 Python 运行时 + 托盘库：dpkg-shlibdeps 不覆盖这两项
DEPS="python3 (>= 3.12), python3 (<< 3.13), libayatana-appindicator3-1, ${SHLIB_DEPS}"
sed -i "s|^Depends: DEPENDS_PLACEHOLDER|Depends: ${DEPS}|" "$PKG/DEBIAN/control"

INSTALLED_SIZE="$(du -sk "$PKG" | cut -f1)"
sed -i "s|^Installed-Size: 0|Installed-Size: ${INSTALLED_SIZE}|" "$PKG/DEBIAN/control"

echo "==> 打包"
mkdir -p "$(dirname "$OUT")"
dpkg-deb --root-owner-group --build "$PKG" "$OUT" >/dev/null

echo
echo "完成：$OUT"
echo "依赖：${DEPS}"
echo
dpkg-deb -I "$OUT" | sed -n '/Package:/,/Description:/p' | head -12
