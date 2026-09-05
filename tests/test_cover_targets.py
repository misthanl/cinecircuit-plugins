import asyncio
import json
import logging
from types import SimpleNamespace
from pathlib import Path
import pytest
from cinecircuit_plugins.media_cover_generator.plugin import LibraryArtworkPlugin,ArtworkGenerationRun

class Servers:
    async def configurations(self):
        return {'items':[{'id':'a','name':'家里 Emby','type':'emby','enabled':True},{'id':'b','name':'Jellyfin','type':'jellyfin','enabled':True},{'id':'c','name':'停用','type':'emby','enabled':False},{'id':'d','name':'Plex','type':'plex','enabled':True}]}
    async def libraries(self,identity):
        return {'server_id':identity,'items':[{'id':'1','name':'电影'},{'id':'2','name':'剧集'}]}

def execute(config,monkeypatch):
    plugin=LibraryArtworkPlugin()
    async def font(context):return Path('.')
    monkeypatch.setattr(plugin,'_ensure_cjk_font',font)
    run=ArtworkGenerationRun(plugin,SimpleNamespace(config=config,media_servers=Servers(),logger=logging.getLogger('targets')))
    seen=[]
    async def process(library):
        seen.append((run.server_id,library['id']))
        run.results.append({'status':'preview'})
    monkeypatch.setattr(run,'_process_library',process)
    result=asyncio.run(run.run())
    return seen,result

def test_no_servers_is_noop(monkeypatch):
    seen,result=execute({'selected_servers':[]},monkeypatch)
    assert seen==[] and result['reason']=='no_servers_selected'

def test_empty_libraries_means_all_on_selected_servers(monkeypatch):
    seen,result=execute({'selected_servers':['a','b'],'library_targets':[]},monkeypatch)
    assert seen==[('a','1'),('a','2'),('b','1'),('b','2')]
    assert result['library_count']==4

def test_library_ids_are_scoped_to_server(monkeypatch):
    seen,_=execute({'selected_servers':['a','b'],'library_targets':[json.dumps(['b','1'])]},monkeypatch)
    assert seen==[('b','1')]

@pytest.mark.parametrize('identity',['c','d','missing'])
def test_disabled_unsupported_or_deleted_servers_never_run(identity,monkeypatch):
    with pytest.raises(ValueError):execute({'selected_servers':[identity],'library_targets':[]},monkeypatch)

def test_target_inventory_lists_only_enabled_supported_instances():
    plugin=LibraryArtworkPlugin()
    request=SimpleNamespace(action='targets',method='GET',query={'servers':'["a","b","c","d"]'})
    context=SimpleNamespace(media_servers=Servers())
    result=asyncio.run(plugin.handle_api(request,context))
    assert [x['value'] for x in result['servers']]==['a','b']
    assert [json.loads(x['value']) for x in result['libraries']]==[['a','1'],['a','2'],['b','1'],['b','2']]
