<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
interface Row { identity: string; name: string; path: string; source_name: string; target_storage_name: string; status: string; method?: string; reason?: string; target_name?: string; handoff?: string }
interface Snapshot { configured: boolean; configuration_message?: string; counts: Record<string,number>; records: Row[]; total: number; page: number; pages: number; directories: number; paused: boolean; updated_at?: number }
const props = defineProps<{context?: {close: () => void}; page?: boolean; request: <T = unknown>(path: string, init?: RequestInit) => Promise<T>; dialogComponent: Component; cardComponent: Component; buttonComponent: Component}>();
const UiDialog = props.dialogComponent, UiCard = props.cardComponent, UiButton = props.buttonComponent;
const data = ref<Snapshot | null>(null), busy = ref(false), error = ref("");
const search = ref(""), status = ref(""), method = ref(""), pageNumber = ref(1), expanded = ref("");
let generation = 0;
const labels: Record<string,string> = {completed:"复制完成",copied:"等待交接",uncertain:"结果待确认",conflict:"同名冲突",skipped:"未命中秒传",retry:"等待重试",failed:"复制失败"};
const methods: Record<string,string> = {rapid:"秒传",relay:"中转",existing:"已存在"};
const metrics = computed(() => [{key:"completed",label:"已复制"},{key:"skipped",label:"已跳过"},{key:"attention",label:"待核对"},{key:"pending",label:"待处理"}]);
const statusOptions = [{title:"全部处理结果",value:""}, ...Object.entries(labels).map(([value,title]) => ({value,title}))];
const methodOptions = [{title:"全部复制方式",value:""}, ...Object.entries(methods).map(([value,title]) => ({value,title}))];
const updated = computed(() => data.value?.updated_at ? new Date(data.value.updated_at*1000).toLocaleTimeString("zh-CN",{hour12:false}) : "");
async function load(reset = false) {
  if (reset) pageNumber.value = 1;
  const current = ++generation;
  busy.value = true; error.value = "";
  const query = new URLSearchParams({page:String(pageNumber.value), search:search.value, status:status.value, method:method.value});
  try {
    const result = await props.request<Snapshot>(`/plugins/cloud-copy/api/status?${query}`);
    if (current !== generation) return;
    data.value = result; pageNumber.value = result.page; expanded.value = "";
  } catch { if (current === generation) error.value = "统计数据加载失败，请刷新重试"; }
  finally { if (current === generation) busy.value = false; }
}
async function action(name: string, identity?: string) {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try {
    await props.request(`/plugins/cloud-copy/api/${name}`, {method:"POST", body:JSON.stringify({identity})});
    await load();
  } catch { error.value = "操作未完成，请重试"; }
  finally { busy.value = false; }
}
function paginate(offset: number) { pageNumber.value += offset; void load(); }
function tone(value: string) { return value === "completed" ? "saved" : value === "copied" ? "waiting" : ["conflict","uncertain","failed","retry"].includes(value) ? "attention" : "skipped"; }
onMounted(() => load());
</script>
<template>
  <component :is="page ? 'div' : UiDialog" :model-value="true" :max-width="1060" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context?.close(); }">
    <UiCard class="copy-statistics cc-statistics-dialog">
      <header><h2>跨网盘复制 · 数据统计</h2><UiButton v-if="!page" class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context?.close()" /></header>
      <main>
        <p v-if="error" class="error" role="alert">{{error}}</p>
        <section class="metrics"><article v-for="metric in metrics" :key="metric.key"><span>{{metric.label}}</span><strong>{{ data ? data.counts[metric.key] || 0 : '—' }}</strong></article></section>
        <div class="heading"><h3>复制明细</h3><span v-if="data?.configured" class="muted">剩余 {{data.directories}} 个目录</span><UiButton color="primary" class="push" prepend-icon="mdi-folder-search-outline" variant="text" :disabled="busy || !data?.configured" @click="action('rescan')">重新扫描</UiButton><UiButton :prepend-icon="data?.paused ? 'mdi-play-outline' : 'mdi-pause'" variant="text" :disabled="busy || !data?.configured" @click="action(data?.paused ? 'resume' : 'pause')">{{data?.paused ? '继续' : '暂停'}}</UiButton></div>
        <template v-if="data?.configured">
          <div class="filters"><VTextField v-model="search" placeholder="搜索文件名或路径" aria-label="搜索文件名或路径" prepend-inner-icon="mdi-magnify" variant="outlined" hide-details clearable @keyup="(event: KeyboardEvent) => { if (event.key === 'Enter') load(true); }" @click:clear="search = ''; load(true)" @blur="load(true)" /><VSelect v-model="status" :items="statusOptions" aria-label="处理结果" variant="outlined" hide-details @update:model-value="load(true)" /><VSelect v-model="method" :items="methodOptions" aria-label="复制方式" variant="outlined" hide-details @update:model-value="load(true)" /></div>
          <div class="table-scroll"><table><colgroup><col style="width:33%"><col style="width:14%"><col style="width:14%"><col style="width:11%"><col style="width:15%"><col style="width:13%"></colgroup><thead><tr><th>文件名称</th><th>源网盘</th><th>目的网盘</th><th>复制方式</th><th>处理结果</th><th>操作</th></tr></thead><tbody>
            <template v-for="row in data.records" :key="row.identity"><tr><td><div><VTooltip :text="row.path" location="top" activator="parent" /><strong class="file">{{row.name || row.path}}</strong><small class="path">{{row.path}}</small></div></td><td><span class="cell-name">{{row.source_name}}</span></td><td><span class="cell-name">{{row.target_storage_name}}</span></td><td>{{methods[row.method || ''] || '—'}}</td><td><span class="pill" :class="tone(row.status)">{{labels[row.status] || row.status}}</span></td><td><UiButton color="primary" variant="text" size="small" @click="expanded = expanded === row.identity ? '' : row.identity">{{expanded === row.identity ? '收起详情' : '查看详情'}}</UiButton></td></tr>
            <tr v-if="expanded === row.identity"><td colspan="6" class="detail"><span>{{row.reason || (row.handoff ? `后续处理：${row.handoff}` : `目标文件：${row.target_name || row.name}`)}}</span><UiButton v-if="!['completed','copied'].includes(row.status)" variant="text" size="small" :disabled="busy" @click="action('retry',row.identity)">核对并重试</UiButton></td></tr></template>
            <tr v-if="!data.records.length"><td colspan="6" class="empty">{{search || status || method ? '没有符合条件的复制记录' : '暂无复制记录'}}</td></tr>
          </tbody></table></div>
          <div class="pagination"><span>共 {{data.total}} 条记录</span><div><UiButton variant="text" icon="mdi-chevron-left" aria-label="上一页" :disabled="busy || pageNumber <= 1" @click="paginate(-1)"/><span>{{pageNumber}} / {{data.pages}}</span><UiButton variant="text" icon="mdi-chevron-right" aria-label="下一页" :disabled="busy || pageNumber >= data.pages" @click="paginate(1)" /></div></div>
        </template>
        <div v-else-if="data" class="empty"><VIcon icon="mdi-folder-outline" size="42"/><h3>暂无复制记录</h3><p>{{data.configuration_message || '请先在插件配置中选择源网盘与目标网盘'}}</p></div>
      </main>
      <footer><span class="muted">{{updated ? `最近更新 ${updated}` : ''}}</span><UiButton prepend-icon="mdi-refresh" variant="text" :loading="busy" :disabled="busy" @click="load()">刷新</UiButton></footer>
    </UiCard>
  </component>
</template>
<style scoped>
.copy-statistics{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);overflow:hidden;border-radius:18px!important;background:var(--app-dialog-surface,#fff);color:var(--app-text,#1a2434);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}header{display:flex;align-items:center;justify-content:space-between;flex:none;height:var(--app-plugin-dialog-header-height,58px);padding:0 24px;border-bottom:1px solid var(--app-border-subtle,#e0e6ef)}h2{margin:0;font-size:var(--app-font-size-title,18px)}main{padding:24px;overflow:auto;min-height:0}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metrics article{border:1px solid var(--app-border-subtle);border-radius:12px;padding:15px 16px;background:var(--app-surface-muted)}.metrics span,.muted,.pagination{font-size:12px;color:var(--app-text-muted,#73819a)}.metrics strong{display:block;margin-top:10px;font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}.heading{display:flex;align-items:center;gap:12px;margin:22px 0 16px}h3{margin:0;font-size:14px}.push{margin-left:auto}.filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin-bottom:16px}.table-scroll{overflow-x:auto;border:1px solid var(--app-border-subtle,#e0e6ef);border-radius:10px}table{width:100%;min-width:820px;border-collapse:collapse;table-layout:fixed;text-align:left}td,th{padding:12px 14px;border-bottom:1px solid var(--app-border-subtle,#e0e6ef);font-size:12px}th{background:var(--app-surface-subtle,#f5f7fb);white-space:nowrap}td{height:68px}tbody tr:last-child td{border-bottom:0}.file,.path,.cell-name{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file{font-weight:500;font-size:13px}.path{margin-top:7px;color:var(--app-text-muted);font-size:11px}.pill{display:inline-block;border-radius:20px;padding:4px 9px;font-size:11px;white-space:nowrap}.saved{background:var(--app-success-soft);color:var(--app-success-text)}.attention{background:var(--app-warning-soft,#fff4df);color:var(--app-warning-text,#a87821)}.waiting{background:var(--app-primary-soft,#edf3ff);color:rgb(var(--v-theme-primary,41,104,255))}.skipped{background:var(--app-surface-muted);color:var(--app-text-secondary)}.detail{white-space:normal;overflow-wrap:anywhere}.detail span{margin-right:16px}.empty{text-align:center;padding:45px 16px;color:var(--app-text-muted,#73819a)}.empty h3{margin-top:14px}.empty p{margin:12px 0}.pagination{display:flex;align-items:center;justify-content:space-between;margin-top:12px}.pagination>div{display:flex;align-items:center;gap:8px}footer{display:flex;align-items:center;justify-content:space-between;flex:none;padding:10px 20px;border-top:1px solid var(--app-border-subtle,#e0e6ef)}.error{color:var(--app-danger-text,#c62828);margin:0 0 16px}@media(max-width:760px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:16px}header{padding:0 16px}.heading{gap:5px;flex-wrap:wrap}.heading .muted{display:none}.filters{grid-template-columns:1fr 1fr}.filters>:first-child{grid-column:1/-1}}
</style>
