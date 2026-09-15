<script setup lang="ts">
import {type Component} from 'vue';
export interface CopyRecord {
 id?:string;identity?:string;row_key?:string;batch_id?:string;origin?:string;name?:string;path?:string;names?:string[];
 source_name?:string;target_storage_name?:string;config?:{source:string;target:string};status:string;outcome?:string;
 method?:string;methods?:string[];reason?:string;notes?:string[];selected?:number;completed?:number;pending?:number;
 directories?:number;skipped?:number;current_file?:string;phase?:string;error?:string;can_retry?:boolean;can_delete?:boolean;
}
const props=defineProps<{rows:CopyRecord[];buttonComponent:Component;busy?:boolean;plain?:boolean;showOrigin?:boolean;storageNames?:Record<string,string>;emptyText?:string}>();
const emit=defineEmits<{action:[action:'retry'|'delete',key:string]}>();
const UiButton=props.buttonComponent;
const labels:Record<string,string>={completed:'复制完成',copied:'等待交接',uncertain:'结果待确认',conflict:'同名冲突',skipped:'已跳过',retry:'等待重试',failed:'复制失败',queued:'等待执行',running:'正在复制',partial:'部分复制成功'};
const methods:Record<string,string>={rapid:'秒传',download_rapid:'下载后秒传',relay:'中转上传',existing:'目标已存在'};
const key=(row:CopyRecord)=>row.row_key || row.id || row.identity || '';
const title=(row:CopyRecord)=>row.names?.join('、') || row.name || row.path || '';
const status=(row:CopyRecord)=>row.outcome || row.status;
const stateLabel=(row:CopyRecord)=>labels[status(row)] || status(row);
const tone=(row:CopyRecord)=>status(row)==='completed'?'saved':['running','queued','copied'].includes(status(row))?'waiting':'attention';
function account(row:CopyRecord,target=false){
 const id=row.config?.[target?'target':'source'] || '';
 const label=target?row.target_storage_name:row.source_name;
 return label || props.storageNames?.[id] || id;
}
function transfer(row:CopyRecord){const values=row.methods || (row.method?[row.method]:[]);return values.length?values.map(value=>methods[value] || '其他方式').join('、'):'—';}
function reason(row:CopyRecord){
 if(row.error)return row.error;
 if(row.notes?.length)return row.notes.join(' ');
 if(!row.reason || row.status==='completed')return '';
 return ({rapid_material_unavailable:'当前策略无法直接秒传',rapid_not_matched:'未命中秒传，文件未复制'} as Record<string,string>)[row.reason] || (/[\u3400-\u9fff]/.test(row.reason)?row.reason:'具体原因请查看运行日志');
}
</script>
<template>
 <div class="copy-records-table" :class="{plain}"><table><colgroup><col><col style="width:14%"><col style="width:14%"><col style="width:13%"><col style="width:13%"><col style="width:116px"><col style="width:44px"></colgroup>
 <thead><tr><th>文件名称</th><th>源网盘</th><th>目标网盘</th><th>传输方式</th><th>进度</th><th>处理结果</th><th class="record-actions" aria-label="记录操作"></th></tr></thead>
 <tbody><tr v-for="row in rows" :key="key(row)">
  <td><strong class="file">{{title(row)}}</strong><small v-if="row.path && row.path !== row.name" class="path">{{row.path}}</small><small v-if="row.selected && row.selected > 1">{{row.selected}} 项</small><small v-if="showOrigin">{{row.origin==='manual'?'手动复制':'规则任务'}}</small><small v-if="row.current_file" class="path">当前：{{row.current_file}}</small></td>
  <td><span class="account">{{account(row)}}</span></td><td><span class="account">{{account(row,true)}}</span></td><td>{{transfer(row)}}</td>
  <td>已复制 {{row.completed ?? (['completed','copied'].includes(status(row))?1:0)}}<small v-if="row.pending">待处理 {{row.pending}}</small><small v-if="row.directories">待扫描目录 {{row.directories}}</small><small v-if="row.skipped">已跳过 {{row.skipped}}</small></td>
  <td><span class="pill" :class="tone(row)">{{stateLabel(row)}}</span><small v-if="row.phase && row.phase!==stateLabel(row)">{{row.phase}}</small><small v-if="!plain && reason(row)" class="reason">{{reason(row)}}</small></td>
  <td class="record-actions"><VMenu location="bottom end"><template #activator="{props:menuProps}"><UiButton icon="mdi-dots-vertical" variant="text" size="small" aria-label="记录操作" :aria-expanded="menuProps['aria-expanded']" :aria-haspopup="menuProps['aria-haspopup']" @click="menuProps.onClick" /></template><VList class="card-action-menu" density="compact" nav><VListItem title="重试" prepend-icon="mdi-refresh" :disabled="busy || !row.can_retry" @click="emit('action','retry',key(row))"/><VListItem title="删除" prepend-icon="mdi-trash-can-outline" base-color="error" :disabled="busy || !row.can_delete" @click="emit('action','delete',key(row))"/></VList></VMenu></td>
 </tr><tr v-if="!rows.length"><td colspan="7" class="empty">{{emptyText || '暂无复制记录'}}</td></tr></tbody></table></div>
</template>
<style scoped>
.copy-records-table{overflow:auto;border:1px solid var(--app-border-subtle,#e0e6ef);border-radius:10px;color:var(--app-text,#1a2434);font-family:var(--app-font-family,inherit);font-size:13px}table{table-layout:fixed;width:100%;min-width:860px;border-collapse:collapse;text-align:left}th,td{padding:12px 12px;border-bottom:1px solid var(--app-border-subtle,#e0e6ef);font-size:13px;vertical-align:middle}th{font-weight:600;white-space:nowrap;background:var(--app-surface-subtle,#f5f7fb)}td{height:68px}tbody tr:last-child td{border-bottom:0}.file,.path,.account{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file{font-size:13px;font-weight:500}small{display:block;font-size:11px;color:var(--app-text-muted,#73819a);margin-top:6px;line-height:1.45}.reason{overflow-wrap:anywhere}.pill{display:inline-block;border-radius:20px;padding:4px 9px;font-size:11px;white-space:nowrap}.saved{background:var(--app-success-soft,#e8f5ef);color:var(--app-success-text,#00865a)}.waiting{background:var(--app-primary-soft,#edf3ff);color:var(--app-primary,#2968ff)}.attention{background:var(--app-warning-soft,#fff4df);color:var(--app-warning-text,#a87821)}.record-actions{width:44px;padding:8px 2px;text-align:center}.empty{text-align:center;padding:32px;color:var(--app-text-muted)}
.copy-records-table.plain{border:0;border-radius:0}
</style>
