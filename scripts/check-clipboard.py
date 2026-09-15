#!/usr/bin/env python3
"""Real cross-process clipboard check on a disposable GNOME Wayland session.

Build the Rust example first: cargo build --manifest-path src-tauri/Cargo.toml --example clipboard_probe
No clipboard data, focus, or settings in the user's desktop are touched.
"""
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'src-tauri/target/debug/examples/clipboard_probe'


def until(predicate, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if result := predicate(): return result
        time.sleep(.1)
    raise AssertionError('Timed out waiting for clipboard test')


def receiver():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    window = Gtk.Window(title='Independent paste target')
    window.set_default_size(320, 200)
    window.show_all()
    def read():
        if not window.is_active(): return True
        print('Paste target focused; requesting image', file=sys.stderr, flush=True)
        def received(_clipboard, pixbuf, _data):
            if pixbuf is None:
                print(json.dumps({'image': None}), flush=True)
            else:
                encoded = bytes(pixbuf.save_to_bufferv('png', [], [])[1])
                image = Image.open(io.BytesIO(encoded)).convert('RGBA')
                print(json.dumps({'size': image.size, 'pixel': image.getpixel((0, 0))}), flush=True)
            Gtk.main_quit()
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).request_image(received, None)
        return False
    GLib.timeout_add(200, read)
    Gtk.main()


def session():
    root = Path(os.environ['XDG_RUNTIME_DIR']).parent
    subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', "['clipboard-test@linger']"], check=True)
    processes = []
    with (root / 'gnome.log').open('w') as log:
        try:
            shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--no-x11',
                '--virtual-monitor', '1280x800', '--wayland-display', 'linger-clipboard-test'], stdout=log, stderr=log)
            processes.append(shell)
            until(lambda: Path(os.environ['XDG_RUNTIME_DIR'], 'linger-clipboard-test').exists())
            fixture = root / 'fixture.png'
            Image.new('RGBA', (73, 41), (48, 96, 144, 255)).save(fixture)
            env = {**os.environ, 'WAYLAND_DISPLAY': 'linger-clipboard-test', 'GDK_BACKEND': 'wayland'}
            # Reproduce v0.4.0: a live GTK worker has no focused window or serial.
            legacy_code = '''
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf
import sys
Gtk.init([])
clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
clipboard.set_image(GdkPixbuf.Pixbuf.new_from_file(sys.argv[1]))
clipboard.store()
print('copied', flush=True)
Gtk.main()
'''
            legacy = subprocess.Popen(['/usr/bin/python3', '-c', legacy_code, str(fixture)], env=env,
                                      stdout=subprocess.PIPE, text=True)
            processes.append(legacy)
            # Do not mistake the old helper's success response for a paste test.
            assert legacy.stdout.readline().strip() == 'copied'
            def paste():
                try:
                    result = subprocess.run(['/usr/bin/python3', str(Path(__file__).resolve()), '--receiver'],
                        env=env, capture_output=True, text=True, timeout=15, check=True)
                except subprocess.TimeoutExpired as exc:
                    print('Receiver diagnostics:', exc.stderr, file=sys.stderr)
                    raise
                return json.loads(result.stdout)
            old = paste()
            assert old == {'image': None}, old
            legacy.terminate(); legacy.wait(timeout=5)
            results = []
            # Replace ownership twice, close each source window, then paste in
            # another process. Read pixels, not the sender's own cached image.
            for n, color in enumerate(((48, 96, 144, 255), (180, 40, 70, 255))):
                Image.new('RGBA', (73, 41), color).save(fixture)
                ready = root / f'copied-{n}'
                owner = subprocess.Popen([str(PROBE), str(fixture), str(ready)], env=env)
                processes.append(owner)
                until(ready.exists)
                actual = paste()
                assert actual == {'size': [73, 41], 'pixel': list(color)}, actual
                assert owner.poll() is None
                results.append(actual)
            print(json.dumps({'legacy_worker': 'reproduced false success',
                'native_owner': 'PASS after source window closes', 'pastes': results}), flush=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()


if '--receiver' in sys.argv:
    receiver()
elif '--session' in sys.argv:
    session()
else:
    with tempfile.TemporaryDirectory(prefix='linger-clipboard-check-', ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        for name in ('data', 'config', 'runtime', 'cache'): (root / name).mkdir(mode=0o700)
        # Suppress GNOME's startup overview only inside this disposable session
        # so test windows can receive focus normally without physical input.
        extension = root / 'data/gnome-shell/extensions/clipboard-test@linger'
        extension.mkdir(parents=True)
        (extension / 'metadata.json').write_text(json.dumps({'uuid': 'clipboard-test@linger',
            'name': 'Clipboard test setup', 'description': 'Disposable test session', 'shell-version': ['46']}))
        (extension / 'extension.js').write_text('''
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
export default class Test extends Extension {
    enable() {
        this.keyboard = Clutter.get_default_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        Main.layoutManager.connectObject('startup-complete', () => Main.overview.hide(), this);
        Main.overview.hide();
    }
    disable() { Main.layoutManager.disconnectObject(this); this.keyboard = null; }
}
''')
        env = {**os.environ, **{f'XDG_{name.upper()}_HOME': str(root / name) for name in ('data', 'config', 'cache')},
               'XDG_RUNTIME_DIR': str(root / 'runtime'), 'XDG_CURRENT_DESKTOP': 'GNOME',
               'XDG_SESSION_TYPE': 'wayland', 'GNOME_SHELL_SESSION_MODE': 'gnome',
               'WAYLAND_DISPLAY': 'linger-clipboard-test', 'GSETTINGS_BACKEND': 'keyfile', 'GTK_USE_PORTAL': '0', 'GIO_USE_VFS': 'local'}
        runner = subprocess.Popen(['dbus-run-session', '--', '/usr/bin/python3', str(Path(__file__).resolve()), '--session'],
                                  env=env, start_new_session=True)
        try: runner.wait(timeout=100)
        finally:
            try: os.killpg(runner.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            subprocess.run(['fusermount3', '-u', str(root / 'runtime/doc')], capture_output=True)
        if runner.returncode:
            if (root / 'gnome.log').exists(): print((root / 'gnome.log').read_text()[-4000:], file=sys.stderr)
            raise SystemExit(runner.returncode)
