<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import type { PluginContributionContext } from "@cinecircuit/plugin-sdk";
type Task = { id: string; name: string; site_id: string; downloader_id: string; enabled: boolean; removed?: boolean; seeding_limit_gib: number; interval_minutes: number; cron: string; download_count: number; seed_count: number; upload_speed: number; download_speed: number; size: number; uploaded: number; downloaded: number; available: boolean; history_complete: boolean };
type Entry = { id: string; task_id: string; name: string; site_id: string; timestamp: number; added: number; cleaned: number; skipped: number; failed: number; matched: number; reason: string };
type Resource = { id: string; name: string };
type Report = { tasks: Task[]; history: Entry[]; updated_at: number; enabled: boolean };
const props = defineProps<{ context: PluginContributionContext; request: <T>(path: string, init?: RequestInit) => Promise<T>; buttonComponent: Component; cardComponent: Component; dialogComponent: Component }>();
const UiButton = props.buttonComponent, UiCard = props.cardComponent, UiDialog = props.dialogComponent;
const report = ref<Report | null>(null), sites = ref<Resource[]>([]), downloaders = ref<Resource[]>([]);
const busy = ref(false), error = ref(""), taskId = ref(""), siteId = ref(""), onlyErrors = ref(false), page = ref(1), expanded = ref("");
const selected = computed(() => (report.value?.tasks || []).filter(t => (!taskId.value || t.id === taskId.value) && (!siteId.value || t.site_id === siteId.value)));
const history = computed(() => (report.value?.history || []).filter(e => (!taskId.value || e.task_id === taskId.value) && (!siteId.value || e.site_id === siteId.value) && (!onlyErrors.value || e.failed > 0)));
const pages = computed(() => Math.max(1, Math.ceil(history.value.length / 8)));
const entries = computed(() => history.value.slice((page.value - 1) * 8, page.value * 8));
const total = (key: "uploaded" | "downloaded" | "size") => selected.value.reduce((sum, t) => sum + t[key], 0);
const unavailable = computed(() => selected.value.some(t => !t.available));
const incomplete = computed(() => selected.value.some(t => !t.history_complete));
const ratio = computed(() => total("downloaded") > 0 ? (total("uploaded") / total("downloaded")).toFixed(2) : "—");
function bytes(value: number): string { if (!Number.isFinite(value)) return "—"; const units = ["B", "KiB", "MiB", "GiB", "TiB"]; let n = value, i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return `${n.toLocaleString(undefined, { maximumFractionDigits: i > 0 ? 1 : 0 })} ${units[i]}`; }
function date(value: number): string { return value ? new Date(value * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"; }
function resource(rows: Resource[], id: string): string { return rows.find(r => r.id === id)?.name || (id ? "资源不可用" : "未指定"); }
function percent(task: Task): number { return task.seeding_limit_gib > 0 ? Math.min(100, task.size / (task.seeding_limit_gib * 1024 ** 3) * 100) : 0; }
function changePage(value: number) { page.value = Math.min(pages.value, Math.max(1, Math.trunc(Number(value) || 1))); expanded.value = ""; }
function reset() { changePage(1); }
function inputPage(event: Event) { const input = event.target as HTMLInputElement; changePage(Number(input.value)); input.value = String(page.value); }
async function load() {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try {
    const [stats, inventory] = await Promise.all([props.request<Report>("/plugins/brush-flow/api/statistics"), props.request<{ sites: Resource[]; downloaders: Resource[] }>("/plugins/brush-flow/api/inventory")]);
    report.value = stats; sites.value = inventory.sites || []; downloaders.value = inventory.downloaders || []; changePage(page.value);
  } catch { error.value = "统计读取失败，请重试；已有数据保留为上次结果。"; }
  finally { busy.value = false; }
}
onMounted(load);
</script>
<template>
  <UiDialog :model-value="true" max-width="980" scrollable @update:model-value="!$event && context.close()">
  <UiCard class="traffic-statistics-dialog">
    <header class="statistics-heading"><h2>站点刷流 · 数据统计</h2><UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close()" /></header>
    <section class="traffic-statistics" :aria-busy="busy">
    <div class="stat-toolbar">
      <VSelect v-model="taskId" aria-label="筛选任务" :items="[{ title: '全部任务', value: '' }, ...(report?.tasks || []).map(t => ({ title: t.name, value: t.id }))]" variant="outlined" density="compact" hide-details @update:model-value="reset" />
      <VSelect v-model="siteId" aria-label="筛选站点" :items="[{ title: '全部站点', value: '' }, ...sites.map(s => ({ title: s.name, value: s.id }))]" variant="outlined" density="compact" hide-details @update:model-value="reset" />
    </div>
    <p v-if="error" class="stat-error" role="alert">{{ error }}</p>
    <template v-if="report">
      <div class="stat-totals">
        <div><span>累计上传</span><strong>{{ incomplete && !total('uploaded') ? '—' : bytes(total('uploaded')) }}</strong></div>
        <div><span>累计下载</span><strong>{{ incomplete && !total('downloaded') ? '—' : bytes(total('downloaded')) }}</strong></div>
        <div><span>分享率</span><strong>{{ ratio }}</strong></div>
        <div><span>当前保种体积</span><strong>{{ unavailable ? '—' : bytes(total('size')) }}</strong></div>
      </div>
      <p v-if="unavailable" class="stat-error" role="status">部分下载任务暂时无法读取，当前占用和速度显示为 —。</p>
      <div class="stat-heading"><h3>任务概览</h3><span>{{ selected.length }} 个任务 · {{ selected.filter(t => t.enabled && report?.enabled).length }} 个已启用</span></div>
      <div class="stat-task-list">
        <article v-for="task in selected" :key="task.id" class="stat-task">
          <div class="stat-task-info"><div><h4>{{ task.name }}</h4><span class="status" :class="{ paused: !task.enabled || !report.enabled }">{{ task.removed ? '已移除' : task.enabled && report.enabled ? '已启用' : '已停用' }}</span></div>
            <p>{{ resource(sites, task.site_id) }} → {{ resource(downloaders, task.downloader_id) }}</p>
            <div class="capacity"><span>保种体积</span><b>{{ task.available ? bytes(task.size) : '—' }}</b><span>/ {{ task.seeding_limit_gib > 0 ? task.seeding_limit_gib + ' GiB' : '不限体积' }}</span></div>
            <progress v-if="task.available && task.seeding_limit_gib > 0" :value="percent(task)" max="100" :aria-label="task.name + '保种体积占用'" />
            <small>{{ !task.enabled || !report.enabled ? '调度已停止' : task.cron ? 'Cron：' + task.cron : '每 ' + task.interval_minutes + ' 分钟执行' }}</small>
          </div>
          <dl><div><dt>下载中</dt><dd>{{ task.available ? task.download_count : '—' }}</dd></div><div><dt>保种中</dt><dd>{{ task.available ? task.seed_count : '—' }}</dd></div><div><dt>上传速度</dt><dd>{{ task.available ? bytes(task.upload_speed) + '/s' : '—' }}</dd></div><div><dt>下载速度</dt><dd>{{ task.available ? bytes(task.download_speed) + '/s' : '—' }}</dd></div></dl>
        </article>
        <p v-if="!selected.length" class="stat-empty">没有符合筛选条件的任务</p>
      </div>
      <div class="stat-heading"><h3>最近执行</h3><div class="segments"><button type="button" :class="{ on: !onlyErrors }" @click="onlyErrors = false; reset()">全部</button><button type="button" :class="{ on: onlyErrors }" @click="onlyErrors = true; reset()">有异常</button></div></div>
      <div class="execution-table"><table><thead><tr><th>执行时间</th><th>任务</th><th>新增</th><th>清理</th><th>跳过</th><th>结果</th><th aria-label="详情" /></tr></thead><tbody>
        <template v-for="entry in entries" :key="entry.id"><tr><td>{{ date(entry.timestamp) }}</td><td>{{ entry.name }}</td><td>{{ entry.added }}</td><td>{{ entry.cleaned }}</td><td>{{ entry.skipped }}</td><td><span class="status" :class="{ failed: entry.failed > 0, paused: entry.reason !== '成功' && !entry.failed }">{{ entry.reason }}</span></td><td><button type="button" :aria-label="'查看 ' + entry.name + ' 执行详情'" :aria-expanded="expanded === entry.id" @click="expanded = expanded === entry.id ? '' : entry.id"><VIcon :icon="expanded === entry.id ? 'mdi-chevron-down' : 'mdi-chevron-right'" /></button></td></tr>
          <tr v-if="expanded === entry.id"><td colspan="7" class="execution-detail">匹配 {{ entry.matched }} · 失败 {{ entry.failed }} · {{ entry.reason }}</td></tr></template>
      </tbody></table><p v-if="!entries.length" class="stat-empty">暂无执行记录，新执行结果会显示在这里。</p></div>
      <div class="stat-pagination"><span>最近 {{ history.length }} 条记录</span><div><button aria-label="第一页" :disabled="page <= 1" @click="changePage(1)"><VIcon icon="mdi-page-first" /></button><button aria-label="上一页" :disabled="page <= 1" @click="changePage(page - 1)"><VIcon icon="mdi-chevron-left" /></button><input :value="page" aria-label="页码" type="number" min="1" :max="pages" @change="inputPage" @keydown="$event.key === 'Enter' && inputPage($event)"><span>/ {{ pages }}</span><button aria-label="下一页" :disabled="page >= pages" @click="changePage(page + 1)"><VIcon icon="mdi-chevron-right" /></button><button aria-label="最后一页" :disabled="page >= pages" @click="changePage(pages)"><VIcon icon="mdi-page-last" /></button></div></div>
    </template>
    </section>
    <footer class="statistics-footer">
      <span class="updated">{{ report ? '更新于 ' + date(report.updated_at) : '正在读取统计…' }}</span>
      <UiButton prepend-icon="mdi-refresh" variant="text" :loading="busy" :disabled="busy" @click="load">刷新</UiButton>
    </footer>
  </UiCard>
  </UiDialog>
</template>
<style scoped>
.traffic-statistics-dialog{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);overflow:hidden;border-radius:18px!important;background:var(--app-dialog-surface,#fff);color:var(--app-text)}.statistics-heading{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;border-bottom:1px solid var(--app-border-subtle,#e1e7f0);flex:0 0 auto}.statistics-heading h2{margin:0;font-size:18px}.traffic-statistics{color:var(--app-text);font-size:14px;min-width:0;overflow:auto;padding:20px}.stat-toolbar{display:flex;gap:16px;align-items:center;margin-bottom:18px}.stat-toolbar .v-input{max-width:190px;min-width:120px}.updated{color:var(--app-text-muted,#7b89a4);font-size:12px;flex:1}.stat-totals{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.stat-totals>div{display:flex;flex-direction:column;gap:7px;align-items:flex-start;text-align:left;min-width:0;padding:15px 16px;border:1px solid var(--app-border-subtle,#e2e7f0);border-radius:12px;background:var(--app-surface-muted,#f4f6fb)}.stat-totals span,.stat-heading>span,dt{color:var(--app-text-muted,#7b89a4);font-size:12px}.stat-totals strong{font-family:inherit;font-size:var(--app-font-size-metric,24px);font-weight:var(--app-font-weight-metric,700);line-height:1.15;color:var(--app-text,#202939);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.stat-note{color:var(--app-text-muted,#7b89a4);font-size:12px;margin:9px 0}.stat-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:22px 0 12px}.stat-heading h3{margin:0;font-size:16px;font-weight:650}.stat-task-list{border:1px solid var(--app-border-subtle,#e1e7f0);border-radius:12px;overflow:hidden}.stat-task{display:grid;grid-template-columns:minmax(220px,1fr) 1.35fr;gap:20px;padding:16px;border-bottom:1px solid var(--app-border-subtle,#e1e7f0)}.stat-task:last-child{border:0}.stat-task-info>div:first-child{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stat-task h4{margin:0;font-size:14px;overflow-wrap:anywhere}.stat-task p{font-size:12px;color:var(--app-text-muted,#7b89a4);margin:7px 0}.status{display:inline-block;padding:4px 9px;border-radius:7px;font-size:12px;color:var(--app-success-text);background:var(--app-success-soft);white-space:nowrap}.status.paused{color:var(--app-text-secondary,#657087);background:var(--app-surface-subtle,#f1f3f7)}.status.failed{color:var(--app-danger-text);background:var(--app-danger-soft)}.capacity{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:12px}.capacity>span{color:var(--app-text-muted,#7b89a4)}progress{appearance:none;display:inline-block;border:0;border-radius:10px;width:110px;height:7px;margin:9px 10px 0 0;overflow:hidden}progress::-webkit-progress-bar{background:var(--app-surface-disabled)}progress::-webkit-progress-value{background:#2968ff}progress::-moz-progress-bar{background:#2968ff}.stat-task small{font-size:11px;color:var(--app-text-muted,#7b89a4)}dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;align-items:center}dl>div{padding-left:14px;border-left:1px solid var(--app-border-subtle,#e1e7f0)}dd{margin:8px 0 0;font-weight:600;font-size:16px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.segments{display:flex;border:1px solid var(--app-border-subtle,#e1e7f0);padding:3px;border-radius:8px}.segments button{font:inherit;font-size:12px;background:none;border:0;padding:7px 13px;color:inherit;cursor:pointer}.segments .on{background:#2968ff;color:#fff;border-radius:5px}.execution-table{overflow:auto;border:1px solid var(--app-border-subtle,#e1e7f0);border-radius:10px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--app-border-subtle,#e1e7f0);font-size:12px}th{font-weight:500;background:var(--app-surface-subtle,#f4f6fa);color:var(--app-text-muted,#7b89a4)}tbody tr:last-child td{border-bottom:0}td button,.stat-pagination button{border:0;background:none;color:inherit;cursor:pointer;min-width:32px;min-height:32px}.execution-detail{background:var(--app-surface-subtle,#f4f6fa)}.stat-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;font-size:12px;color:var(--app-text-muted,#7b89a4)}.stat-pagination>div{display:flex;align-items:center;gap:6px}.stat-pagination input{width:48px;text-align:center;border:1px solid var(--app-border-subtle,#e1e7f0);border-radius:6px;padding:5px;background:var(--app-surface,#fff);color:inherit}.stat-pagination button:disabled{opacity:.35;cursor:default}button:focus-visible,input:focus-visible{outline:2px solid #2968ff;outline-offset:2px}.stat-empty{text-align:center;padding:24px;color:var(--app-text-muted,#7b89a4)}.stat-error{color:var(--app-danger-text);background:var(--app-danger-soft);padding:10px;border-radius:6px;font-size:12px}
@media(max-width:700px){.traffic-statistics-dialog{max-height:min(720px,calc(100dvh - 112px))}.traffic-statistics{padding:16px}.stat-toolbar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stat-toolbar .v-input{max-width:none;min-width:0;width:100%}.updated{grid-column:1;line-height:1.5}.stat-toolbar>.v-btn{justify-self:end}.stat-totals{grid-template-columns:repeat(2,minmax(0,1fr))}.stat-task{grid-template-columns:1fr;gap:14px}dl{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 0}dl>div:nth-child(odd){padding-left:0;border:0}dd{font-size:14px;white-space:nowrap}.stat-pagination{flex-wrap:wrap}.stat-heading>span{font-size:11px}.execution-table table{min-width:620px}}
.statistics-footer{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:12px;padding:10px 18px;border-top:1px solid var(--app-border-subtle,#e2e7f0);background:var(--app-surface,#fff)}
.statistics-footer>.v-btn{flex:0 0 auto;color:var(--app-text,#202939)}
</style>
