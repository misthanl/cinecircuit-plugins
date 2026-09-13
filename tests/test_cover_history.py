import hashlib
import io
import pytest
from PIL import Image
from cinecircuit_plugins.media_cover_generator import history

@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'cover_directory',lambda:tmp_path)
    return history.CoverHistory()

def image(color='red'):
    out=io.BytesIO();Image.new('RGB',(320,180),color).save(out,format='JPEG');return out.getvalue()

def add(store,server='one',library='1',color='red',config=None):
    store.add(image(color),{'library_id':library,'name':'电影','format':'jpeg','status':'updated'},server,config or {})

def test_immutable_retention_and_server_scope(store):
    add(store,color='red');first=store.listing({})['items'][0]
    add(store,color='blue');assert store.read(first['id'])[1]==image('red')
    add(store,server='two')
    add(store,config={'covers_history_limit_per_library':1})
    rows=store.listing({})['items'];assert len(rows)==2
    assert len(list(store.root.glob('*.thumb.jpg')))==2

def test_delete_explicit_only_and_does_not_reset_counters(store):
    add(store);add(store,library='2')
    rows=store.listing({})['items']
    assert store.delete([rows[0]['id']])=={'deleted':1}
    assert len(store.listing({})['items'])==1
    assert store.listing({})['counts']['uploaded']==2
    with pytest.raises(ValueError):store.delete(['../../anything'])
    with pytest.raises(ValueError):store.read(rows[0]['id'])

def test_disabled_retention_and_page_cap(store):
    add(store,config={'save_recent_covers':False})
    assert store.listing({})['items']==[]
    for i in range(12):add(store,library=str(i))
    assert len(store.listing({'covers_page_history_limit':10})['items'])==10

def test_legacy_import_hash_and_no_resurrection(store):
    folder=store.root.parent/'output';folder.mkdir();path=folder/'old.jpg';path.write_bytes(image())
    result={'output_path':str(path),'library_id':'1','status':'updated','format':'jpeg','sha256':hashlib.sha256(image()).hexdigest()}
    rows=[{'payload':{'server_id':'one'},'result':result}]
    store.import_latest(rows,{})
    imported=store.listing({})['items'];assert len(imported)==1
    store.delete([imported[0]['id']]);store.import_latest(rows,{})
    assert store.listing({})['items']==[]
    path.write_bytes(image('blue'));store.import_latest(rows,{})
    assert store.listing({})['items']==[]

def test_new_generation_is_not_imported_twice(store):
    add(store)
    folder=store.root.parent/'output';folder.mkdir();path=folder/'old.jpg';path.write_bytes(image())
    store.import_latest([{'payload':{'server_id':'one'},'result':{'output_path':str(path),'library_id':'1','status':'updated','format':'jpeg','sha256':hashlib.sha256(image()).hexdigest()}}],{})
    assert len(store.listing({})['items'])==1
