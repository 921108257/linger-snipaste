import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import dbus
from gi.repository import GLib
from storage import ServiceError


def read_uri(uri):
    parsed = urlsplit(str(uri))
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
        raise ServiceError('INVALID_URI', '系统未返回本地截图文件。')
    path = Path(unquote(parsed.path))
    if not path.is_absolute():
        raise ServiceError('INVALID_URI', '系统截图路径无效。')
    return path.read_bytes()


class Capture:
    def __init__(self, store, bus):
        self.store = store
        self.bus = bus
        self.state = 'ready'

    def screenshot(self, interactive=False):
        done = threading.Event()
        outcome = {}
        request = {}

        def response(code, results):
            if done.is_set():
                return
            if int(code) == 0:
                outcome['uri'] = results.get('uri', '')
            else:
                outcome['error'] = ServiceError('CANCELLED' if int(code) == 1 else 'CAPTURE_FAILED',
                                                '已取消截图。' if int(code) == 1 else '系统截图失败，请重试。')
            done.set()

        def start():
            try:
                self.state = 'requesting'
                token = 'linger_' + uuid.uuid4().hex
                sender = self.bus.get_unique_name()[1:].replace('.', '_')
                request['path'] = '/org/freedesktop/portal/desktop/request/' + sender + '/' + token
                request['signal'] = self.bus.add_signal_receiver(response, signal_name='Response',
                    dbus_interface='org.freedesktop.portal.Request', path=request['path'])
                portal = dbus.Interface(self.bus.get_object('org.freedesktop.portal.Desktop',
                    '/org/freedesktop/portal/desktop'), 'org.freedesktop.portal.Screenshot')
                request['path'] = str(portal.Screenshot('', dbus.Dictionary({
                    'handle_token': token, 'interactive': dbus.Boolean(interactive),
                }, signature='sv')))
            except Exception as exc:
                outcome['error'] = exc
                done.set()
            return False

        def cleanup():
            if 'signal' in request:
                request['signal'].remove()
            if 'path' in request:
                try:
                    dbus.Interface(self.bus.get_object('org.freedesktop.portal.Desktop', request['path']),
                                   'org.freedesktop.portal.Request').Close()
                except dbus.DBusException:
                    pass
            self.state = 'ready'
            return False

        GLib.idle_add(start)
        try:
            if not done.wait(120):
                done.set()
                raise ServiceError('TIMEOUT', '系统截图请求超时，请重新截图。')
            if 'error' in outcome:
                raise outcome['error']
            png = read_uri(outcome['uri'])
            return self.store.save(png, 'portal-window' if interactive else 'portal-screenshot',
                                   datetime.now(timezone.utc).isoformat())
        finally:
            GLib.idle_add(cleanup)
