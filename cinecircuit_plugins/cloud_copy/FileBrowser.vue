<script setup lang="ts">
import { pluginErrorFallback } from "../_shared/request-feedback";
import { computed, ref } from "vue";
type Item = {file_id:string;name:string;directory:boolean;size?:number};
const props = defineProps<{request:<T=unknown>(path:string,init?:RequestInit)=>Promise<T>; storages:Array<{id:string;name:string}>; target?:boolean; disabled?:boolean}>();
const emit = defineEmits<{change:[value:{storage:string;parent:string;selected:string[];path:string} ]}>();
const storage=ref(""), items=ref<Item[]>([]), selected=ref<string[]>([]), loading=ref(false), error=ref("");
const folders=ref([{id:"0",name:"根目录"}]), cursor=ref<string|null>(null), search=ref("");
const searchOpen=ref(false), searchInput=ref<HTMLInputElement|null>(null);
const hiddenFolders=computed(()=>folders.value.slice(1,-1).map((folder,index)=>({...folder,index:index+1})));
function toggleSearch(){searchOpen.value=!searchOpen.value;if(searchOpen.value)requestAnimationFrame(()=>searchInput.value?.focus());else search.value='';}
let generation=0;

const visible=computed(()=>items.value.filter(item=>(!props.target || item.directory) && item.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())));
const allVisibleSelected=computed(()=>visible.value.length>0 && visible.value.every(item=>selected.value.includes(String(item.file_id))));
const someVisibleSelected=computed(()=>!allVisibleSelected.value && visible.value.some(item=>selected.value.includes(String(item.file_id))));
const selectedSize=computed(()=>{
 const rows=items.value.filter(item=>selected.value.includes(String(item.file_id)));
 return rows.length && rows.every(item=>!item.directory && item.size!==undefined) ? size(rows.reduce((total,item)=>total+(item.size || 0),0)) : '';
});
const destination=computed(()=>`${props.storages.find(row=>row.id===storage.value)?.name || ''} / ${folders.value.map(row=>row.name).join(' / ')}`);
function publish(){emit("change",{storage:storage.value,parent:folders.value.at(-1)!.id,selected:[...selected.value],path:folders.value.map(row=>row.name).join(" / ")});}
async function load(more=false){
 const current=++generation;loading.value=true;error.value="";
 if(!more){items.value=[];selected.value=[];cursor.value=null;publish();}
 if(!storage.value){loading.value=false;return;}
 try{
  const query=new URLSearchParams({storage:storage.value,parent:folders.value.at(-1)!.id});
  if(more)query.set("cursor",cursor.value!);
  const data=await props.request<{items:Item[];cursor:string|null}>(`/plugins/cloud-copy/api/browse?${query}`);
  if(current!==generation)return;
  if(!more)items.value=[];
  items.value.push(...data.items);cursor.value=data.cursor;
 }catch (cause) {if(current===generation)error.value=pluginErrorFallback(cause, "目录读取失败，请刷新重试");}
 finally{if(current===generation)loading.value=false;}
}
function changeStorage(value:string){storage.value=value;folders.value=[{id:"0",name:"根目录"}];search.value="";void load();}
function enter(item:Item){if(loading.value || props.disabled)return;folders.value.push({id:String(item.file_id),name:item.name});search.value="";void load();}
function navigate(index:number){if(loading.value || props.disabled || index===folders.value.length-1)return;folders.value=folders.value.slice(0,index+1);search.value="";void load();}
function back(){navigate(folders.value.length-2);}
function toggle(item:Item){const id=String(item.file_id);selected.value=selected.value.includes(id)?selected.value.filter(value=>value!==id):[...selected.value,id];publish();}
function selectAll(){selected.value=visible.value.every(item=>selected.value.includes(String(item.file_id)))?[]:visible.value.map(item=>String(item.file_id));publish();}
function size(value?:number){return value===undefined?"—":value>=1073741824?`${(value/1073741824).toFixed(1)} GB`:value>=1048576?`${(value/1048576).toFixed(1)} MB`:`${value} B`;}
</script>
<template>
 <section class="copy-browser" :class="{'copy-browser--target':target}" :aria-label="target ? '目标目录浏览器' : '源文件浏览器'">
  <div class="browser-select"><VSelect class="app-field app-control-compact" density="compact" :model-value="storage || null" :items="storages" item-title="name" item-value="id" :label="target ? '目标网盘' : '源网盘'" prepend-inner-icon="mdi-cloud-outline" variant="outlined" hide-details :disabled="disabled" @update:model-value="changeStorage" /></div>
  <div class="browser-toolbar" :class="{'browser-toolbar--search-open':searchOpen}">
   <button type="button" class="browser-tool" :disabled="folders.length===1 || loading || disabled" aria-label="返回上级目录" @click="back"><VIcon icon="mdi-arrow-up" /></button>
   <nav class="browser-crumbs" aria-label="目录路径" :title="folders.map(folder=>folder.name).join(' / ')">
    <button v-if="folders.length>1" type="button" class="crumb-root" :disabled="loading || disabled" @click="navigate(0)">根目录</button>
    <template v-if="hiddenFolders.length"><span class="crumb-divider" aria-hidden="true">/</span><VMenu><template #activator="{props:menuProps}"><button :id="menuProps.id" :aria-haspopup="menuProps['aria-haspopup']" :aria-expanded="menuProps['aria-expanded']" :aria-controls="menuProps['aria-controls']" @click="menuProps.onClick" @keydown="menuProps.onKeydown" type="button" class="crumb-overflow" aria-label="展开上级目录" :disabled="loading || disabled">…</button></template><VList><VListItem v-for="folder in hiddenFolders" :key="folder.index" :title="folder.name" :disabled="loading || disabled" @click="navigate(folder.index)" /></VList></VMenu></template>
    <span v-if="folders.length>1" class="crumb-divider" aria-hidden="true">/</span><span class="crumb-current" aria-current="page" :title="folders.at(-1)?.name">{{folders.at(-1)?.name}}</span>
   </nav>
   <label class="browser-search-field"><VIcon icon="mdi-magnify" size="18" /><input ref="searchInput" :value="search" @input="search=($event.target as HTMLInputElement).value" :disabled="disabled || !storage" aria-label="筛选当前目录" placeholder="筛选目录" @keydown="event=>{if(event.key==='Escape'){searchOpen=false;search='';}}" /></label>
   <button type="button" class="browser-tool browser-search-toggle" :disabled="disabled || !storage" :aria-label="searchOpen ? '收起目录筛选' : '展开目录筛选'" :aria-expanded="searchOpen" @click="toggleSearch"><VIcon :icon="searchOpen ? 'mdi-close' : 'mdi-magnify'" size="18" /></button>
   <button type="button" class="browser-tool" :disabled="!storage || loading || disabled" aria-label="刷新目录" @click="load()"><VIcon icon="mdi-refresh" /></button>
  </div>
  <p v-if="error" role="alert">{{error}}</p>
  <div class="browser-list-heading" :class="{'browser-list-heading--target':target}"><label v-if="!target" class="browser-heading-select"><input type="checkbox" aria-label="全选" :checked="allVisibleSelected" :indeterminate="someVisibleSelected" :disabled="!visible.length || loading || disabled" @change="selectAll" /></label><span class="browser-heading-name">名称</span><span v-if="!target" class="browser-heading-size">大小</span></div>
  <div class="browser-files" :aria-busy="loading">
   <div v-for="item in visible" :key="item.file_id" class="browser-file" :class="{selected:selected.includes(String(item.file_id))}">
    <input v-if="!target" type="checkbox" :checked="selected.includes(String(item.file_id))" :aria-label="`选择 ${item.name}`" :disabled="disabled || loading" @change="toggle(item)" />
    <VIcon :icon="item.directory ? 'mdi-folder-outline' : 'mdi-file-outline'" />
    <button v-if="item.directory" type="button" class="file-name" :disabled="loading || disabled" @click="enter(item)">{{item.name}}</button>
    <span v-else class="file-name">{{item.name}}</span>
    <small v-if="!target">{{item.directory ? '—' : size(item.size)}}</small>
    <button v-else type="button" class="browser-enter" :aria-label="`进入 ${item.name}`" :disabled="loading || disabled" @click="enter(item)"><VIcon icon="mdi-chevron-right" size="18" /></button>
   </div>
   <div v-if="!visible.length" class="browser-empty">{{loading ? '正在读取目录…' : !storage ? (target ? '选择目标网盘和目录' : '选择源网盘，勾选要复制的文件或文件夹') : '当前目录暂无可显示的内容'}}</div>
   <button v-if="cursor" type="button" class="browser-more" :disabled="loading || disabled" @click="load(true)">{{loading ? '正在读取…' : '加载更多'}}</button>
  </div>
  <footer class="browser-status" aria-live="polite">
   <VIcon :icon="target ? 'mdi-folder-outline' : selected.length ? 'mdi-check-circle-outline' : 'mdi-file-multiple-outline'" size="20" />
   <template v-if="target"><span class="browser-status-label">目标目录</span><span class="browser-status-value" :title="storage ? destination : undefined">{{storage ? destination : '尚未选择保存位置'}}</span></template>
   <template v-else><span class="browser-status-value">已选择 {{selected.length}} 项</span><span v-if="selectedSize" class="browser-status-size">{{selectedSize}}</span></template>
  </footer>
 </section>
</template>
<style scoped>
.copy-browser{container-type:inline-size;min-height:0;overflow:hidden;min-width:0;display:flex;flex-direction:column;background:var(--app-surface);color:var(--app-text);font-family:var(--app-font-family);font-size:var(--app-font-size-control);font-weight:var(--app-font-weight-regular)}
.browser-select{flex-shrink:0;padding:14px 18px 8px}
.browser-toolbar{display:flex;align-items:center;gap:8px;flex-shrink:0;min-width:0;min-height:44px;margin:0 18px 6px;padding:6px 10px;border-radius:var(--app-radius-panel);background:var(--app-surface-muted)}
.browser-tool{display:grid;width:30px;height:30px;flex:none;place-items:center;border-radius:var(--app-radius-action)}
.browser-tool:not(:disabled):hover{background:var(--app-surface-hover)}
.browser-crumbs{display:flex;align-items:center;gap:6px;min-width:0;flex:1;overflow:hidden;white-space:nowrap;color:var(--blue)}
.browser-crumbs button{font:inherit;color:inherit}.crumb-root,.crumb-overflow,.crumb-divider{flex:none}.crumb-current{min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--app-text)}.crumb-divider{color:var(--app-text-secondary)}
button{color:var(--app-text);cursor:pointer;font:inherit}button:disabled{color:var(--app-text-disabled);cursor:default}button:focus-visible,input:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.browser-search-field{display:flex;align-items:center;gap:8px;min-width:0;flex:0 1 180px;min-height:32px;padding:0 10px;border:1px solid var(--app-border);border-radius:var(--app-radius-action);background:var(--app-surface);color:var(--app-text-secondary)}
.browser-search-field:focus-within{border-color:var(--blue)}
.browser-search-field input:focus-visible{outline:none}
.browser-search-field input{color:var(--app-text);min-width:0;width:100%;flex:1;background:transparent;font:inherit;line-height:1.5}
.browser-search-field input::placeholder{color:var(--app-text-secondary);opacity:var(--app-opacity-visible)}
.browser-search-toggle{display:none}
.browser-list-heading{display:grid;grid-template-columns:18px 24px minmax(0,1fr) 88px;align-items:center;gap:10px;min-height:32px;margin:0 18px;padding:0 10px;border-bottom:1px solid var(--app-border);font-size:var(--app-table-heading-font-size);font-weight:var(--app-table-heading-font-weight)}
.browser-list-heading--target{grid-template-columns:24px minmax(0,1fr) 28px}.browser-heading-select{grid-column:1;display:flex;align-items:center}.browser-heading-name{grid-column:3}.browser-list-heading--target .browser-heading-name{grid-column:2}.browser-heading-size{grid-column:4;text-align:left}
.browser-file>.v-icon{color:var(--blue)}
.browser-enter{display:grid;width:28px;height:28px;flex:none;place-items:center;color:var(--app-text-secondary);border-radius:var(--app-radius-action)}
.browser-files{flex:1;min-height:0;overflow:auto;padding:0 18px}.browser-file{display:grid;grid-template-columns:18px 24px minmax(0,1fr) 88px;align-items:center;gap:10px;min-height:42px;padding:7px 10px;border-radius:var(--app-radius-action)}.copy-browser--target .browser-file{grid-template-columns:24px minmax(0,1fr) 28px}.browser-file:not(.selected):hover{background:var(--app-surface-hover)}.browser-file.selected{background:var(--app-surface-selected);color:var(--app-text)}
.copy-browser input[type=checkbox]{appearance:none;-webkit-appearance:none;width:18px;height:18px;flex:none;margin:0;border:2px solid var(--app-text-secondary);border-radius:5px;background:transparent;cursor:pointer}
.copy-browser input[type=checkbox]:checked,.copy-browser input[type=checkbox]:indeterminate{border-color:var(--blue);background-color:var(--blue);background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m3 8 3 3 7-7' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-size:100% 100%}
.copy-browser input[type=checkbox]:indeterminate{background-image:linear-gradient(var(--app-on-accent),var(--app-on-accent));background-size:10px 2px;background-repeat:no-repeat;background-position:center}
.copy-browser input[type=checkbox]:disabled{border-color:var(--app-text-disabled);cursor:default}
.file-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:left;font:inherit}.browser-file small{text-align:left;color:var(--app-text-secondary);font-size:var(--app-font-size-helper);white-space:nowrap}.browser-empty{padding:60px 18px;text-align:center;color:var(--app-text-secondary)}.browser-more{width:100%;padding:12px}
.browser-status{display:flex;align-items:center;gap:10px;flex-shrink:0;min-height:36px;margin:6px 18px 8px;padding:6px 10px;border-radius:var(--app-radius-action);background:var(--app-surface-muted);font-size:var(--app-table-field-content-font-size);color:var(--app-text)}
.browser-status>.v-icon{flex:none;color:var(--blue)}.browser-status-label{flex:none;color:var(--app-text-secondary)}.browser-status-value{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.browser-status-size{margin-left:4px;white-space:nowrap}
p[role=alert]{color:var(--app-danger-text);padding:8px 18px}
@container(max-width:520px){.browser-search-field{display:none}.browser-search-toggle{display:grid}.browser-toolbar--search-open .browser-crumbs{display:none}.browser-toolbar--search-open .browser-search-field{display:flex;flex:1}}
@media(max-width:700px){.browser-select{padding:10px 12px 6px}.browser-toolbar{margin:0 10px 6px;padding:6px 8px}.browser-empty{padding:12px 10px}.browser-files{padding:0 10px}.browser-list-heading{margin:0 10px}.browser-status{margin:6px 10px 8px;gap:8px}}
</style>
