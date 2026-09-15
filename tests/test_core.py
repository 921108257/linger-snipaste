import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
from PIL import Image
from storage import Store, ServiceError
from capture import Capture, read_uri


class FakeBus:
    def __init__(self, uri, code=0):
        self.uri = uri
        self.code = code
        self.closed = False
        self.removed = False
        self.options = None

    def get_unique_name(self): return ':1.9'
    def get_object(self, *args): return self
    def add_signal_receiver(self, callback, **kwargs):
        self.callback = callback
        return self
    def remove(self): self.removed = True
    def Close(self): self.closed = True
    def Screenshot(self, parent, options):
        self.options = options
        self.callback(self.code, {'uri': self.uri})
        return '/request/test'


class CoreTests(unittest.TestCase):
    def setUp(self):
        desktop = patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'test'})
        desktop.start()
        self.addCleanup(desktop.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        image = Image.new('RGB', (100, 80), '#306090')
        image.putpixel((10, 10), (255, 0, 0))
        out = io.BytesIO(); image.save(out, 'PNG'); self.png = out.getvalue()

    def tearDown(self): self.temp.cleanup()

    def test_saved_pixels_hash_and_history(self):
        import hashlib
        shot = self.store.save(self.png, 'import')
        self.assertEqual((shot['width'], shot['height']), (100, 80))
        self.assertEqual(hashlib.sha256(Path(shot['path']).read_bytes()).hexdigest(), shot['sha256'])
        self.assertEqual(len(self.store.history()), 1)
        self.store.delete(shot['id']); self.assertEqual(self.store.history(), [])

    def test_ids_cannot_escape_store(self):
        for invalid in ('../secret', '/etc/passwd', 'a'*31, None):
            with self.assertRaises(ServiceError): self.store.image(invalid)

    def test_invalid_images_rejected(self):
        with self.assertRaises(ServiceError): self.store.save(b'not an image', 'import')

    def test_portal_uri_validation(self):
        file = Path(self.temp.name) / '截图 space.png'; file.write_bytes(self.png)
        self.assertEqual(read_uri(file.as_uri()), self.png)
        for uri in ('https://example.com/a.png', 'file://remote/tmp/a', 'file:relative', 'file:///tmp/a?query=1'):
            with self.assertRaises(ServiceError): read_uri(uri)

    @patch('capture.GLib.idle_add', side_effect=lambda callback: callback())
    @patch('capture.dbus.Interface', side_effect=lambda proxy, interface: proxy)
    def test_each_capture_reads_new_portal_result_and_closes_request(self, *_):
        file = Path(self.temp.name) / 'portal.png'; file.write_bytes(self.png)
        bus = FakeBus(file.as_uri()); cap = Capture(self.store, bus)
        shot = cap.screenshot()
        self.assertEqual(Image.open(shot['path']).getpixel((10, 10)), (255,0,0,255))
        self.assertFalse(bus.options['interactive'])
        Image.new('RGB', (200, 120), 'green').save(file)
        second = cap.screenshot(interactive=True)
        self.assertEqual((second['width'],second['height']), (200,120))
        self.assertNotEqual(shot['sha256'], second['sha256'])
        self.assertTrue(bus.options['interactive'])
        self.assertTrue(bus.removed and bus.closed)
        self.assertEqual(cap.state, 'ready')

    @patch('capture.GLib.idle_add', side_effect=lambda callback: callback())
    @patch('capture.dbus.Interface', side_effect=lambda proxy, interface: proxy)
    def test_cancel_resets_state_and_writes_no_image(self, *_):
        bus = FakeBus('', code=1); cap = Capture(self.store, bus)
        with self.assertRaises(ServiceError) as error: cap.screenshot()
        self.assertEqual(error.exception.code, 'CANCELLED')
        self.assertEqual(cap.state, 'ready')
        self.assertTrue(bus.removed and bus.closed)
        self.assertEqual(self.store.history(), [])

    @patch('capture.GLib.idle_add', side_effect=lambda callback: callback())
    @patch('capture.dbus.Interface', side_effect=lambda proxy, interface: proxy)
    def test_portal_failure_cleans_up(self, *_):
        bus = FakeBus('', code=2); cap = Capture(self.store, bus)
        with self.assertRaises(ServiceError): cap.screenshot()
        self.assertEqual(cap.state, 'ready')
        self.assertTrue(bus.removed and bus.closed)

    @patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'ubuntu:GNOME'})
    def test_gnome_direct_capture_never_opens_portal_selector(self):
        cap = Capture(self.store, FakeBus(''))
        with patch.object(cap.desktop, 'screenshot', return_value={'id': 'test'}) as direct, patch.object(cap, '_request') as portal:
            self.assertEqual(cap.screenshot(), {'id': 'test'})
            direct.assert_called_once()
            portal.assert_not_called()
        self.assertEqual(cap.state, 'ready')
        with patch.object(cap.desktop, 'screenshot', side_effect=ServiceError('DIRECT_CAPTURE_UNAVAILABLE', 'enable extension')), patch.object(cap, '_request') as portal:
            with self.assertRaises(ServiceError): cap.screenshot()
            portal.assert_not_called()
        self.assertEqual(cap.state, 'ready')

    @patch('capture.GLib.idle_add', side_effect=lambda callback: callback())
    @patch('capture.dbus.Interface', side_effect=lambda proxy, interface: proxy)
    def test_portal_failure_does_not_silently_retry_interactive_mode(self, *_):
        bus = FakeBus('', code=2)
        with patch.object(bus, 'Screenshot', wraps=bus.Screenshot) as screenshot:
            with self.assertRaises(ServiceError): Capture(self.store, bus).screenshot()
            self.assertEqual(screenshot.call_count, 1)
            self.assertFalse(bus.options['interactive'])

    @patch('capture.GLib.idle_add', side_effect=lambda callback: callback())
    @patch('capture.dbus.Interface', side_effect=lambda proxy, interface: proxy)
    def test_interactive_empty_result_does_not_claim_permission_denied(self, *_):
        with self.assertRaises(ServiceError) as error:
            Capture(self.store, FakeBus('', code=2)).screenshot(interactive=True)
        self.assertIn('未返回图片', str(error.exception))
        self.assertNotIn('拒绝', str(error.exception))

    def test_private_worker_status_rejects_old_commands_and_exits_on_eof(self):
        worker = Path(__file__).resolve().parents[1] / 'service/daemon.py'
        requests = '\n'.join(json.dumps({'method': m}) for m in ('status', 'snapshot', 'start', 'history', 'clipboard')) + '\n'
        output = subprocess.run(['/usr/bin/python3', str(worker)], input=requests, text=True, capture_output=True,
                                timeout=15, env={**os.environ, 'XDG_DATA_HOME': self.temp.name})
        self.assertEqual(output.returncode, 0, output.stderr)
        responses = [json.loads(line) for line in output.stdout.splitlines()]
        self.assertEqual(responses[0]['result']['backend'], 'portal-screenshot')
        for response in responses[1:4]: self.assertEqual(response['error']['code'], 'UNKNOWN_METHOD')
        self.assertEqual(responses[4]['error']['code'], 'NATIVE_CLIPBOARD_REQUIRED')


if __name__ == '__main__': unittest.main()
