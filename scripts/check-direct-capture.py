#!/usr/bin/env python3
"""Exercise real GNOME screenshot + native app on an isolated virtual display.

Requires GNOME 46 with --headless and a release app built from this checkout.
Never changes the real session's shortcuts, extensions or screen contents.
"""
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'src-tauri/target/release/linger-snipaste'
UUID = 'capture@linger-snipaste'


def until(predicate, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.25)
    raise AssertionError('Timed out waiting for native capture')


def inside():
    root = Path(os.environ['XDG_DATA_HOME']).parent
    subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', f"['{UUID}']"], check=True)
    log = (root / 'gnome.log').open('w')
    shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--no-x11',
                              '--virtual-monitor', '1280x800', '--wayland-display', 'linger-test'], stdout=log, stderr=log)
    app = None
    try:
        def extension_ready():
            result = subprocess.run(['gdbus', 'introspect', '--session', '--dest', 'org.gnome.Shell',
                '--object-path', '/app/linger/Screenshot'], capture_output=True, text=True, timeout=5)
            if shell.poll() is not None:
                raise AssertionError((root / 'gnome.log').read_text()[-5000:])
            return 'app.linger.Screenshot1' in result.stdout
        until(extension_ready)
        denied = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.gnome.Shell',
            '--object-path', '/app/linger/Screenshot', '--method', 'app.linger.Screenshot1.Capture'],
            capture_output=True, text=True, timeout=5)
        assert denied.returncode != 0 and 'Only the Linger' in denied.stderr, denied.stderr
        env = {**os.environ, 'WAYLAND_DISPLAY': 'linger-test', 'GDK_BACKEND': 'wayland'}
        app_log = (root / 'app.log').open('w')
        app = subprocess.Popen([str(BINARY), '--settings'], env=env, stdout=app_log, stderr=app_log)
        config = Path(env['XDG_CONFIG_HOME']) / 'linger-snipaste/settings.json'
        until(config.exists)
        time.sleep(2)
        start = time.monotonic()
        subprocess.run([str(BINARY), '--capture'], env=env, timeout=10, check=True)
        folder = Path(env['XDG_DATA_HOME']) / 'linger-snipaste'
        files = until(lambda: list(folder.glob('*.json')))
        shot = json.loads(files[0].read_text())
        assert shot['source'] == 'gnome-extension', shot
        assert (shot['width'], shot['height']) == (1280, 800), shot
        from PIL import Image
        image = Image.open(shot['path']); image.load()
        assert image.size == (1280, 800)
        elapsed = round((time.monotonic() - start) * 1000)
        # Calling capture again must focus the current overlay, not take a
        # second image or open the system screenshot selector.
        time.sleep(2)
        subprocess.run([str(BINARY), '--capture'], env=env, timeout=10, check=True)
        time.sleep(1)
        assert len(list(folder.glob('*.json'))) == 1
        assert app.poll() is None
        assert 'Linger window blur:' not in (root / 'gnome.log').read_text()
        print(json.dumps({'capture': 'PASS', 'source': shot['source'], 'size': image.size,
                          'elapsed_ms': elapsed, 'unauthorized_client': 'denied',
                          'duplicate_capture': 'focused existing overlay'}, ensure_ascii=False), flush=True)
    finally:
        for process in (app, shell):
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=8)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        log.close()


if '--session' in sys.argv:
    inside()
else:
    with tempfile.TemporaryDirectory(prefix='linger-gnome-check-', ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        for name in ('data', 'config', 'runtime', 'cache'):
            (root / name).mkdir(mode=0o700)
        extension = root / 'data/gnome-shell/extensions' / UUID
        shutil.copytree(ROOT / 'gnome-extension', extension)
        metadata = json.loads((extension / 'metadata.json').read_text())
        metadata['development-client'] = {'executable': str(BINARY), 'worker': str(ROOT / 'service/daemon.py')}
        (extension / 'metadata.json').write_text(json.dumps(metadata))
        env = {**os.environ, 'XDG_DATA_HOME': str(root / 'data'), 'XDG_CONFIG_HOME': str(root / 'config'),
               'XDG_RUNTIME_DIR': str(root / 'runtime'), 'XDG_CACHE_HOME': str(root / 'cache'),
               'XDG_CURRENT_DESKTOP': 'GNOME', 'XDG_SESSION_TYPE': 'wayland',
               'GSETTINGS_BACKEND': 'keyfile', 'GTK_USE_PORTAL': '0', 'GIO_USE_VFS': 'local'}
        result = subprocess.Popen(['dbus-run-session', '--', '/usr/bin/python3', str(Path(__file__).resolve()), '--session'],
                                  env=env, start_new_session=True)
        try:
            result.wait(timeout=100)
        finally:
            try: os.killpg(result.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            subprocess.run(['fusermount3', '-u', str(root / 'runtime/doc')], capture_output=True)
        if result.returncode:
            for name in ('gnome.log', 'app.log'):
                if (root / name).exists(): print((root / name).read_text()[-6000:], file=sys.stderr)
            raise SystemExit(result.returncode)
