"""Plugin-owned immutable cover history; never deletes media-server images."""
import array
import hashlib
import io
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from filelock import FileLock
from PIL import Image

from .encoding import cover_directory


class CoverHistory:
    def __init__(self):
        self.root = cover_directory() / 'history'
        if self.root.is_symlink():
            raise ValueError('历史目录不能是链接')
        self.root.mkdir(exist_ok=True)
        self.lock = FileLock(str(self.root / '.lock'))

    @contextmanager
    def db(self):
        path = self.root / 'index.sqlite'
        if path.is_symlink():
            raise ValueError('历史索引不能是链接')
        db = sqlite3.connect(path)
        db.execute('create table if not exists covers (id text primary key, payload text not null)')
        db.execute('create table if not exists counters (key text primary key, value integer not null)')
        db.execute('create table if not exists imported (key text primary key)')
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_latest(self, records, config):
        from pathlib import Path
        output = (cover_directory() / 'output').resolve()
        for record in records:
            result = record.get('result') or {}
            raw = result.get('output_path')
            server = (record.get('payload') or {}).get('server_id')
            if not raw or not server or result.get('status') not in {'updated','preview'}:
                continue
            path = Path(raw)
            if path.is_symlink() or path.resolve().parent != output or not path.is_file() or path.stat().st_size > 20*1024*1024:
                continue
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != result.get('sha256'):
                continue
            token = f"{server}:{result.get('library_id')}:{result['sha256']}"
            self.add(data,{**result,'created_at':record.get('updated_at')},server,config,imported=token)

    def path(self, identity, suffix):
        if not re.fullmatch('[0-9a-f]{32}', str(identity)) or suffix not in {'jpg','png','gif','webp','thumb.jpg'}:
            raise ValueError('历史封面标识无效')
        path = self.root / f'{identity}.{suffix}'
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise ValueError('历史封面路径无效')
        return path

    def rows(self, db):
        return [json.loads(row[0]) for row in db.execute('select payload from covers')]

    def add(self, data, result, server, config, *, imported=None):
        with self.lock, self.db() as db:
            if imported and db.execute('select 1 from imported where key=?',(imported,)).fetchone():
                return
            status = result.get('status', 'preview')
            for key in ('generated', 'uploaded' if status == 'updated' else 'preview'):
                db.execute('insert into counters values (?,1) on conflict(key) do update set value=value+1',(key,))
            token = imported or f"{server}:{result.get('library_id')}:{hashlib.sha256(data).hexdigest()}"
            db.execute('insert or ignore into imported values (?)',(token,))
            if not config.get('save_recent_covers', True):
                return
            identity = uuid4().hex
            fmt = result.get('format', 'jpeg')
            suffix = {'jpeg':'jpg','apng':'png','gif':'gif','webp':'webp'}[fmt]
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                animated = bool(getattr(image, 'is_animated', False))
                thumb = image.convert('RGB'); thumb.thumbnail((640,360))
                output = io.BytesIO(); thumb.save(output,format='JPEG',quality=85)
            row = {**result,'id':identity,'server_id':server,'suffix':suffix,'animated':animated,
                   'created_at':result.get('created_at') or datetime.now(timezone.utc).isoformat(),
                   'resolution':f'{width}×{height}','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            row.pop('output_path',None)
            self.path(identity,suffix).write_bytes(data)
            self.path(identity,'thumb.jpg').write_bytes(output.getvalue())
            db.execute('insert into covers values (?,?)',(identity,json.dumps(row)))
            limit = min(100,max(1,int(config.get('covers_history_limit_per_library') or 10)))
            siblings = sorted([x for x in self.rows(db) if x['server_id']==server and x['library_id']==row['library_id']],key=lambda x:(x['created_at'],x['id']),reverse=True)
            for old in siblings[limit:]:
                self._delete(db,old)

    def failure(self):
        with self.lock, self.db() as db:
            db.execute("insert into counters values ('failed',1) on conflict(key) do update set value=value+1")

    def listing(self, config):
        with self.lock, self.db() as db:
            limit = min(500,max(10,int(config.get('covers_page_history_limit') or 50)))
            rows = sorted(self.rows(db),key=lambda x:(x['created_at'],x['id']),reverse=True)
            return {'items':rows[:limit], 'limit':limit,'total':len(rows),
                    'counts':dict(db.execute('select key,value from counters'))}

    def _delete(self,db,row):
        self.path(row['id'],row['suffix']).unlink(missing_ok=True)
        self.path(row['id'],'thumb.jpg').unlink(missing_ok=True)
        db.execute('delete from covers where id=?',(row['id'],))

    def delete(self, identities):
        if not isinstance(identities,list) or not 1<=len(identities)<=500:
            raise ValueError('请选择要清理的历史封面')
        for identity in identities:
            self.path(identity,'jpg')
        with self.lock, self.db() as db:
            rows = [x for x in self.rows(db) if x['id'] in set(identities)]
            for row in rows:
                self._delete(db,row)
            return {'deleted':len(rows)}

    def read(self, identity, thumbnail=False):
        self.path(identity,'jpg')
        with self.lock, self.db() as db:
            found = db.execute('select payload from covers where id=?',(identity,)).fetchone()
            if not found:
                raise ValueError('历史封面已清理，请刷新列表')
            row = json.loads(found[0])
            return row,self.path(identity,'thumb.jpg' if thumbnail else row['suffix']).read_bytes()

    def applied(self, identity):
        with self.lock, self.db() as db:
            found=db.execute('select payload from covers where id=?',(identity,)).fetchone()
            if not found:
                return
            row=json.loads(found[0])
            if row['status']=='preview':
                db.execute("insert into counters values ('uploaded',1) on conflict(key) do update set value=value+1")
                db.execute("update counters set value=max(0,value-1) where key='preview'")
            row['status']='updated'
            db.execute('update covers set payload=? where id=?',(json.dumps(row),identity))


def packed(data, mime):
    words=array.array('I'); words.frombytes(data+b'\0'*(-len(data)%4))
    if sys.byteorder!='little':words.byteswap()
    return {'image_words':words.tolist(),'byte_length':len(data),'mime':mime}


MIMES={'jpg':'image/jpeg','png':'image/png','webp':'image/webp','gif':'image/gif'}
