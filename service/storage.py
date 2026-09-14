import base64
import hashlib
import io
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


class ServiceError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linger-snipaste')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def path(self, image_id, suffix='.png'):
        if not isinstance(image_id, str) or not re.fullmatch(r'[a-f0-9]{32}', image_id):
            raise ServiceError('INVALID_ID', '截图编号无效。')
        return self.root / (image_id + suffix)

    def save(self, png, source, captured_at=None, extra=None):
        if len(png) > 32 * 1024 * 1024:
            raise ServiceError('IMAGE_TOO_LARGE', '图片超过 32 MB，请缩小后再导入。')
        try:
            image = Image.open(io.BytesIO(png))
            if image.width * image.height > 40_000_000:
                raise ValueError('Too many pixels')
            image.load()
            image = image.convert('RGBA')
        except Exception as exc:
            raise ServiceError('INVALID_IMAGE', '无法读取图片，请选择 PNG、JPEG 或 WebP 文件。') from exc
        output = io.BytesIO()
        image.save(output, format='PNG')
        png = output.getvalue()
        image_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        meta = {'id': image_id, 'name': '截图 ' + datetime.now().strftime('%H-%M-%S'),
                'width': image.width, 'height': image.height, 'bytes': len(png),
                'created_at': now, 'captured_at': captured_at, 'source': source,
                'sha256': hashlib.sha256(png).hexdigest(), 'path': str(self.path(image_id)),
                **(extra or {})}
        thumb = image.copy()
        thumb.thumbnail((320, 200))
        buffer = io.BytesIO()
        thumb.save(buffer, format='PNG')
        meta['thumbnail'] = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        with self.lock:
            self.path(image_id).write_bytes(png)
            self.path(image_id).chmod(0o600)
            self.path(image_id, '.json').write_text(json.dumps(meta, ensure_ascii=False))
            self.path(image_id, '.json').chmod(0o600)
        return meta

    def history(self):
        with self.lock:
            items = []
            for file in self.root.glob('*.json'):
                try:
                    item = json.loads(file.read_text())
                    if self.path(item['id']).exists():
                        items.append(item)
                except (ValueError, KeyError, ServiceError):
                    continue
            return sorted(items, key=lambda x: x['created_at'], reverse=True)

    def image(self, image_id):
        try:
            return {'data': 'data:image/png;base64,' + base64.b64encode(self.path(image_id).read_bytes()).decode()}
        except FileNotFoundError as exc:
            raise ServiceError('NOT_FOUND', '截图已不存在，请刷新历史记录。') from exc

    def delete(self, image_id):
        with self.lock:
            self.path(image_id).unlink(missing_ok=True)
            self.path(image_id, '.json').unlink(missing_ok=True)
        return {'deleted': image_id}
