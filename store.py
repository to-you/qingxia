"""Local clipboard history. Images are stored as PNG, files as local URLs."""
import hashlib
import json
import re
import sqlite3
import time

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QUrl
from PySide6.QtGui import QImage


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def read_mime(mime):
    if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
        return 'file', json.dumps([u.toString() for u in mime.urls() if u.isLocalFile()], ensure_ascii=False), b''
    if mime.hasImage():
        data = mime.imageData()
        image = QImage.fromData(data) if isinstance(data, (QByteArray, bytes, bytearray)) else QImage(data)
        if not image.isNull():
            return 'image', f'{image.width()} × {image.height()}', png_bytes(image)
    if mime.hasText() and mime.text().strip():
        return text_payload(mime.text())
    return None


def text_payload(text):
    kind = 'link' if re.fullmatch(r'https?://\S+', text.strip()) else 'text'
    if re.fullmatch(r'#[0-9a-fA-F]{6}', text.strip()):
        kind = 'color'
    return kind, text, b''


def make_mime(item):
    mime = QMimeData()
    if item['kind'] == 'file':
        mime.setUrls([QUrl(url) for url in json.loads(item['text'])])
    elif item['kind'] == 'image':
        mime.setImageData(QImage.fromData(item['image']))
    else:
        mime.setText(item['text'])
    return mime


class History:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY, digest TEXT UNIQUE, kind TEXT, text TEXT, image BLOB,
            created REAL, source TEXT, starred INTEGER DEFAULT 0, tag TEXT DEFAULT '')''')
        self.db.execute('CREATE INDEX IF NOT EXISTS clips_created ON clips(created DESC)')
        self.db.commit()

    def add(self, payload, source='剪贴板'):
        kind, text, image = payload
        digest = hashlib.sha256(kind.encode() + text.encode('utf-8') + image).hexdigest()
        self.db.execute('''INSERT INTO clips(digest,kind,text,image,created,source) VALUES(?,?,?,?,?,?)
            ON CONFLICT(digest) DO UPDATE SET created=excluded.created, source=excluded.source''',
            (digest, kind, text, image, time.time(), source))
        self.db.execute('''DELETE FROM clips WHERE starred=0 AND id NOT IN
            (SELECT id FROM clips WHERE starred=0 ORDER BY created DESC LIMIT 200)''')
        self.db.commit()
        return self.db.execute('SELECT id FROM clips WHERE digest=?', (digest,)).fetchone()[0]

    def items(self, query='', category='all', tag=''):
        clauses, values = [], []
        if query:
            clauses.append('(instr(lower(text),lower(?))>0 OR instr(lower(tag),lower(?))>0)')
            values.extend((query, query))
        if category == 'starred':
            clauses.append('starred=1')
        elif category != 'all':
            clauses.append('kind=?')
            values.append(category)
        if tag:
            clauses.append('tag=?')
            values.append(tag)
        sql = 'SELECT * FROM clips' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
        return [dict(row) for row in self.db.execute(sql + ' ORDER BY created DESC', values)]

    def update(self, item_id, *, starred=None, tag=None):
        if starred is not None:
            self.db.execute('UPDATE clips SET starred=? WHERE id=?', (int(starred), item_id))
        if tag is not None:
            self.db.execute('UPDATE clips SET tag=? WHERE id=?', (tag, item_id))
        self.db.commit()

    def delete(self, item_id):
        self.db.execute('DELETE FROM clips WHERE id=?', (item_id,))
        self.db.commit()

    def clear(self):
        self.db.execute('DELETE FROM clips WHERE starred=0')
        self.db.commit()

    def close(self):
        self.db.close()
