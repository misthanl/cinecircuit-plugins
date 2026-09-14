<script setup lang="ts">
import {computed,onMounted,ref,type Component} from "vue";
import FileBrowser from "./FileBrowser.vue";
type Selection={storage:string;parent:string;selected:string[];path:string};
type Batch={id:string;config:{source:string;target:string};names:string[];status:string;selected:number;completed?:number;attention?:number;error?:string;records?:Array<{identity:string;path:string;status:string;reason?:string}>};
const props=defineProps<{request:<T=unknown>(path:string,init?:RequestInit)=>Promise<T>;buttonComponent:Component;dialogComponent:Component;cardComponent:Component}>();
const UiButton=props.buttonComponent,UiDialog=props.dialogComponent,UiCard=props.cardComponent;
const workspaceRoot=ref<HTMLElement|null>(null);
let releaseBounds:(()=>void)|undefined;
function fitWorkspace(){
 const root=workspaceRoot.value;if(!root)return;
 const update=()=>{const top=root.getBoundingClientRect().top;const dock=document.querySelector('.mobile-shell-dock')?.getBoundingClientRect();const shell=root.closest('.app-workspace');const padding=shell ? parseFloat(getComputedStyle(shell).paddingBottom) : 24;const bottom=Math.min(window.innerHeight-padding-2,dock && dock.height ? dock.top-8 : window.innerHeight);root.style.height=`${Math.max(0,bottom-top)}px`;};
 const observer=new ResizeObserver(update);if(root.parentElement)observer.observe(root.parentElement);const shell=root.closest('.app-workspace');if(shell)observer.observe(shell);if(shell?.parentElement)observer.observe(shell.parentElement);
 window.addEventListener('resize',update);window.visualViewport?.addEventListener('resize',update);update();
 releaseBounds=()=>{observer.disconnect();window.removeEventListener('resize',update);window.visualViewport?.removeEventListener('resize',update);};
}
const recordsOpen=ref(false),settingsOpen=ref(false),activePane=ref("source");
function openRecords(){recordsOpen.value=true;void load();}
const storages=ref<Array<{id:string;name:string;enabled:boolean;capabilities:string[]}>>([]);
const sources=computed(()=>storages.value.filter(row=>row.enabled!==false && row.capabilities.includes('file_copy_source')));
const targets=computed(()=>storages.value.filter(row=>row.enabled!==false && row.capabilities.includes('file_copy_target')));
const source=ref<Selection>({storage:'',parent:'0',selected:[],path:''}),target=ref<Selection>({storage:'',parent:'0',selected:[],path:''});
const policy=ref('metadata'),followup=ref('none'),maxGib=ref(10),busy=ref(false),loading=ref(false),error=ref(''),message=ref(''),batches=ref<Batch[]>([]);
let submissionId='',submittedPayload='';
let refreshTimer:ReturnType<typeof setTimeout>|undefined;let disposed=false;
function dispose(){releaseBounds?.();disposed=true;clearTimeout(refreshTimer);}
const policies=[{title:'仅使用已有校验信息',value:'metadata'},{title:'允许读取源文件验证秒传',value:'verify'},{title:'允许服务器中转上传',value:'relay'}];
const followups=[{title:'仅复制',value:'none'},{title:'交接整理',value:'organize'},{title:'同步本批文件',value:'sync'}];
const states:Record<string,string>={queued:'等待执行',running:'正在复制',completed:'处理完成',failed:'执行失败',skipped:'已跳过',uncertain:'结果待确认',conflict:'同名冲突',copied:'等待交接'};
const name=(id:string)=>storages.value.find(row=>row.id===id)?.name || id;
async function load(){clearTimeout(refreshTimer);loading.value=true;try{batches.value=(await props.request<{items:Batch[]}>('/plugins/cloud-copy/api/batches')).items;}catch{error.value='批次记录读取失败，请刷新重试';}finally{loading.value=false;if(!disposed && batches.value.some(row=>['queued','running'].includes(row.status)))refreshTimer=setTimeout(()=>void load(),5000);}}
async function submit(){
 if(busy.value || !source.value.selected.length || !target.value.storage)return;
 busy.value=true;error.value='';message.value='';
 const data={source:source.value.storage,source_root:source.value.parent,target:target.value.storage,target_root:target.value.parent,selected:source.value.selected,policy:policy.value,followup:followup.value,max_gib:maxGib.value};
 const encoded=JSON.stringify(data);if(encoded!==submittedPayload){submissionId=crypto.randomUUID();submittedPayload=encoded;}
 try{await props.request('/plugins/cloud-copy/api/submit',{method:'POST',body:JSON.stringify({...data,id:submissionId})});message.value=`已提交 ${source.value.selected.length} 项，后台将处理本批文件`;await load();}
 catch(e){error.value=e instanceof Error ? e.message : '复制提交失败，请重试';}finally{busy.value=false;}
}
onMounted(async()=>{fitWorkspace();try{storages.value=(await props.request<{items:typeof storages.value}>('/plugins/cloud-copy/api/options')).items;await load();}catch{error.value='网盘列表读取失败，请刷新页面';}});
</script>
<template>
 <section ref="workspaceRoot" class="copy-workspace" @vue:before-unmount="dispose">
  <header><div><h2>跨网盘复制</h2></div><div class="workspace-actions"><UiButton variant="text" prepend-icon="mdi-history" @click="openRecords">复制记录</UiButton><UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新记录</UiButton></div></header>
  <p v-if="error" class="workspace-error" role="alert">{{error}}</p><p v-else-if="message" class="workspace-message" role="status">{{message}}</p>
  <div class="copy-workbench app-surface-boundary">
   <div class="mobile-copy-tabs" role="tablist" aria-label="复制位置"><button role="tab" :aria-selected="activePane==='source'" @click="activePane='source'">源文件<span v-if="source.selected.length">{{source.selected.length}}</span></button><button role="tab" :aria-selected="activePane==='target'" @click="activePane='target'">目标目录</button></div>
   <div class="copy-browsers"><FileBrowser :class="{'is-mobile-hidden':activePane!=='source'}" :request="request" :storages="sources" :disabled="busy" @change="source=$event" /><FileBrowser :class="{'is-mobile-hidden':activePane!=='target'}" :request="request" :storages="targets" :disabled="busy" target @change="target=$event" /></div>
   <div class="copy-controls"><VSelect v-model="policy" :items="policies" label="复制策略" variant="outlined" hide-details :disabled="busy" /><VTextField v-model="maxGib" type="number" min="1" label="临时空间上限（GiB）" variant="outlined" hide-details :disabled="busy" /><VSelect v-model="followup" :items="followups" label="复制完成后" variant="outlined" hide-details :disabled="busy" /><UiButton class="copy-submit" color="primary" prepend-icon="mdi-content-copy" :disabled="busy || !source.selected.length || !target.storage || Number(maxGib)<=0" :loading="busy" @click="submit">复制所选 {{source.selected.length}} 项</UiButton></div>
   <div class="mobile-copy-footer"><button class="mobile-target-row" @click="activePane='target'"><span>目标目录</span><strong>{{target.storage ? `${name(target.storage)} · ${target.path}` : '请选择'}}</strong><VIcon icon="mdi-chevron-right" size="16" /></button><div class="mobile-copy-actions"><UiButton class="mobile-settings-trigger" variant="text" icon="mdi-cog-outline" aria-label="复制设置" @click="settingsOpen=true" /><span class="mobile-selected-count">已选 {{source.selected.length}} 项</span><UiButton class="copy-submit" color="primary" :disabled="busy || !source.selected.length || !target.storage || Number(maxGib)<=0" :loading="busy" @click="submit">开始复制</UiButton></div></div>

  </div>
  <UiDialog v-if="settingsOpen" v-model="settingsOpen" :max-width="480" width="calc(100vw - 24px)"><UiCard class="mobile-copy-settings cc-statistics-dialog"><header class="records-header"><h2>复制设置</h2><UiButton icon="mdi-close" variant="text" aria-label="关闭复制设置" @click="settingsOpen=false" /></header><div class="mobile-settings-fields"><VSelect v-model="policy" :items="policies" label="复制策略" variant="outlined" hide-details :disabled="busy" /><VTextField v-model="maxGib" type="number" min="1" label="临时空间上限（GiB）" variant="outlined" hide-details :disabled="busy" /><VSelect v-model="followup" :items="followups" label="复制完成后" variant="outlined" hide-details :disabled="busy" /></div><footer><UiButton color="primary" @click="settingsOpen=false">完成</UiButton></footer></UiCard></UiDialog>
  <UiDialog v-if="recordsOpen" v-model="recordsOpen" :max-width="1060" width="calc(100vw - 32px)"><UiCard class="copy-batches cc-statistics-dialog"><header class="records-header"><h2>复制记录</h2><UiButton icon="mdi-close" class="app-dialog-close" variant="text" aria-label="关闭复制记录" @click="recordsOpen=false" /></header><main class="records-body"><div v-if="!batches.length" class="batch-empty">暂无手动复制批次</div><div v-else class="batch-table"><table><colgroup><col style="width:40%" /><col style="width:18%" /><col style="width:18%" /><col style="width:12%" /><col style="width:12%" /></colgroup><thead><tr><th>所选内容</th><th>源网盘</th><th>目标网盘</th><th>进度</th><th>状态</th></tr></thead><tbody><tr v-for="batch in batches" :key="batch.id"><td><span class="batch-name"><VTooltip :text="batch.names.join('、')" activator="parent" />{{batch.names.join('、')}}</span><small>{{batch.selected}} 项</small></td><td>{{name(batch.config.source)}}</td><td>{{name(batch.config.target)}}</td><td>已复制 {{batch.completed || 0}}<small v-if="batch.attention">待核对 {{batch.attention}}</small></td><td>{{states[batch.status] || batch.status}}</td></tr></tbody></table></div>
  </main></UiCard></UiDialog>
 </section>
</template>
<style scoped>
:global(.app-workspace:has(.copy-workspace)){min-height:0}
.copy-workspace{display:flex;flex-direction:column;min-height:0;overflow:hidden;color:var(--app-text,#1d2939);max-width:1600px;margin:auto}.copy-workspace>header{flex-shrink:0;display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.copy-workspace h2{color:var(--blue,#2b6dff);font-size:22px;font-weight:700}.copy-workspace header span{font-size:13px;color:var(--app-text-secondary,#738198)}.copy-workbench,.copy-batches{border:1px solid var(--app-border,#e2e8f0);border-radius:14px;background:var(--app-surface,#fff);overflow:hidden}.copy-workbench{display:flex;flex-direction:column;flex:1;min-height:0}.copy-browsers{flex:1;min-height:0;overflow:hidden;display:grid;grid-template-columns:1fr 1fr}.copy-browsers>:first-child{border-right:1px solid var(--app-border,#e2e8f0)}.copy-controls{flex-shrink:0;display:grid;grid-template-columns:1.5fr 1fr 1fr auto;align-items:center;gap:14px;padding:20px;border-top:1px solid var(--app-border,#e2e8f0)}.workspace-actions{display:flex;align-items:center;gap:6px}.copy-batches{margin:0;color:var(--app-text,#1d2939)}.records-header{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;border-bottom:1px solid var(--app-border,#e2e8f0)}.records-header h2{font-size:20px;font-weight:700}.records-body{max-height:70vh;overflow:auto}.records-body table{min-width:720px}.copy-batches>h3{padding:18px 20px;border-bottom:1px solid var(--app-border,#e2e8f0);font-size:16px}.batch-empty{padding:36px;text-align:center;color:var(--app-text-secondary,#738198)}.batch-table{overflow:auto}table{table-layout:fixed;width:100%;border-collapse:collapse;text-align:left;font-size:13px}th,td{overflow:hidden;text-overflow:ellipsis;padding:12px 20px;border-bottom:1px solid var(--app-border,#e2e8f0)}th{font-weight:500;color:var(--app-text-secondary,#738198)}.batch-name{display:block;max-width:100%;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}td small{display:block;color:var(--app-text-secondary,#738198)}.workspace-error{color:var(--app-danger-text,#bd3333);margin-bottom:14px}.workspace-message{color:var(--app-success-text,#148754);margin-bottom:14px}.batch-detail{padding:18px 20px}.batch-detail>div:first-child{display:flex;justify-content:space-between;align-items:center}.batch-record{display:flex;gap:20px;padding:10px 0;border-bottom:1px solid var(--app-border,#e2e8f0);font-size:13px}.batch-record>span:first-child{flex:1;overflow-wrap:anywhere}
.workspace-actions :deep(.v-btn){color:var(--app-text)}
.copy-workspace :deep(.v-field-label){color:var(--app-text-secondary)!important}
.copy-workspace :deep(.v-field__input){color:var(--app-text)}
.copy-workspace :deep(.v-field__append-inner){color:var(--app-text-secondary);opacity:1}
.copy-submit{border-radius:var(--app-control-radius,11px)!important}
@media(max-width:1000px){.copy-controls{grid-template-columns:1fr 1fr}}@media(max-width:700px){.copy-browsers{grid-template-columns:1fr;grid-template-rows:repeat(2,minmax(0,1fr))}.copy-browsers>:first-child{border-right:0;border-bottom:1px solid var(--app-border,#e2e8f0)}.copy-controls{grid-template-columns:1fr 1fr;padding:10px;gap:10px}.copy-workspace>header{align-items:flex-start;flex-wrap:wrap;gap:10px}.workspace-actions{margin-left:auto}th,td{padding:10px;white-space:nowrap}}
</style>

<style scoped>
.mobile-copy-tabs,.mobile-copy-footer{display:none}.mobile-settings-fields{display:grid;gap:20px;padding:24px 20px}.mobile-copy-settings>footer{display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--app-border)}
@media(max-width:700px){
 .copy-workspace>header>div:first-child{display:none}.copy-workspace>header{margin-bottom:10px;justify-content:flex-end}.workspace-actions{gap:0}
 .copy-browsers{grid-template-rows:minmax(0,1fr)}.copy-browsers>.is-mobile-hidden{display:none}.copy-browsers>:first-child{border:0}.copy-controls{display:none}
 .mobile-copy-tabs{display:flex;flex-shrink:0;border-bottom:1px solid var(--app-border);padding:0 12px;gap:20px}.mobile-copy-tabs button{position:relative;flex:1;padding:13px 4px;color:var(--app-text-secondary);font-size:14px;font-weight:600}.mobile-copy-tabs button[aria-selected=true]{color:var(--blue);box-shadow:inset 0 -2px var(--blue)}.mobile-copy-tabs span{margin-left:8px;font-size:12px}
 .mobile-copy-footer{display:block;flex-shrink:0;border-top:1px solid var(--app-border);padding:10px 12px}.mobile-copy-summary{display:flex;align-items:center;gap:12px;margin-bottom:10px;font-size:12px;color:var(--app-text-secondary)}.mobile-copy-summary>span{flex-shrink:0}.mobile-copy-summary button{display:flex;align-items:center;justify-content:flex-end;gap:3px;min-width:0;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;text-align:right;color:var(--app-text)}.mobile-copy-actions{display:grid;grid-template-columns:1fr 1.3fr;gap:12px}.mobile-copy-actions .copy-submit{min-height:42px}
}
</style>

<style scoped>
@media(max-width:700px){
 .mobile-copy-footer{padding:0}.mobile-target-row{display:flex;align-items:center;gap:12px;width:100%;min-height:42px;padding:10px 14px;border-bottom:1px solid var(--app-border);color:var(--app-text);text-align:left;font-size:12px}.mobile-target-row>span{flex-shrink:0;color:var(--app-text-secondary)}.mobile-target-row strong{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:400}.mobile-target-row>.v-icon{flex-shrink:0;color:var(--app-text-secondary)}
 .mobile-copy-actions{grid-template-columns:36px minmax(0,1fr) 124px;align-items:center;gap:10px;padding:10px 12px}.mobile-settings-trigger{width:36px!important;height:36px!important;color:var(--app-text)!important}.mobile-selected-count{color:var(--app-text-secondary);font-size:12px}.mobile-copy-actions .copy-submit{font-size:14px}
}
</style>
