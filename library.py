"""Local history, independent of the original audio folder's write permission."""
import hashlib
import json
import math
import os
import uuid
from datetime import datetime
from pathlib import Path


def valid_rows(rows):
    try:
        return isinstance(rows, list) and all(
            isinstance(r['text'], str) and math.isfinite(r['start']) and
            math.isfinite(r['end']) and 0 <= r['start'] < r['end'] for r in rows)
    except (KeyError, TypeError, ValueError):
        return False


class Library:
    def __init__(self, root=None):
        self.root = Path(root or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Kotoba' / 'history')
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, path):
        return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode()).hexdigest()

    def entries(self):
        entries = []
        for file in self.root.glob('*.json'):
            try:
                record = json.loads(file.read_text(encoding='utf-8'))
                if valid_rows(record['sentences']) and isinstance(record['path'], str):
                    entries.append(record)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(entries, key=lambda r: r.get('updated', ''), reverse=True)

    def find(self, path):
        return next((r for r in self.entries() if self.key(r['path']) == self.key(path)), None)

    def save(self, path, rows, position=0, previous=None):
        if not valid_rows(rows):
            raise ValueError('Invalid sentence timestamps')
        record = dict(previous or {})
        # Progress/transcription saves must not overwrite newer library edits.
        latest = self.find(path) or {}
        for field in ('title', 'favorite', 'category'):
            if field in latest:
                record[field] = latest[field]
        audio = Path(path)
        if audio.exists():
            stat = audio.stat()
            record.update(size=stat.st_size, mtime=stat.st_mtime_ns)
        record.update(path=str(audio.resolve()), sentences=rows, position=max(0, int(position)),
                      updated=datetime.now().isoformat(timespec='seconds'))
        target = self.root / (self.key(path) + '.json')
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(target)
        return record

    def edit(self, path, **fields):
        record = self.find(path)
        if record is None:
            raise ValueError('请先完成转写，再管理收藏。')
        record.update({k: v for k, v in fields.items() if k in ('title', 'favorite', 'category')})
        target = self.root / (self.key(path) + '.json')
        self.write_json(target, record)
        return record

    @staticmethod
    def write_json(target, data):
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(target)

    def categories(self):
        try:
            return json.loads((self.root / '_collections.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def set_category(self, name, key=None):
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError('分类名称需为 1–60 个字符。')
        categories = self.categories()
        if any(v.casefold() == name.casefold() and k != key for k, v in categories.items()):
            raise ValueError('已有同名分类。')
        key = key or uuid.uuid4().hex
        categories[key] = name
        self.write_json(self.root / '_collections.json', categories)
        return key

    def delete_category(self, key):
        categories = self.categories()
        categories.pop(key, None)
        for record in self.entries():
            if record.get('category') == key:
                self.edit(record['path'], category=None)
        self.write_json(self.root / '_collections.json', categories)

    def matches(self, record, path):
        try:
            stat = Path(path).stat()
            return record['size'] == stat.st_size and record['mtime'] == stat.st_mtime_ns
        except (OSError, KeyError):
            return False

    def import_sidecar(self, file):
        path = str(file)[:-len('.kotoba.json')]
        record = json.loads(Path(file).read_text(encoding='utf-8'))
        if not valid_rows(record['sentences']) or not self.matches(record, path):
            raise ValueError('音频已改变或记录格式不正确')
        return self.save(path, record['sentences'], previous=record)
