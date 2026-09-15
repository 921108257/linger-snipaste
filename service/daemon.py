"""Desktop-owned worker. Requests travel only over inherited stdin/stdout."""
import base64
import json
import shutil
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GLib, Gtk
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from capture import Capture
from storage import Store, ServiceError
from settings import Settings


def on_main(callback):
    done = threading.Event()
    result = {}

    def run():
        try:
            result['value'] = callback()
        except Exception as exc:
            result['error'] = exc
        done.set()
        return False

    GLib.idle_add(run)
    if not done.wait(15):
        raise ServiceError('TIMEOUT', '剪贴板请求超时。')
    if 'error' in result:
        raise result['error']
    return result.get('value')


class Worker:
    def __init__(self):
        self.store = Store()
        self.capture = Capture(self.store, dbus.SessionBus())
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.settings = Settings()

    def dispatch(self, method, params):
        if method == 'status':
            return {'state': self.capture.state, 'backend': 'portal-screenshot'}
        if method == 'capture':
            shot = self.capture.screenshot(bool(params.get('interactive', False)))
            shot['auto_detect'] = self.settings.load()['autoDetect']
            self.store.path(shot['id'], '.json').write_text(json.dumps(shot, ensure_ascii=False))
            return shot
        if method == 'detect_regions':
            from detection import detect_regions
            return detect_regions(self.store.path(params['id']).read_bytes())
        if method == 'settings_get':
            return {**self.settings.load(), 'directCapture': self.capture.desktop.status()}
        if method == 'enable_direct_capture':
            return on_main(self.capture.desktop.enable)
        if method in ('settings_save', 'settings_init'):
            return on_main(lambda: self.settings.save(params if method == 'settings_save' else self.settings.load()))
        if method == 'metadata':
            return json.loads(self.store.path(params['id'], '.json').read_text())
        if method == 'image':
            return self.store.image(params['id'])
        if method == 'import':
            data = params['data'].split(',', 1)[-1]
            return self.store.save(base64.b64decode(data, validate=True), 'edited',
                                   extra={'parent_id': params.get('parent_id'),
                                          'auto_detect': self.settings.load()['autoDetect']})
        if method == 'clipboard':
            raise ServiceError('NATIVE_CLIPBOARD_REQUIRED', '请由截图窗口写入系统剪贴板。')
        if method == 'import_clipboard':
            def read():
                pixbuf = self.clipboard.wait_for_image()
                if pixbuf is None:
                    raise ServiceError('EMPTY_CLIPBOARD', '剪贴板中没有图片。')
                return bytes(pixbuf.save_to_bufferv('png', [], [])[1])
            return self.store.save(on_main(read), 'clipboard')
        if method == 'export':
            shutil.copyfile(self.store.path(params['id']), params['path'])
            return {'saved': True}
        raise ServiceError('UNKNOWN_METHOD', '不支持的操作。')


def main():
    DBusGMainLoop(set_as_default=True)
    Gtk.init([])
    worker = Worker()
    loop = GLib.MainLoop()

    def requests():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                result = {'result': worker.dispatch(request['method'], request.get('params', {}))}
            except Exception as exc:
                result = {'error': {'code': getattr(exc, 'code', 'FAILED'), 'message': str(exc)}}
            print(json.dumps(result, ensure_ascii=False), flush=True)
        GLib.idle_add(loop.quit)

    threading.Thread(target=requests, daemon=True).start()
    loop.run()


if __name__ == '__main__':
    main()
