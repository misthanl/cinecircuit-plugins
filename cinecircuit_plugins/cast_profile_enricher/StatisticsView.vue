<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface RunResult {
  scanned_media?: number;
  scanned_people?: number;
  updated_profiles?: number;
  updated_images?: number;
  failures?: number;
  removed_people?: number;
  updated_names?: number;
  updated_roles?: number;
  updated_biographies?: number;
  no_chinese_role?: number;
  unmatched_people?: number;
  request_failures?: number;
  cache_hits?: number;
  resumed_media?: number;
  skipped_people?: number;
}
interface Progress extends RunResult { status?: string; current_media?: string[]; source?: string; elapsed_seconds?: number; }

interface RunRecord {
  display_status?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  result?: RunResult;
}

interface RunResponse { items?: RunRecord[]; }

const props = defineProps<{
  context: PluginContributionContext;
  request: CineCircuitPluginSdk["request"];
  buttonComponent: Component;
  cardComponent: Component;
  dialogComponent: Component;
  chipComponent: Component;
  alertComponent: Component;
}>();

const UiButton = props.buttonComponent;
const UiCard = props.cardComponent;
const UiDialog = props.dialogComponent;
const UiChip = props.chipComponent;
const UiAlert = props.alertComponent;
const latest = ref<RunRecord | null>(null);
const progress = ref<Progress>({});
const loading = ref(false);
const error = ref("");

function count(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
}

const running = computed(() => progress.value.status === "running" && ["running", "pending"].includes(latest.value?.status || ""));
const result = computed(() => running.value ? progress.value : latest.value?.result || {});
const metrics = computed(() => [
  { label: "检查媒体", value: count(result.value.scanned_media) },
  { label: "检查人物", value: count(result.value.scanned_people) },
  { label: "更新资料", value: count(result.value.updated_profiles) },
  { label: "更新图片", value: count(result.value.updated_images) },
  { label: "中文姓名", value: count(result.value.updated_names) },
  { label: "中文角色", value: count(result.value.updated_roles) },
  { label: "中文简介", value: count(result.value.updated_biographies) },
  { label: "缓存命中", value: count(result.value.cache_hits) },
]);
const outcomes = computed(() => [
  { label: "资料更新", value: count(result.value.updated_profiles), tone: "green" },
  { label: "图片更新", value: count(result.value.updated_images), tone: "blue" },
  { label: "处理失败", value: count(result.value.failures), tone: "red" },
]);
const outcomeTotal = computed(() => outcomes.value.reduce((total, item) => total + item.value, 0));
const state = computed(() => latest.value?.display_status || latest.value?.status || "empty");
const statePresentation = computed(() => ({
  completed: { label: "已完成", color: "success" },
  partial: { label: "部分完成", color: "warning" },
  failed: { label: "执行失败", color: "error" },
  running: { label: "正在处理", color: "primary" },
  pending: { label: "等待执行", color: "primary" },
  skipped: { label: "已跳过", color: undefined },
  empty: { label: "暂无记录", color: undefined },
}[state.value] || { label: "已结束", color: undefined }));

const summary = computed(() => {
  if (!latest.value) return "任务运行后将在这里显示处理结果";
  const data = result.value;
  const parts = [
    `检查 ${count(data.scanned_media)} 部媒体 · ${count(data.scanned_people)} 位人物`,
    `更新资料 ${count(data.updated_profiles)} 条、图片 ${count(data.updated_images)} 张`,
  ];
  if (count(data.removed_people)) parts.push(`移除人物 ${count(data.removed_people)}`);
  if (count(data.failures)) parts.push(`失败 ${count(data.failures)}`);
  parts.push(`来源无中文角色 ${count(data.no_chinese_role)}，人物未匹配 ${count(data.unmatched_people)}，请求失败 ${count(data.request_failures)}`);
  if (count(data.resumed_media)) parts.push(`断点跳过已处理作品 ${count(data.resumed_media)}`);
  if (count(data.skipped_people)) parts.push(`无变更人物条目 ${count(data.skipped_people)}`);
  return parts.join("，");
});

function localTime(value: unknown): string {
  if (!value) return "尚未执行";
  const text = String(value);
  const date = new Date(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text) ? `${text.replace(" ", "T")}Z` : text);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { hour12: false }) : text;
}

async function load(): Promise<void> {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const payload = await props.request<RunResponse>("/plugins/cast-profile-enricher/runs?limit=1");
    latest.value = payload.items?.[0] || null;
    progress.value = await props.request<Progress>("/plugins/cast-profile-enricher/api/progress");
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : "统计数据加载失败";
  } finally {
    loading.value = false;
  }
}

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => { void load(); poll = setInterval(() => void load(), 5000); });
function stopPolling(): void { clearInterval(poll); }
</script>

<template>
  <UiDialog :model-value="true" :max-width="900" width="calc(100vw - 32px)" @vue:unmounted="stopPolling" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="cast-stat-dialog">
      <header class="cast-stat-header">
        <h2>演职员资料完善 · 数据统计</h2>
        <UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>

      <main class="cast-stat-content">
        <p v-if="loading && !latest" class="cast-stat-message" role="status">正在读取处理结果…</p>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <template v-else>
          <dl class="cast-metrics" aria-label="处理指标">
            <div v-for="metric in metrics" :key="metric.label">
              <dt>{{ metric.label }}</dt>
              <dd>{{ metric.value }}</dd>
            </div>
          </dl>

          <section class="cast-latest" aria-label="本次处理">
            <div class="cast-latest-heading">
              <h3>本次处理</h3>
              <UiChip :color="statePresentation.color" size="small" variant="tonal">{{ statePresentation.label }}</UiChip>
              <time>{{ localTime(latest?.finished_at || latest?.started_at) }}</time>
            </div>
            <p>{{ summary }}</p>
            <p v-if="running" role="status">正在处理：{{ progress.current_media?.join('、') || '准备扫描' }} · 来源 {{ progress.source || '媒体服务器' }} · 已用时 {{ Math.floor(count(progress.elapsed_seconds) / 60) }} 分钟</p>
            <div class="cast-result-bar" aria-hidden="true">
              <span
                v-for="outcome in outcomes"
                :key="outcome.label"
                :class="`cast-tone--${outcome.tone}`"
                :style="{ flex: outcomeTotal ? outcome.value : (outcome.tone === 'green' ? 1 : 0) }"
              />
            </div>
            <ul class="cast-result-legend" aria-label="处理结果">
              <li v-for="outcome in outcomes" :key="outcome.label" :class="`cast-tone--${outcome.tone}`"><i />{{ outcome.label }} <strong>{{ outcome.value }}</strong></li>
            </ul>
          </section>
        </template>
      </main>

      <footer class="cast-stat-actions"><UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</UiButton></footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.cast-stat-dialog{display:flex;max-height:calc(100dvh - 32px);overflow:hidden;flex-direction:column;border:1px solid var(--app-border-subtle);border-radius:18px!important;background:var(--app-dialog-surface)!important;color:var(--app-text)}
.cast-stat-header{display:flex;box-sizing:border-box;height:var(--app-plugin-dialog-header-height,58px);min-height:var(--app-plugin-dialog-header-height,58px);max-height:var(--app-plugin-dialog-header-height,58px);flex:0 0 var(--app-plugin-dialog-header-height,58px);align-items:center;justify-content:space-between;gap:12px;padding:6px 24px;border-bottom:1px solid var(--app-border-subtle)}
.cast-stat-header h2{margin:0;font-size:18px;font-weight:750;line-height:1.2}
.cast-stat-content{display:grid;min-height:0;gap:18px;overflow:auto;padding:20px 24px;background:var(--app-surface-subtle)}
.cast-stat-message{min-height:220px;margin:0;display:grid;place-items:center;color:var(--app-text-muted)}
.cast-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 6px}.cast-metrics>div{min-width:0;padding:15px 16px;border:1px solid var(--app-border-subtle);border-radius:12px;background:var(--app-surface-muted)}.cast-metrics dt{color:var(--app-text-muted);font-size:12px}.cast-metrics dd{margin:10px 0 0;color:var(--app-text);font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}
.cast-tone--blue{--cast-tone:#2f74ee}.cast-tone--violet{--cast-tone:#7451d5}.cast-tone--green{--cast-tone:#29a866}.cast-tone--amber{--cast-tone:#e49312}.cast-tone--red{--cast-tone:#e4525d}
.cast-latest{padding:18px 20px;border:1px solid var(--app-border-subtle);border-radius:14px;background:var(--app-surface)}.cast-latest-heading{display:flex;align-items:center;gap:10px}.cast-latest-heading h3{margin:0;font-size:15px}.cast-latest-heading time{margin-left:auto;color:var(--app-text-muted);font-size:11px;font-variant-numeric:tabular-nums}.cast-latest>p{margin:15px 0;color:var(--app-text);font-size:12px;line-height:1.6}.cast-result-bar{display:flex;height:7px;overflow:hidden;border-radius:999px;background:var(--app-surface-muted)}.cast-result-bar span{min-width:0;background:var(--cast-tone)}.cast-result-legend{display:flex;flex-wrap:wrap;gap:10px 22px;padding:0;margin:14px 0 0;list-style:none}.cast-result-legend li{display:flex;align-items:center;gap:6px;color:var(--app-text-secondary);font-size:11px}.cast-result-legend i{width:7px;height:7px;border-radius:50%;background:var(--cast-tone)}.cast-result-legend strong{color:var(--app-text)}
.cast-stat-actions{display:flex;flex:0 0 auto;justify-content:flex-end;padding:10px 20px;border-top:1px solid var(--app-border-subtle);background:var(--app-surface-raised)}
@media(max-width:700px){.cast-stat-content{padding:16px}.cast-stat-header{padding:6px 16px}.cast-stat-header h2{font-size:16px}.cast-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.cast-latest-heading{align-items:flex-start;flex-wrap:wrap}.cast-latest-heading time{width:100%;margin-left:0}}
@media(max-width:420px){.cast-metrics{grid-template-columns:1fr}}
</style>
