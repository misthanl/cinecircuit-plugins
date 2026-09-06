<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { Component } from 'vue';
type Row={id:string;name:string;server_id:string;server_name:string;library_id:string;created_at:string;status:string;style:string;format:string;resolution:string;bytes:number;animated:boolean};
const props=defineProps<{context:{close:()=>void};request:(path:string,init?:RequestInit)=>Promise<any>;dialogComponent:Component;cardComponent:Component;buttonComponent:Component}>();
const UiDialog=props.dialogComponent,UiCard=props.cardComponent,UiButton=props.buttonComponent;
const rows=ref<Row[]>([]),limit=ref(50),counts=ref<Record<string,number>>({}),busy=ref(false),error=ref('');
const server=ref(''),library=ref(''),kind=ref(''),status=ref(''),shown=ref(6),batch=ref(false),selected=ref<string[]>([]);
const urls=ref<Record<string,string>>({}),preview=ref(''),previewTitle=ref(''),notice=ref('');
const confirm=ref<'delete'|'apply'|''>(''),pending=ref<string[]>([]);
let disposed=false,version=0,observer:IntersectionObserver|undefined;
const fetching=new Set<string>();
const all={title:'全部',value:''};
const servers=computed(()=>[all,...Array.from(new Map(rows.value.map(x=>[x.server_id,{value:x.server_id,title:x.server_name}])).values())]);
const libraries=computed(()=>[all,...Array.from(new Map(rows.value.filter(x=>!server.value||x.server_id===server.value).map(x=>[x.server_id+'|'+x.library_id,{value:x.server_id+'|'+x.library_id,title:x.server_name+'：'+x.name}])).values())]);
const filtered=computed(()=>rows.value.filter(x=>(!server.value||x.server_id===server.value)&&(!library.value||x.server_id+'|'+x.library_id===library.value)&&(!kind.value||(x.animated?'dynamic':'static')===kind.value)&&(!status.value||x.status===status.value)));
const visible=computed(()=>filtered.value.slice(0,shown.value));
const styles:Record<string,string>={diagonal:'斜向画廊',animated_diagonal:'动态海报墙',animated_wedge:'动态斜切轮播',animated:'动态轮播',single:'焦点单图',poster:'海报长廊',multi:'多图拼贴',duo:'留白双海报',stack:'扇形叠卡',editorial:'杂志拼版',panorama:'胶片横窗',cinema:'极简巨幕',echo:'叠影',wedge:'斜切'};
function endpoint(action:string){return '/plugins/emby-cover-generator/api/'+action;}
function fail(e:unknown){error.value=e instanceof Error?e.message:String(e);}
function menuButton(p:Record<string,unknown>){return {...p,icon:'mdi-dots-vertical',variant:'text',size:'small','aria-label':'更多操作'};}
function closePreview(){if(preview.value)URL.revokeObjectURL(preview.value);preview.value='';}
function cleanup(){disposed=true;version++;observer?.disconnect();Object.values(urls.value).forEach(URL.revokeObjectURL);if(preview.value)URL.revokeObjectURL(preview.value);}
async function imageBlob(id:string,thumb=false){const data=await props.request(endpoint('history_image')+'?id='+encodeURIComponent(id)+(thumb?'&thumbnail=1':''));const buffer=new ArrayBuffer(data.image_words.length*4),view=new DataView(buffer);data.image_words.forEach((v:number,i:number)=>view.setUint32(i*4,v,true));return new Blob([buffer.slice(0,data.byte_length)],{type:data.mime});}
async function thumbnails(){const ticket=version;for(const row of visible.value){if(disposed||ticket!==version)return;const key=ticket+row.id;if(urls.value[row.id]||fetching.has(key))continue;fetching.add(key);try{const blob=await imageBlob(row.id,true);if(disposed||ticket!==version)return;urls.value={...urls.value,[row.id]:URL.createObjectURL(blob)};}catch(e){if(ticket===version)fail(e);}finally{fetching.delete(key);}}}
async function load(){if(busy.value)return;busy.value=true;error.value='';const ticket=++version;try{const data=await props.request(endpoint('history'));if(disposed||ticket!==version)return;rows.value=data.items;limit.value=data.limit;counts.value=data.counts;shown.value=6;selected.value=[];Object.values(urls.value).forEach(URL.revokeObjectURL);urls.value={};}catch(e){fail(e);}finally{busy.value=false;}void thumbnails();}
function filter(){version++;shown.value=6;selected.value=[];void thumbnails();}
function selectServer(v:string){server.value=v;library.value='';filter();}
function more(){if(shown.value>=filtered.value.length||busy.value)return;shown.value+=6;void thumbnails();}
function observe(el:Element){observer?.disconnect();observer=new IntersectionObserver(entries=>{if(entries[0]?.isIntersecting)more();},{rootMargin:'100px'});observer.observe(el);}
function scroll(e:Event){const el=e.target as HTMLElement;if(el.scrollHeight-el.scrollTop-el.clientHeight<180)more();}
function toggle(id:string,on:boolean){selected.value=on?[...new Set([...selected.value,id])]:selected.value.filter(x=>x!==id);}
async function open(row:Row,download=false){error.value='';try{const blob=await imageBlob(row.id);if(disposed)return;const url=URL.createObjectURL(blob);if(download){const a=document.createElement('a');a.href=url;a.download=`${row.name}-${row.id}.${row.format==='jpeg'?'jpg':row.format==='apng'?'png':row.format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}else{if(preview.value)URL.revokeObjectURL(preview.value);preview.value=url;previewTitle.value=row.name;}}catch(e){fail(e);}}
function askDelete(ids:string[]){pending.value=[...ids];confirm.value='delete';}
function askApply(id:string){pending.value=[id];confirm.value='apply';}
async function execute(){if(busy.value)return;busy.value=true;error.value='';try{await props.request(endpoint(confirm.value==='delete'?'history_delete':'history_apply'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(confirm.value==='delete'?{ids:pending.value}:{id:pending.value[0]})});notice.value=confirm.value==='delete'?'历史封面已清理':'已重新应用封面';confirm.value='';}catch(e){fail(e);}finally{busy.value=false;}if(!confirm.value)await load();}
function date(s:string){return new Date(s).toLocaleString('zh-CN',{hour12:false});}
onMounted(load);
</script>
<template>
 <UiDialog :model-value="true" :max-width="920" width="calc(100vw - 32px)" @update:model-value="context.close()">
 <UiCard class="cover-history" @vue:unmounted="cleanup">
  <header><h2>媒体库视觉封面 · 数据统计</h2><UiButton icon="mdi-close" variant="text" aria-label="关闭" @click="context.close()" /></header>
  <main @scroll="scroll">
   <div class="metrics"><div v-for="[key,label] in [['generated','已生成'],['uploaded','已上传'],['preview','仅预览'],['failed','生成失败']]" :key="key"><span>{{label}}</span><strong>{{counts[key]||0}}</strong></div></div>
   <div class="heading"><h3>历史封面</h3><span>最近 {{limit}} 张</span><UiButton variant="text" @click="batch=!batch;selected=[]">{{batch?'退出多选':'批量清理'}}</UiButton></div>
   <div class="filters">
    <VSelect label="媒体服务器" :items="servers" :model-value="server" variant="outlined" hide-details @update:model-value="selectServer" />
    <VSelect label="媒体库" :items="libraries" v-model="library" variant="outlined" hide-details @update:model-value="filter" />
    <VSelect label="封面类型" :items="[all,{title:'静态',value:'static'},{title:'动态',value:'dynamic'}]" v-model="kind" variant="outlined" hide-details @update:model-value="filter" />
    <VSelect label="生成结果" :items="[all,{title:'已上传',value:'updated'},{title:'仅预览',value:'preview'}]" v-model="status" variant="outlined" hide-details @update:model-value="filter" />
   </div>
   <p v-if="error" role="alert">{{error}} <UiButton variant="text" @click="load">重试</UiButton></p><p v-if="notice" role="status">{{notice}}</p>
   <div v-if="batch" class="batch"><UiButton variant="text" @click="selected=visible.map(x=>x.id)">全选已加载结果</UiButton><UiButton variant="text" @click="selected=[]">取消全选</UiButton><span>已选 {{selected.length}} 张</span><UiButton color="error" :disabled="!selected.length||busy" @click="askDelete(selected)">清理所选</UiButton></div>
   <p v-if="busy" role="status">正在处理…</p>
   <p v-if="!busy&&!filtered.length" class="empty">暂无历史封面。开启“保留最近生成封面”后，新成品会保存在这里。</p>
   <div class="gallery">
    <article v-for="row in visible" :key="row.id" :class="{selected:selected.includes(row.id)}">
     <button class="thumbnail" :aria-label="'查看 '+row.name" @click="batch?toggle(row.id,!selected.includes(row.id)):open(row)"><img v-if="urls[row.id]" :src="urls[row.id]" :alt="row.name" loading="lazy"><span v-else>正在加载封面…</span><span v-if="row.animated" class="dynamic">动态 · 点击播放</span></button>
     <VCheckboxBtn v-if="batch" class="check" :class="{'is-selected':selected.includes(row.id)}" true-icon="mdi-check" color="primary" density="compact" :model-value="selected.includes(row.id)" :aria-label="'选择 '+row.name" @update:model-value="toggle(row.id,Boolean($event))" />
     <div class="details"><div class="title"><strong>{{row.name}}</strong><span>{{row.server_name}}</span><small>{{row.status==='updated'?'已上传':'仅预览'}}</small></div><time>{{date(row.created_at)}}</time><p>{{styles[row.style]||row.style}} · {{row.resolution}} · {{row.format.toUpperCase()}} · {{(row.bytes/1048576).toFixed(2)}} MB</p></div>
     <div class="actions"><UiButton variant="text" size="small" @click="open(row)">查看大图</UiButton><UiButton variant="text" size="small" @click="open(row,true)">下载</UiButton><VMenu><template #activator="{props:menuProps}"><UiButton icon="mdi-dots-vertical" variant="text" size="small" aria-label="更多操作" :aria-expanded="menuProps['aria-expanded']" :aria-haspopup="menuProps['aria-haspopup']" @click="menuProps.onClick" /></template><VList><VListItem title="重新应用这张封面" @click="askApply(row.id)" /><VListItem title="删除历史封面" @click="askDelete([row.id])" /></VList></VMenu></div>
    </article>
   </div>
   <div class="sentinel" @vue:mounted="observe($event.el)" @vue:updated="observe($event.el)">{{visible.length>=filtered.length?'已全部加载':'下滑加载更多'}} · {{visible.length}} / {{filtered.length}} 张</div>
  </main>
  <footer><span>统计自历史功能启用起，含可恢复的旧成品</span><UiButton variant="text" :disabled="busy" @click="load">刷新</UiButton></footer>
  <UiDialog :model-value="Boolean(preview)" :max-width="1280" @update:model-value="closePreview"><UiCard class="cover-large"><UiButton variant="text" @click="closePreview">关闭</UiButton><img :src="preview" :alt="previewTitle" /></UiCard></UiDialog>
  <UiDialog :model-value="Boolean(confirm)" :max-width="480" @update:model-value="!busy&&(confirm='')"><UiCard class="confirmation"><h3>{{confirm==='delete'?'清理 '+pending.length+' 张历史封面？':'重新应用这张封面？'}}</h3><p>{{confirm==='delete'?'仅删除本地历史文件和对应记录，不影响媒体服务器当前封面。此操作不可撤销。':'将替换该历史封面所属媒体库的当前封面。'}}</p><UiButton variant="text" :disabled="busy" @click="confirm=''">取消</UiButton><UiButton :color="confirm==='delete'?'error':'primary'" :disabled="busy" @click="execute">确认</UiButton></UiCard></UiDialog>
 </UiCard></UiDialog>
</template>
<style scoped>
.cover-history{display:flex;flex-direction:column;max-height:90vh;color:var(--app-text,#202939);font-size:12px;background:var(--app-surface,#fff)}header,footer{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;gap:12px;border-bottom:1px solid #e2e7f0}header h2{margin:0;font-size:18px}main{overflow:auto;padding:18px;min-height:0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metrics>div{background:#f4f6fb;border:1px solid #e2e7f0;border-radius:11px;padding:12px 14px}.metrics span,time,.details p,footer span{color:#7a869d;font-size:11px}.metrics strong{display:block;margin-top:5px;font-size:24px;line-height:1.15}.heading{display:flex;align-items:center;gap:12px;margin:17px 0 12px}.heading h3{margin:0 auto 0 0;font-size:15px}.filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}.gallery{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.gallery article{position:relative;border:1px solid #dbe2ef;border-radius:11px;overflow:hidden}.gallery article.selected{outline:2px solid #2962ff}.thumbnail{width:100%;aspect-ratio:16/9;display:grid;place-items:center;background:#eef1f6;position:relative;cursor:pointer}.thumbnail img{width:100%;height:100%;object-fit:contain}.dynamic{position:absolute;bottom:8px;left:9px;background:#23334bd9;color:white;border-radius:6px;padding:3px 6px;font-size:10px}.details{padding:9px 10px}.title{display:flex;gap:6px;align-items:center;margin-bottom:5px}.title strong{margin-right:auto;font-size:12px}.title span,.title small{font-size:10px}.title small{color:#189c65}.details p{margin:4px 0 0}.actions{display:flex;align-items:center;border-top:1px solid #edf0f6;padding:2px 5px}.actions>:last-child{margin-left:auto}.check{position:absolute;top:4px;left:6px;background:white;border-radius:6px}.batch{display:flex;align-items:center;gap:9px;margin-bottom:14px;flex-wrap:wrap}.sentinel,.empty{text-align:center;color:#8490a3;padding:18px}.confirmation{padding:20px}.confirmation p{margin:12px 0}.cover-large{padding:10px}.cover-large img{display:block;width:100%;max-height:78vh;object-fit:contain}footer{border-top:1px solid #e2e7f0;border-bottom:0;padding:10px 18px}[role=alert]{color:#c62828}@media(max-width:1100px){.gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:850px){.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}.filters{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.gallery{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}main{padding:12px}header{padding:13px 14px}header h2{font-size:16px}.title{flex-wrap:wrap}}
</style>
<style scoped>
header,footer{flex-shrink:0}
.cover-history .gallery{grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;align-items:start}
.gallery article{min-width:0}
.title{flex-wrap:wrap;overflow-wrap:anywhere}
.details p{overflow-wrap:anywhere}
.check{top:4px;left:4px;width:44px;height:44px;min-height:44px;background:transparent;display:flex;justify-content:center;align-items:center}
.check :deep(.v-selection-control__wrapper){width:44px;height:44px}
.check :deep(.v-selection-control__input){width:28px;height:28px;background:#fff;border:1px solid #dbe2ef;border-radius:6px;box-shadow:none}
.check:not(.is-selected) :deep(.v-selection-control__input > .v-icon){opacity:0}
.check.is-selected :deep(.v-selection-control__input){background:#2962ff;border-color:#2962ff}
.check.is-selected :deep(.v-selection-control__input > .v-icon){opacity:1;color:#fff}
.gallery article.selected{outline:1px solid #90adff}
.thumbnail:focus:not(:focus-visible){outline:none}
.thumbnail:focus-visible{outline:2px solid #2962ff;outline-offset:-2px}
.check :deep(input:focus-visible + .v-icon){outline:2px solid #2962ff;outline-offset:2px}
@media(max-width:600px){
 .cover-history{max-height:82vh;max-height:82dvh}
 .cover-history main{overscroll-behavior:contain}
 .cover-history footer{padding:10px 14px}
}
@media(max-width:1100px) and (min-width:851px){.cover-history .gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:850px) and (min-width:601px){.cover-history .gallery{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.cover-history .gallery{grid-template-columns:1fr}}
</style>
