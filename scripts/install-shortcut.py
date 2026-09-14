#!/usr/bin/env python3
"""Register the saved shortcuts using the same validation as desktop settings."""
import argparse
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parent
service = here / 'service' if (here / 'service').exists() else root / 'service'
sys.path[:0] = [str(here / 'vendor'), str(service)]
from settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument('--remove', action='store_true')
args = parser.parse_args()
launcher = next((p for p in (Path('/usr/bin/linger-snipaste'), root / 'src-tauri/target/release/linger-snipaste',
                            root / 'src-tauri/target/debug/linger-snipaste') if p.exists()), None)
if launcher is None:
    raise SystemExit('请先构建桌面应用。')
settings = Settings(launcher=str(launcher))
values = settings.load()
if args.remove:
    values.update(captureShortcut='', pinShortcut='')
settings.save(values)
print('Linger 快捷键已移除。' if args.remove else 'Linger 快捷键已注册。')
