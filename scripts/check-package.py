#!/usr/bin/env python3
"""Smoke-test an extracted package with system Python site packages disabled."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve() / 'usr/lib/linger-snipaste'
with tempfile.TemporaryDirectory() as temporary:
    env = {**os.environ, 'PYTHONPATH': str(root / 'vendor'), 'XDG_DATA_HOME': temporary,
           'XDG_CONFIG_HOME': temporary, 'GSETTINGS_BACKEND': 'memory'}
    # -S is intentional: missing extension modules must not resolve from the
    # developer's /usr/lib/python3/dist-packages and conceal packaging defects.
    probe = '''
import gi, dbus, PIL, cairo, cv2, numpy, _dbus_bindings, _dbus_glib_bindings
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import io
from PIL import Image
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from detection import detect_regions
image = Image.new('RGB', (200, 100), 'white'); out = io.BytesIO(); image.save(out, 'PNG')
assert detect_regions(out.getvalue()) == []
for module in (gi, dbus, PIL, cairo, cv2, numpy, _dbus_bindings, _dbus_glib_bindings):
    assert '/vendor/' in module.__file__, module.__file__
print('private runtime: OK')
'''
    subprocess.run(['/usr/bin/python3', '-S', '-c', probe, str(root / 'service')], check=True, env=env)
    messages = '\n'.join(json.dumps({'method': name}) for name in ('status', 'settings_get', 'snapshot')) + '\n'
    result = subprocess.run(['/usr/bin/python3', '-S', str(root / 'service/daemon.py')], input=messages,
                            capture_output=True, text=True, env=env, timeout=20, check=True)
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]['result']['state'] == 'ready', result
    assert responses[1]['result']['captureShortcut'] == 'F1', result
    assert responses[2]['error']['code'] == 'UNKNOWN_METHOD', result
    print('packaged worker, settings, private protocol: OK')
