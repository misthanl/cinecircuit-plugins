"""Run local fixes in an isolated NAS process; never update media metadata."""
import base64
import importlib.util
import json
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT.parent / "cinecircuit"
sources = {
    "app.modules.explore.discover_service": (HOST / "app/modules/explore/discover_service.py").read_text(encoding="utf-8"),
    "app.modules.plugins.gateway_media_discovery": (HOST / "app/modules/plugins/gateway_media_discovery.py").read_text(encoding="utf-8"),
    "probe_cast.plugin": (ROOT / "cinecircuit_plugins/cast_profile_enricher/plugin.py").read_text(encoding="utf-8"),
}
payload = base64.b64encode(json.dumps(sources).encode()).decode()
code = r'''
import asyncio,base64,importlib,json,logging,sys,types
from types import SimpleNamespace
sources=json.loads(base64.b64decode(PAYLOAD))
package=types.ModuleType('probe_cast');package.__path__=['/app/plugin-runtime/installed/cast-profile-enricher'];sys.modules['probe_cast']=package
for name,source in sources.items():
    if name.startswith('probe_cast'):
        module=types.ModuleType(name);module.__package__='probe_cast';sys.modules[name]=module
    else: module=importlib.import_module(name)
    exec(compile(source,name,'exec'),module.__dict__)
from probe_cast.plugin import CastProfileEnricherPlugin
from app.modules.plugins.gateway_media_discovery import MediaDiscoveryGateway
from app.modules.plugins.permissions import PluginPermission
from app.modules.config.service import ConfigService
from app.modules.media.media_server_service import MediaServerService
config=ConfigService()
# The diagnostic audit sink stays in memory; no plugin runs are created.
gateway=MediaDiscoveryGateway(SimpleNamespace(audit=lambda *a,**k:None),'probe-cast',None,{PluginPermission.MEDIA_DISCOVER},config_service=config)
context=SimpleNamespace(media=gateway,logger=logging.getLogger('probe-cast'))
plugin=CastProfileEnricherPlugin()
lookup=gateway.search_source_identity
async def checked_identity(**kwargs):
    identity=await lookup(**kwargs)
    if identity:
        assert identity.get('source_key')=='douban', identity.get('source_key')
    print('identity',json.dumps({'title':kwargs['title'],'source':(identity or {}).get('source_key'),'id':(identity or {}).get('source_id')},ensure_ascii=False),flush=True)
    return identity
gateway.search_source_identity=checked_identity
async def main():
    media_service=MediaServerService(config)
    server='media-server-1788776150050'
    films=[]
    for library in (await media_service.list_libraries(server)).get('items',[]):
        result=await media_service.list_metadata_items(server,str(library['id']),limit=200)
        films.extend(result.get('items',[]))
    samples=[m for m in films if m.get('name') in ('奥德赛','苦菜花','肖申克的救赎','盗梦空间')]
    print('samples',json.dumps([{'name':m['name'],'year':m['year'],'people':len(m['people'])} for m in samples],ensure_ascii=False),flush=True)
    for media in samples:
        cast=await plugin._read_cast(context,media)
        roles=plugin._role_map(cast)
        matched=[]
        for person in media.get('people',[]):
            if person.get('Type','').lower()!='actor' or plugin._has_han(person.get('Role')):continue
            role=plugin._localized_role({},media,roles,person_name=person.get('Name',''),person_role=person.get('Role',''),localized_name='')
            if role:matched.append({'actor':person.get('Name'),'before':person.get('Role'),'after':role})
        assert all(plugin._is_chinese_role(row['after']) for row in matched)
        if media['name'] in ('盗梦空间','肖申克的救赎'):
            assert len(matched)>=20, (media['name'],len(matched))
        print('result',json.dumps({'title':media['name'],'year':media['year'],'cast_count':len(cast),'chinese_role_count':sum(plugin._is_chinese_role(p.get('character')) for p in cast),'matched_count':len(matched),'matched':matched,'source_samples':[{k:p.get(k) for k in ('name','aliases','character')} for p in cast[:5]]},ensure_ascii=False),flush=True)
    assert {'盗梦空间','肖申克的救赎'} <= {m['name'] for m in samples}
    print('real_role_lookup=passed; media_library_writes=0',flush=True)
asyncio.run(main())
'''.replace("PAYLOAD", repr(payload))
spec = importlib.util.spec_from_file_location("nas", HOST / ".planning/2026-07-19-phase91-nas-deploy/deploy_phase91.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
helper.SSH_HOST = "10.10.10.21"
session = helper.NasSession()
try:
    session.run("docker exec cinecircuit python -B -c " + shlex.quote(code), sudo=True, stream=True)
finally:
    session.close()
