import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const INTERFACE = `<node><interface name="app.linger.Screenshot1">
  <method name="Capture"><arg type="ay" direction="out" name="png"/></method>
</interface></node>`;
const decoder = new TextDecoder();
const read = path => decoder.decode(GLib.file_get_contents(path)[1]);

export default class LingerCapture extends Extension {
    enable() {
        this._active = true;
        this._busy = false;
        this._lockdown = new Gio.Settings({schema_id: 'org.gnome.desktop.lockdown'});
        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._dbus.export(Gio.DBus.session, '/app/linger/Screenshot');
        this._glass = new Map();
        this._mapSignal = global.window_manager.connect('map', (_manager, actor) => this._addGlass(actor));
        for (const actor of global.get_window_actors()) this._addGlass(actor);
    }

    _addGlass(actor) {
        try {
            const window = actor.meta_window;
            if (window?.get_title() !== 'Linger 设置' || this._glass.has(actor)) return;
            const executable = GLib.file_read_link(`/proc/${window.get_pid()}/exe`);
            if (executable !== '/usr/lib/linger-snipaste/linger-snipaste' &&
                executable !== this.metadata['development-client']?.executable) return;
            const glass = new St.Widget({reactive: false});
            glass.add_effect(new Shell.BlurEffect({radius: 48 * St.ThemeContext.get_for_stage(global.stage).scale_factor,
                brightness: 1, mode: Shell.BlurMode.BACKGROUND}));
            actor.insert_child_at_index(glass, 0);
            const resize = () => { glass.set_position(0, 0); glass.set_size(actor.width, actor.height); };
            const allocation = actor.connect('notify::allocation', resize);
            const destroyed = actor.connect('destroy', () => this._glass.delete(actor));
            this._glass.set(actor, {glass, allocation, destroyed});
            resize();
        } catch (error) { console.warn(`Linger window blur: ${error.message}`); }
    }

    disable() {
        this._active = false;
        this._dbus?.unexport();
        this._dbus = null;
        this._lockdown = null;
        if (this._mapSignal) global.window_manager.disconnect(this._mapSignal);
        this._mapSignal = null;
        for (const [actor, {glass, allocation, destroyed}] of this._glass) {
            actor.disconnect(allocation);
            actor.disconnect(destroyed);
            glass.destroy();
        }
        this._glass.clear();
    }

    async _checkClient(sender) {
        const pid = await new Promise((resolve, reject) => {
            Gio.DBus.session.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus', 'GetConnectionUnixProcessID',
                new GLib.Variant('(s)', [sender]), new GLib.VariantType('(u)'),
                Gio.DBusCallFlags.NONE, 2000, null, (connection, result) => {
                    try { resolve(connection.call_finish(result).deepUnpack()[0]); }
                    catch (error) { reject(error); }
                });
        });
        const parent = read(`/proc/${pid}/status`).match(/^PPid:\s*(\d+)/m)?.[1];
        if (!parent) throw new Error('Invalid client process');
        const executable = GLib.file_read_link(`/proc/${parent}/exe`);
        const args = read(`/proc/${pid}/cmdline`).split('\0');
        const worker = GLib.canonicalize_filename(args[1] || '', null);
        const installed = executable === '/usr/lib/linger-snipaste/linger-snipaste' &&
            worker === '/usr/lib/linger-snipaste/service/daemon.py';
        // Development builds may opt in through their local extension metadata.
        const development = this.metadata['development-client'];
        const developing = development && executable === development.executable && worker === development.worker;
        if (!installed && !developing) throw new Error('Only the Linger desktop worker may capture');
    }

    async CaptureAsync(_params, invocation) {
        let stream;
        let ownsCapture = false;
        try {
            await this._checkClient(invocation.get_sender());
            if (!this._active || Main.sessionMode.isLocked || Main.sessionMode.isGreeter)
                throw new Error('Desktop is locked or capture is disabled');
            if (this._lockdown.get_boolean('disable-save-to-disk'))
                throw new Error('Screenshot saving is disabled by desktop policy');
            if (this._busy) throw new Error('A capture is already running');
            this._busy = true;
            ownsCapture = true;
            stream = Gio.MemoryOutputStream.new_resizable();
            const screenshot = new Shell.Screenshot();
            // GNOME already promisifies this API in ui/screenshot.js. Capture
            // current pixels once; never open ScreenshotUI or a screen stream.
            await screenshot.screenshot(false, stream);
            stream.close(null);
            const bytes = stream.steal_as_bytes();
            if (!this._active) throw new Error('Capture extension was disabled');
            if (bytes.get_size() > 32 * 1024 * 1024) throw new Error('Screenshot exceeds 32 MB');
            invocation.return_value(new GLib.Variant('(ay)', [bytes.get_data()]));
        } catch (error) {
            invocation.return_dbus_error('app.linger.Screenshot1.Failed', error.message);
        } finally {
            if (stream && !stream.is_closed()) stream.close(null);
            if (ownsCapture) this._busy = false;
        }
    }
}
