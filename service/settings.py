"""User preferences and GNOME shortcuts. Never replace another app's binding."""
import json
import os
import shlex
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, Gtk, Gdk
from storage import ServiceError

DEFAULTS = {'captureShortcut': 'F1', 'pinShortcut': 'F2', 'autoDetect': True, 'autostart': True}
SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys'
CUSTOM = SCHEMA + '.custom-keybinding'
PATHS = {
    'captureShortcut': '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linger-snipaste/',
    'pinShortcut': '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linger-snipaste-pin/',
}


def normalize(value):
    if not isinstance(value, str):
        raise ServiceError('INVALID_SHORTCUT', '快捷键格式无效。')
    if not value:
        return ''
    key, modifiers = Gtk.accelerator_parse(value)
    if not key or not Gtk.accelerator_valid(key, modifiers):
        raise ServiceError('INVALID_SHORTCUT', '请使用功能键或包含 Ctrl、Alt、Super 的组合键。')
    # Bare letters would steal normal typing across the entire desktop.
    name = Gtk.accelerator_name(key, 0)
    if not modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK) and not (name.startswith('F') and name[1:].isdigit()):
        raise ServiceError('INVALID_SHORTCUT', '单键快捷键仅支持 F1–F35。')
    return Gtk.accelerator_name(key, modifiers)


class Settings:
    def __init__(self, root=None, launcher=None):
        self.root = Path(root or os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        self.file = self.root / 'linger-snipaste/settings.json'
        self.autostart = self.root / 'autostart/linger-snipaste.desktop'
        self.launcher = launcher or os.environ.get('LINGER_LAUNCHER', '/usr/bin/linger-snipaste')
        source = Gio.SettingsSchemaSource.get_default()
        self.supported = bool(source and source.lookup(SCHEMA, True) and
                              'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower())

    def load(self):
        values = DEFAULTS.copy()
        if self.file.exists():
            try:
                stored = json.loads(self.file.read_text())
                values.update({key: stored[key] for key in DEFAULTS if key in stored})
            except (ValueError, TypeError) as exc:
                raise ServiceError('INVALID_SETTINGS', '设置文件无法读取，请检查 ' + str(self.file)) from exc
        return {**values, 'shortcutsSupported': self.supported}

    def _prepare_shortcuts(self, values):
        if not self.supported:
            if any(values[k] != self.load()[k] for k in PATHS):
                raise ServiceError('UNSUPPORTED_DESKTOP', '当前桌面请在系统键盘设置中配置截图和贴图快捷键。')
            return []
        settings = Gio.Settings.new(SCHEMA)
        if not settings.is_writable('custom-keybindings'):
            raise ServiceError('LOCKED_SHORTCUTS', '系统快捷键设置已锁定。')
        paths = list(settings.get_strv('custom-keybindings'))
        used = {}
        for path in paths:
            if path in PATHS.values():
                continue
            item = Gio.Settings.new_with_path(CUSTOM, path)
            key, mods = Gtk.accelerator_parse(item.get_string('binding'))
            used[Gtk.accelerator_name(key, mods)] = item.get_string('name')
        source = Gio.SettingsSchemaSource.get_default()
        for schema_id in ('org.gnome.desktop.wm.keybindings', 'org.gnome.mutter.keybindings',
                          'org.gnome.mutter.wayland.keybindings', 'org.gnome.shell.keybindings', SCHEMA):
            schema = source.lookup(schema_id, True)
            if not schema:
                continue
            item = Gio.Settings.new(schema_id)
            for name in schema.list_keys():
                if name == 'custom-keybindings':
                    continue
                value = item.get_value(name)
                if value.get_type_string() not in ('as', 's'):
                    continue
                entries = value.unpack() if value.get_type_string() == 'as' else [value.unpack()]
                for binding in entries:
                    key, mods = Gtk.accelerator_parse(binding)
                    if key:
                        used[Gtk.accelerator_name(key, mods)] = name
        changes = []
        for name, path in PATHS.items():
            binding = values[name]
            if binding and binding in used:
                raise ServiceError('SHORTCUT_CONFLICT', f'{binding} 已用于“{used[binding]}”，请选择其他快捷键。')
            item = Gio.Settings.new_with_path(CUSTOM, path)
            for key, value in {'name': 'Linger 截图' if name == 'captureShortcut' else 'Linger 贴图',
                               'binding': binding,
                               'command': shlex.quote(self.launcher) + (' --capture' if name == 'captureShortcut' else ' --pin')}.items():
                if not item.is_writable(key):
                    raise ServiceError('LOCKED_SHORTCUTS', '系统快捷键设置已锁定。')
                changes.append((item, key, value))
            if binding and path not in paths:
                paths.append(path)
            if not binding and path in paths:
                paths.remove(path)
        changes.append((settings, 'custom-keybindings', paths))
        return changes

    def save(self, params):
        current = self.load()
        values = {key: params.get(key, current[key]) for key in DEFAULTS}
        for key in PATHS:
            values[key] = normalize(values[key])
        if values['captureShortcut'] and values['captureShortcut'] == values['pinShortcut']:
            raise ServiceError('SHORTCUT_CONFLICT', '截图和贴图不能使用相同的快捷键。')
        for key in ('autoDetect', 'autostart'):
            if not isinstance(values[key], bool):
                raise ServiceError('INVALID_SETTINGS', '设置值无效。')
        changes = self._prepare_shortcuts(values)
        # Prepare filesystem writes before touching the user's live shortcuts.
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.autostart.parent.mkdir(parents=True, exist_ok=True)
        config_before = self.file.read_bytes() if self.file.exists() else None
        startup_before = self.autostart.read_bytes() if self.autostart.exists() else None
        previous = [(item, key, item.get_user_value(key)) for item, key, _ in changes]
        try:
            # Desktop Exec has its own quoting rules, not shell quoting.
            command = self.launcher.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
            self.autostart.write_text('[Desktop Entry]\nType=Application\nName=Linger 截图\n'
                f'Exec="{command}" --background\nIcon=linger-snipaste\nTerminal=false\n'
                f'Hidden={str(not values["autostart"]).lower()}\nX-GNOME-Autostart-enabled={str(values["autostart"]).lower()}\n')
            for item, key, value in changes:
                ok = item.set_strv(key, value) if isinstance(value, list) else item.set_string(key, value)
                if not ok:
                    raise ServiceError('SAVE_FAILED', '系统未能保存快捷键。')
            temporary = self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
            temporary.replace(self.file)
            Gio.Settings.sync()
        except Exception:
            for item, key, value in previous:
                item.reset(key) if value is None else item.set_value(key, value)
            for path, contents in ((self.file, config_before), (self.autostart, startup_before)):
                path.unlink(missing_ok=True) if contents is None else path.write_bytes(contents)
            Gio.Settings.sync()
            raise
        return self.load()
