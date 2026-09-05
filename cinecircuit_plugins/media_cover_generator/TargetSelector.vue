<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
type Model=Record<string,unknown>;
type Item={value:string;title:string};
const props=defineProps<{modelValue:Model;disabled?:boolean;request:(path:string,init?:RequestInit)=>Promise<unknown>}>();
const emit=defineEmits<{ 'update:modelValue':[value:Model] }>();
const servers=ref<Item[]>([]);
const libraries=ref<Item[]>([]);
const loading=ref(false);
const error=ref('');
let revision=0;
let disposed=false;
function dispose(){disposed=true;revision++;}
const selectedServers=computed(()=>Array.isArray(props.modelValue.selected_servers)?props.modelValue.selected_servers.map(String):props.modelValue.server_id?[String(props.modelValue.server_id)]:[]);
const selectedLibraries=computed(()=>Array.isArray(props.modelValue.library_targets)?props.modelValue.library_targets.map(String):[]);
const libraryItems=computed(()=>[...libraries.value,...selectedLibraries.value.filter(value=>!libraries.value.some(item=>item.value===value)).map(value=>({value,title:`待确认媒体库 ${value}`}))]);
async function load(ids:string[],migrate=false){
  const requestRevision=++revision;
  loading.value=true;error.value='';
  try{
    const data=await props.request('/plugins/emby-cover-generator/api/targets?servers='+encodeURIComponent(JSON.stringify(ids))) as {servers:Item[];libraries:Item[];errors?:string[]};
    if(disposed||requestRevision!==revision)return;
    servers.value=data.servers||[];libraries.value=data.libraries||[];
    error.value=(data.errors||[]).join('；');
    if(migrate && props.modelValue.library_targets===undefined && ids.length===1 && !error.value){
      const legacy=props.modelValue.include_libraries||props.modelValue.library_ids;
      const selected=Array.isArray(legacy)?legacy.map(String):[];
      const targets=libraries.value.filter(item=>selected.includes(JSON.parse(item.value)[1])).map(item=>item.value);
      if(targets.length!==selected.length){error.value='部分原有媒体库已失效，请重新确认选择';return;}
      emit('update:modelValue',{...props.modelValue,selected_servers:ids,library_targets:targets});
    }
  }catch(reason){if(!disposed&&requestRevision===revision)error.value=reason instanceof Error?reason.message:'媒体服务器读取失败';}
  finally{if(!disposed&&requestRevision===revision)loading.value=false;}
}
function chooseServers(value:unknown){
  const ids=Array.isArray(value)?value.map(String):[];
  const targets=selectedLibraries.value.filter(value=>{try{return ids.includes(JSON.parse(value)[0]);}catch{return false;}});
  emit('update:modelValue',{...props.modelValue,selected_servers:ids,library_targets:targets,include_libraries:[],server_id:'',library_ids:[]});
  void load(ids);
}
onMounted(()=>void load(selectedServers.value,true));
</script>
<template>
  <div class="cover-targets" @vue:unmounted="dispose">
    <VSelect class="target-servers" label="媒体服务器" :items="servers" :model-value="selectedServers" multiple chips closable-chips clearable variant="outlined" hide-details="auto" :disabled="disabled" :loading="loading" no-data-text="暂无 Emby 或 Jellyfin 服务器" @update:model-value="chooseServers" />
    <VSelect class="target-libraries" label="更新媒体库" :items="libraryItems" :model-value="selectedLibraries" multiple chips closable-chips clearable variant="outlined" hide-details="auto" :disabled="disabled || !selectedServers.length" :loading="loading" no-data-text="暂无可选择的媒体库" @update:model-value="emit('update:modelValue',{...modelValue,library_targets:$event||[]})" />
    <div v-if="error" role="alert">{{ error }} <VBtn variant="text" :disabled="loading" @click="load(selectedServers)">重试</VBtn></div>
  </div>
</template>
<style scoped>
.cover-targets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;grid-column:1/-1;min-width:0;align-items:start}.cover-targets>div{min-width:0}.cover-targets [role=alert]{grid-column:1/-1;color:var(--app-danger,#c62828)}@media(max-width:680px){.cover-targets{grid-template-columns:1fr}}
</style>
