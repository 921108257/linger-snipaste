import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1] / 'service'
sys.path.insert(0, str(SERVICE))
from settings import normalize
from storage import ServiceError


class SettingsTests(unittest.TestCase):
    def test_invalid_global_keys_rejected(self):
        for value in ('a', 'space', 'not-a-real-key', '<Shift>a', None):
            with self.assertRaises(ServiceError): normalize(value)
        self.assertEqual(normalize('F1'), 'F1')
        self.assertEqual(normalize('<Control><Shift>a'), '<Primary><Shift>a')

    def test_gnome_registration_persistence_conflict_and_rollback(self):
        # One worker retains a private memory GSettings backend; real user
        # bindings and autostart entries are never touched by this test.
        with tempfile.TemporaryDirectory() as root:
            code = '''
import json, sys
sys.path.insert(0, sys.argv[1])
from gi.repository import Gio
from settings import Settings, SCHEMA, CUSTOM, PATHS
from storage import ServiceError
s = Settings(launcher='/tmp/a path/linger')
v = s.save({'captureShortcut': '<Control><Shift>F9', 'pinShortcut': 'F10', 'autoDetect': False, 'autostart': False})
assert s.load()['autoDetect'] is False
assert 'Hidden=true' in s.autostart.read_text()
assert '--background' in s.autostart.read_text()
binding = Gio.Settings.new_with_path(CUSTOM, PATHS['captureShortcut'])
assert binding.get_string('command') == "'/tmp/a path/linger' --capture"
foreign = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/other/'
item = Gio.Settings.new_with_path(CUSTOM, foreign)
item.set_string('name', 'Other'); item.set_string('binding', 'F11')
parent = Gio.Settings.new(SCHEMA)
parent.set_strv('custom-keybindings', list(parent.get_strv('custom-keybindings')) + [foreign])
before = s.file.read_bytes()
try:
    s.save({**v, 'captureShortcut': 'F11'})
    raise AssertionError('conflict accepted')
except ServiceError as e:
    assert e.code == 'SHORTCUT_CONFLICT'
assert s.file.read_bytes() == before
assert item.get_string('binding') == 'F11'
from unittest.mock import patch
startup_before = s.autostart.read_bytes()
binding_before = binding.get_string('binding')
with patch('pathlib.Path.replace', side_effect=OSError('disk write failed')):
    try:
        s.save({**v, 'captureShortcut': 'F12', 'autostart': True})
        raise AssertionError('write failure ignored')
    except OSError:
        pass
assert binding.get_string('binding') == binding_before
assert s.file.read_bytes() == before
assert s.autostart.read_bytes() == startup_before
s.save({**v, 'captureShortcut': '', 'pinShortcut': ''})
assert list(parent.get_strv('custom-keybindings')) == [foreign]
print('ok')
'''
            result = subprocess.run(['/usr/bin/python3', '-c', code, str(SERVICE)], capture_output=True, text=True, timeout=15,
                env={**os.environ, 'GSETTINGS_BACKEND': 'memory', 'XDG_CURRENT_DESKTOP': 'GNOME', 'XDG_CONFIG_HOME': root})
            self.assertEqual(result.returncode, 0, result.stderr)
