#!/usr/bin/env python3
"""Register a GNOME custom keybinding without replacing existing bindings."""
import argparse
import shlex
from pathlib import Path
from gi.repository import Gio

parser = argparse.ArgumentParser()
parser.add_argument('--remove', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
launcher = Path('/usr/bin/linger-snipaste')
binary = next((path for path in (
    launcher,
    root / 'src-tauri/target/release/linger-snipaste',
    root / 'src-tauri/target/debug/linger-snipaste',
) if path.exists()), launcher)
binding_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linger-snipaste/'
settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
paths = list(settings.get_strv('custom-keybindings'))
schema = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
if args.remove:
    settings.set_strv('custom-keybindings', [path for path in paths if path != binding_path])
else:
    if not binary.exists(): raise SystemExit('Build the desktop binary before installing F1.')
    for path in paths:
        existing = Gio.Settings.new_with_path(schema, path)
        if path != binding_path and existing.get_string('binding') == 'F1':
            raise SystemExit('F1 is already assigned to ' + existing.get_string('name') + '. Existing binding was preserved.')
    binding = Gio.Settings.new_with_path(schema, binding_path)
    binding.set_string('name', 'Linger 截图')
    binding.set_string('command', shlex.quote(str(binary)) + ' --capture')
    binding.set_string('binding', 'F1')
    if binding_path not in paths: settings.set_strv('custom-keybindings', paths + [binding_path])
Gio.Settings.sync()
print('Linger F1 removed.' if args.remove else 'Linger F1 registered. Existing shortcuts preserved.')
