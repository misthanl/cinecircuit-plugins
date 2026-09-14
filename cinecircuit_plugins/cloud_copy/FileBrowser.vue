<script setup lang="ts">
import { computed, ref } from "vue";
type Item = {file_id:string;name:string;directory:boolean;size?:number};
const props = defineProps<{request:<T=unknown>(path:string,init?:RequestInit)=>Promise<T>; storages:Array<{id:string;name:string}>; target?:boolean; disabled?:boolean}>();
const emit = defineEmits<{change:[value:{storage:string;parent:string;selected:string[];path:string} ]}>();
const storage=ref(""), items=ref<Item[]>([]), selected=ref<string[]>([]), loading=ref(false), error=ref("");
const folders=ref([{id:"0",name:"根目录"}]), cursor=ref<string|null>(null), search=ref("");
let generation=0;
const pathTipOpen=ref(false);
function showPathTip(event:MouseEvent){const element=event.currentTarget as HTMLElement;pathTipOpen.value=element.scrollWidth>element.clientWidth;}

const visible=computed(()=>items.value.filter(item=>(!props.target || item.directory) && item.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())));
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
 }catch{if(current===generation)error.value="目录读取失败，请刷新重试";}
 finally{if(current===generation)loading.value=false;}
}
function changeStorage(value:string){storage.value=value;folders.value=[{id:"0",name:"根目录"}];search.value="";void load();}
function enter(item:Item){if(loading.value || props.disabled)return;folders.value.push({id:String(item.file_id),name:item.name});search.value="";void load();}
function navigate(index:number){if(loading.value || props.disabled || index===folders.value.length-1)return;pathTipOpen.value=false;folders.value=folders.value.slice(0,index+1);search.value="";void load();}
function back(){navigate(folders.value.length-2);}
function toggle(item:Item){const id=String(item.file_id);selected.value=selected.value.includes(id)?selected.value.filter(value=>value!==id):[...selected.value,id];publish();}
function selectAll(){selected.value=visible.value.every(item=>selected.value.includes(String(item.file_id)))?[]:visible.value.map(item=>String(item.file_id));publish();}
function size(value?:number){return value===undefined?"—":value>=1073741824?`${(value/1073741824).toFixed(1)} GB`:value>=1048576?`${(value/1048576).toFixed(1)} MB`:`${value} B`;}
</script>
<template>
 <section class="copy-browser" :aria-label="target ? '目标目录浏览器' : '源文件浏览器'">
  <div class="browser-select"><VSelect :model-value="storage || null" :items="storages" item-title="name" item-value="id" :label="target ? '目标网盘' : '源网盘'" variant="outlined" hide-details :disabled="disabled" @update:model-value="changeStorage" /></div>
  <div class="browser-path"><button type="button" :disabled="folders.length===1 || loading || disabled" aria-label="返回上级目录" @click="back"><VIcon icon="mdi-arrow-up" /></button><nav class="browser-crumbs" aria-label="目录路径" @mouseenter="showPathTip" @mouseleave="pathTipOpen=false"><VTooltip :model-value="pathTipOpen" :open-on-hover="false" :open-on-focus="false" location="bottom start" content-class="copy-path-tooltip" :text="folders.map(row=>row.name).join(' / ')" activator="parent" /><template v-for="(folder,index) in folders" :key="folder.id"><span v-if="index" class="crumb-divider" aria-hidden="true"> / </span><button type="button" :aria-current="index===folders.length-1 ? 'page' : undefined" :disabled="loading || disabled || index===folders.length-1" @click="navigate(index)">{{folder.name}}</button></template></nav><button type="button" :disabled="!storage || loading || disabled" aria-label="刷新目录" @click="load()"><VIcon icon="mdi-refresh" /></button></div>
  <div class="browser-search"><input :value="search" @input="search=($event.target as HTMLInputElement).value" :disabled="disabled" aria-label="筛选当前目录" placeholder="筛选当前目录" /><button v-if="!target" type="button" :disabled="!visible.length || loading || disabled" @click="selectAll">全选</button></div>
  <p v-if="error" role="alert">{{error}}</p>
  <div class="browser-files" :aria-busy="loading">
   <div v-for="item in visible" :key="item.file_id" class="browser-file" :class="{selected:selected.includes(String(item.file_id))}">
    <input v-if="!target" type="checkbox" :checked="selected.includes(String(item.file_id))" :aria-label="`选择 ${item.name}`" :disabled="disabled || loading" @change="toggle(item)" />
    <VIcon :icon="item.directory ? 'mdi-folder-outline' : 'mdi-file-outline'" />
    <button v-if="item.directory" type="button" class="file-name" :disabled="loading || disabled" @click="enter(item)"><VTooltip :text="item.name" activator="parent" location="bottom start" content-class="copy-path-tooltip" />{{item.name}}</button>
    <span v-else class="file-name"><VTooltip :text="item.name" activator="parent" location="bottom start" content-class="copy-path-tooltip" />{{item.name}}</span>
    <small>{{item.directory ? '文件夹' : size(item.size)}}</small>
   </div>
   <div v-if="!visible.length" class="browser-empty">{{loading ? '正在读取目录…' : !storage ? (target ? '选择目标网盘和目录' : '选择源网盘，勾选要复制的文件或文件夹') : '当前目录暂无可显示的内容'}}</div>
   <button v-if="cursor" type="button" class="browser-more" :disabled="loading || disabled" @click="load(true)">{{loading ? '正在读取…' : '加载更多'}}</button>
  </div>
  <footer>{{target ? '复制到当前目录' : `已选择 ${selected.length} 项`}}</footer>
 </section>
</template>
<style scoped>
:global(.copy-path-tooltip){color:var(--app-text)!important;background:var(--app-dialog-surface,var(--app-surface))!important}
.copy-browser{min-height:0;overflow:hidden;min-width:0;display:flex;flex-direction:column;background:var(--app-surface,#fff)}
.browser-select{flex-shrink:0;padding:18px}.browser-path,.browser-search{flex-shrink:0;display:flex;gap:10px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--app-border,#e2e8f0)}
.browser-crumbs{min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px;color:var(--app-text-secondary,#738198)}
.browser-crumbs button{font:inherit}.browser-crumbs button[aria-current=page]{opacity:1;color:var(--app-text-secondary)}.crumb-divider{color:var(--app-text-secondary)}
button{color:var(--app-text);cursor:pointer}button:disabled{opacity:.4;cursor:default}button:focus-visible,input:focus-visible{outline:2px solid #2b6dff;outline-offset:2px}
.browser-search input{color:var(--app-text);min-width:0;flex:1;outline:none;font-size:13px}.browser-search button{font-size:13px}.browser-search input::placeholder{color:var(--app-text-secondary)!important;opacity:1!important}.browser-file>.v-icon{color:var(--app-text-secondary)}
.browser-files{flex:1;min-height:0;overflow:auto;padding:8px}.browser-file{display:flex;align-items:center;gap:10px;padding:11px 10px;border-radius:8px}.browser-file.selected{background:var(--app-surface-selected,#edf3ff);color:var(--app-text)}.browser-file input[type=checkbox]{appearance:none;-webkit-appearance:none;width:18px;height:18px;flex-shrink:0;margin:0;border:2px solid var(--app-text-secondary);border-radius:5px;background:transparent;cursor:pointer}.browser-file input[type=checkbox]:checked{border-color:var(--blue);background-color:var(--blue);background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m3 8 3 3 7-7' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-size:100% 100%}.browser-file input[type=checkbox]:disabled{opacity:.5;cursor:default}.file-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:left;font-size:14px}.browser-file small{color:var(--app-text-secondary,#738198);font-size:11px;white-space:nowrap}.browser-empty{padding:60px 18px;text-align:center;color:var(--app-text-secondary,#738198);font-size:13px}.browser-more{width:100%;padding:12px;font-size:13px}footer{flex-shrink:0;padding:12px 18px;border-top:1px solid var(--app-border,#e2e8f0);font-size:12px;color:var(--app-text-secondary,#738198)}p[role=alert]{color:var(--app-danger-text,#bd3333);padding:8px 18px;font-size:13px}
@media(max-width:700px){footer{display:none}.browser-select{padding:14px 12px}.browser-path,.browser-search{padding:4px 10px}.browser-empty{padding:12px 10px}footer{padding:4px 10px}}
</style>
