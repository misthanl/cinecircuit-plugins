<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
interface Row { media?: string; provider?: string; language?: string; format?: string; status?: string; reason?: string }
interface Summary { version?: number; media?: number; saved?: number; skipped?: number; failed?: number; completed_media?: number; bilingual?: number; converted?: number; rows?: Row[]; total_rows?: number }
interface Run { status?: string; started_at?: string; finished_at?: string; result?: { statistics?: Summary; media_count?: number; subtitle_count?: number; saved_count?: number } }
const props = defineProps<{
  context: { close: () => void };
  request: <T = unknown>(path: string, init?: RequestInit) => Promise<T>;
  dialogComponent: Component; cardComponent: Component; buttonComponent: Component;
}>();
const UiDialog = props.dialogComponent, UiCard = props.cardComponent, UiButton = props.buttonComponent;
const loading = ref(false), error = ref("");
const latest = ref<Run | null>(null);
const page = ref(1);
const expanded = ref<Record<number, boolean>>({});
const stats = computed(() => latest.value?.result?.statistics);
const rows = computed(() => stats.value?.rows || []);
const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / 8)));
const visibleRows = computed(() => rows.value.slice((page.value - 1) * 8, page.value * 8));
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : 0;
const legacyResult = computed(() => latest.value?.result);
const checkedMedia = computed(() => number(stats.value?.media ?? legacyResult.value?.media_count));
const savedSubtitles = computed(() => number(stats.value?.saved ?? legacyResult.value?.saved_count));
const metrics = computed(() => [
  { label: "检查媒体", value: checkedMedia.value },
  { label: "保存字幕", value: savedSubtitles.value },
  { label: "已跳过", value: number(stats.value?.skipped) },
  { label: "处理失败", value: number(stats.value?.failed) },
]);
function language(value?: string) {
  return ({ "zh-CN-en": "简体中英双语", "zh-TW-en": "繁体中英双语", "zh-CN": "简体中文", "zh-TW": "繁体中文", zh: "中文（未区分简繁）", en: "英语", ja: "日语", ko: "韩语" } as Record<string, string>)[value || ""] || "—";
}
function rowStatus(value?: string) { return ({ saved: "已保存", skipped: "已跳过", failed: "失败" } as Record<string, string>)[value || ""] || "—"; }
async function load() {
  if (loading.value) return;
  loading.value = true; error.value = "";
  try {
    const data = await props.request<{ items?: Run[] }>("/plugins/subtitle-manager/runs?limit=1");
    latest.value = data.items?.[0] || null;
    page.value = 1; expanded.value = {};
  } catch { error.value = "统计数据加载失败，请刷新重试"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiDialog :model-value="true" :max-width="1000" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="subtitle-statistics">
      <header class="stats-header"><h2>字幕管理助手 · 数据统计</h2><UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" /></header>
      <main class="stats-body">
        <p v-if="error" role="alert">{{ error }}</p>
        <p v-else-if="loading && !latest">正在读取统计数据…</p>
        <template v-else>
          <section class="metrics" aria-label="处理指标">
            <article v-for="metric in metrics" :key="metric.label"><h3>{{ metric.label }}</h3><strong>{{ metric.value }}</strong></article>
          </section>
          <section aria-label="字幕明细">
            <h3 class="detail-title">字幕明细</h3>
            <div class="table-scroll"><table><thead><tr><th>媒体名称</th><th>字幕源</th><th>语言</th><th>格式</th><th>处理结果</th></tr></thead><tbody>
              <template v-for="(row, index) in visibleRows" :key="`${page}-${index}`">
                <tr><td>{{ row.media || '—' }}</td><td>{{ row.provider || '—' }}</td><td>{{ language(row.language) }}</td><td>{{ row.format || '—' }}</td><td><span class="pill" :class="row.status">{{ rowStatus(row.status) }}</span><button v-if="row.reason" class="reason-toggle" :aria-expanded="!!expanded[index]" aria-label="查看处理原因" @click="expanded[index] = !expanded[index]">{{ expanded[index] ? '⌃' : '⌄' }}</button></td></tr>
                <tr v-if="row.reason && expanded[index]"><td colspan="5" class="reason" :class="row.status">{{ row.reason }}</td></tr>
              </template>
              <tr v-if="!rows.length"><td colspan="5" class="empty">暂无字幕处理明细</td></tr>
            </tbody></table></div>
            <div class="pagination"><span>共 {{ rows.length }} 条<span v-if="(stats?.total_rows || 0) > rows.length">（仅展示前 {{ rows.length }} 条）</span></span><div><UiButton variant="text" :disabled="page <= 1" aria-label="上一页" @click="page--; expanded = {}">‹</UiButton><span>{{ page }} / {{ pages }}</span><UiButton variant="text" :disabled="page >= pages" aria-label="下一页" @click="page++; expanded = {}">›</UiButton></div></div>
          </section>
        </template>
      </main>
      <footer><UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</UiButton></footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.subtitle-statistics{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);overflow:hidden;border-radius:18px!important;background:var(--app-dialog-surface,#fff);color:var(--app-text,#1a2434);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}
.stats-header{display:flex;align-items:center;justify-content:space-between;flex:none;height:var(--app-plugin-dialog-header-height,58px);padding:0 24px;border-bottom:1px solid var(--app-border-subtle,#e0e6ef)}
.stats-header h2{margin:0;font-size:var(--app-font-size-title,18px)}.stats-body{padding:24px;overflow:auto;min-height:0;display:grid;gap:20px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metrics article{border:1px solid var(--app-border-subtle);border-radius:12px;padding:15px 16px;min-width:0;background:var(--app-surface-muted)}
h3{margin:0;font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}.metrics h3,.secondary,.pagination{color:var(--app-text-muted,#73819a)}.metrics h3{font-size:var(--app-font-size-caption,12px);font-weight:400}.metrics strong{display:block;margin:10px 0 0;font-size:24px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--app-text)}
.pill{display:inline-block;border-radius:20px;padding:4px 10px;font-size:var(--app-font-size-helper,12px)}.saved{background:var(--app-success-soft);color:var(--app-success-text)}.failed{background:var(--app-danger-soft);color:var(--app-danger-text)}.skipped{background:var(--app-surface-muted);color:var(--app-text-secondary)}
.detail-title{margin-bottom:14px}.table-scroll{overflow-x:auto;border:1px solid var(--app-border-subtle,#e0e6ef);border-radius:10px}table{width:100%;border-collapse:collapse;text-align:left}th,td{padding:12px 16px;border-bottom:1px solid var(--app-border-subtle,#e0e6ef)}th{background:var(--app-surface-subtle,#f5f7fb);white-space:nowrap}td:first-child{max-width:260px;overflow-wrap:anywhere}td:not(:first-child){white-space:nowrap}.reason{white-space:normal!important}.reason-toggle{border:0;background:transparent;color:inherit;margin-left:12px;cursor:pointer}.reason-toggle:focus-visible{outline:2px solid rgb(var(--v-theme-primary,41,104,255))}.empty{text-align:center;color:var(--app-text-muted,#73819a);padding:30px}.pagination{display:flex;align-items:center;justify-content:space-between;margin-top:12px}.pagination>div{display:flex;align-items:center;gap:8px}footer{display:flex;justify-content:flex-end;padding:10px 20px;border-top:1px solid var(--app-border-subtle,#e0e6ef)}
@media(max-width:760px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.stats-body{padding:16px}.metrics article{padding:14px 16px}.stats-header{padding:0 16px}}
</style>
