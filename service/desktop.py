"""GNOME's explicitly enabled desktop extension supplies single-shot pixels."""
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import dbus
from gi.repository import Gio, GLib
from storage import ServiceError

UUID = 'capture@linger-snipaste'
INTERFACE = 'app.linger.Screenshot1'


class DesktopCapture:
    def __init__(self, store, bus):
        self.store = store
        self.bus = bus

    def status(self):
        if 'gnome' not in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            return {'state': 'unsupported', 'message': '当前桌面使用系统截图通道。'}
        try:
            extensions = dbus.Interface(self.bus.get_object('org.gnome.Shell.Extensions',
                '/org/gnome/Shell/Extensions'), 'org.gnome.Shell.Extensions')
            info = extensions.GetExtensionInfo(UUID, timeout=3)
            if not info:
                installed = any((p / UUID / 'metadata.json').exists() for p in (
                    Path('/usr/share/gnome-shell/extensions'),
                    Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'gnome-shell/extensions'))
                return {'state': 'needs-login' if installed else 'missing',
                        'message': '桌面扩展已安装，请注销并重新登录一次。' if installed else '请安装包含桌面扩展的新版 Linger 安装包。'}
            state = int(info.get('state', 0))
            if state == 1:
                return {'state': 'ready', 'message': 'F1 直接进入 Linger 选区。'}
            if state in (3, 4):
                return {'state': 'error', 'message': str(info.get('error') or '桌面扩展与当前 GNOME 版本不兼容。')}
            return {'state': 'disabled', 'message': '启用桌面扩展后，F1 直接进入 Linger 选区。'}
        except dbus.DBusException as exc:
            return {'state': 'error', 'message': '无法连接 GNOME 桌面扩展服务：' + str(exc)}

    def enable(self):
        current = self.status()
        if current['state'] in ('unsupported', 'missing', 'error'):
            raise ServiceError('EXTENSION_UNAVAILABLE', current['message'])
        settings = Gio.Settings.new('org.gnome.shell')
        if not all(settings.is_writable(key) for key in ('enabled-extensions', 'disabled-extensions')):
            raise ServiceError('EXTENSIONS_LOCKED', '系统已锁定扩展设置。')
        if settings.get_boolean('disable-user-extensions'):
            raise ServiceError('EXTENSIONS_DISABLED', '系统已停用桌面扩展，请先在系统“扩展”应用中开启。')
        enabled = list(settings.get_strv('enabled-extensions'))
        disabled = list(settings.get_strv('disabled-extensions'))
        if UUID not in enabled:
            if not settings.set_strv('enabled-extensions', enabled + [UUID]):
                raise ServiceError('EXTENSIONS_LOCKED', '系统已锁定扩展设置。')
        if UUID in disabled:
            if not settings.set_strv('disabled-extensions', [x for x in disabled if x != UUID]):
                settings.set_strv('enabled-extensions', enabled)
                raise ServiceError('EXTENSIONS_LOCKED', '系统已锁定扩展设置。')
        Gio.Settings.sync()
        return {'state': 'needs-login' if current['state'] == 'needs-login' else 'enabling',
                'message': '已启用。请注销并重新登录一次。' if current['state'] == 'needs-login' else '正在启用桌面截图…'}

    def screenshot(self):
        current = self.status()
        if current['state'] != 'ready':
            raise ServiceError('DIRECT_CAPTURE_UNAVAILABLE', current['message'])
        done = threading.Event()
        outcome = {}
        def success(png):
            if not done.is_set():
                outcome['png'] = bytes(png)
                done.set()
        def failure(error):
            if not done.is_set():
                outcome['error'] = error
                done.set()
        def start():
            try:
                extension = dbus.Interface(self.bus.get_object('org.gnome.Shell', '/app/linger/Screenshot'), INTERFACE)
                extension.Capture(reply_handler=success, error_handler=failure, byte_arrays=True, timeout=10)
            except Exception as exc:
                failure(exc)
            return False
        GLib.idle_add(start)
        if not done.wait(12):
            done.set()
            raise ServiceError('TIMEOUT', '桌面截图超时，请检查 Linger 桌面扩展。')
        if 'error' in outcome:
            raise ServiceError('CAPTURE_FAILED', '桌面截图失败：' + str(outcome['error']))
        return self.store.save(outcome['png'], 'gnome-extension', datetime.now(timezone.utc).isoformat())
