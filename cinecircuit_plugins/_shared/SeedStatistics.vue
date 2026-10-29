<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import type { PluginContributionContext } from "@cinecircuit/plugin-sdk";
const props = defineProps<{
  context: PluginContributionContext;
  dialogComponent: Component;
  pluginId: string;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  cardComponent: Component; buttonComponent: Component; alertComponent: Component;
}>();
type Entry = { id: string; name: string; hash: string; status: string; error: string; timestamp: number };
type Report = { counts: Record<string, number>; items: Entry[] };
const UiCard = props.cardComponent, UiButton = props.buttonComponent, UiAlert = props.alertComponent;
const UiDialog = props.dialogComponent;
const title = computed(() => `${props.context.installation?.name || "插件"} · 数据统计`);
const report = ref<Report>({ counts: {}, items: [] }), loading = ref(false), error = ref("");
const names: Record<string, string> = { submitted: "已提交", checking: "校验中", ready: "待确认", seeding: "做种中", paused: "已暂停", failed: "失败", attention: "需检查", duplicate: "已存在", missing: "任务已变化" };
const items = computed(() => report.value.items.map(item => ({ ...item, statusLabel: names[item.status] || item.status,
  date: item.timestamp ? new Date(item.timestamp * 1000).toLocaleString("zh-CN") : "—" })));
const page = ref(1);
const pageSize = 10;
const pages = computed(() => Math.max(1, Math.ceil(items.value.length / pageSize)));
function changePage(value: number) { page.value = Math.min(pages.value, Math.max(1, Math.trunc(Number(value) || 1))); }
function inputPage(event: Event) {
  const input = event.target as HTMLInputElement;
  changePage(Number(input.value));
  input.value = String(page.value);
}
function inputPageKey(event: KeyboardEvent) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  inputPage(event);
}
const headers = [{ title: "任务", key: "name" }, { title: "状态", key: "statusLabel" }, { title: "时间", key: "date" }, { title: "说明", key: "error" }];
const totals = computed(() => [
  { label: "做种中", count: report.value.counts.seeding || 0 },
  { label: "待校验", count: (report.value.counts.checking || 0) + (report.value.counts.submitted || 0) },
  { label: "已暂停", count: report.value.counts.paused || 0 },
  { label: "需处理", count: (report.value.counts.failed || 0) + (report.value.counts.attention || 0) },
]);
async function load(): Promise<void> {
  if (loading.value) return;
  loading.value = true; error.value = "";
  try { report.value = await props.request<Report>(`/plugins/${props.pluginId}/api/statistics`); changePage(page.value); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "读取统计失败"; }
  finally { loading.value = false; }
}
async function check(): Promise<void> {
  if (loading.value) return;
  loading.value = true; error.value = "";
  try { await props.request(`/plugins/${props.pluginId}/api/check`, { method: "POST", body: "{}" }); report.value = await props.request<Report>(`/plugins/${props.pluginId}/api/statistics`); changePage(page.value); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "检查失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiDialog :model-value="true" :max-width="980" width="calc(100vw - 32px)" scrollable @update:model-value="!$event && context.close()">
    <UiCard class="seed-statistics-dialog">
      <header class="seed-statistics-header">
        <h2>{{ title }}</h2>
        <UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close()" />
      </header>
      <section class="seed-statistics-content" :aria-busy="loading">
        <UiAlert v-if="error" type="error" variant="tonal" role="alert">{{ error }}</UiAlert>
        <dl class="seed-statistics-metrics" aria-label="任务统计">
          <div v-for="total in totals" :key="total.label"><dt>{{ total.label }}</dt><dd>{{ total.count }}</dd></div>
        </dl>
        <div class="seed-statistics-table">
          <VDataTable :headers="headers" :items="items" :loading="loading" :page="page" :items-per-page="pageSize" hide-default-footer @update:page="changePage" item-value="id" density="compact" no-data-text="暂无任务记录" />
        </div>
        <nav class="seed-statistics-pagination" aria-label="任务记录分页">
          <span>最近 {{ items.length }} 条记录</span>
          <div>
            <button type="button" aria-label="第一页" :disabled="loading || page <= 1" @click="changePage(1)"><VIcon icon="mdi-page-first" /></button>
            <button type="button" aria-label="上一页" :disabled="loading || page <= 1" @click="changePage(page - 1)"><VIcon icon="mdi-chevron-left" /></button>
            <input :value="page" aria-label="页码" type="number" inputmode="numeric" min="1" :max="pages" :disabled="loading" @change="inputPage" @keydown="inputPageKey">
            <span>/ {{ pages }}</span>
            <button type="button" aria-label="下一页" :disabled="loading || page >= pages" @click="changePage(page + 1)"><VIcon icon="mdi-chevron-right" /></button>
            <button type="button" aria-label="最后一页" :disabled="loading || page >= pages" @click="changePage(pages)"><VIcon icon="mdi-page-last" /></button>
          </div>
        </nav>
      </section>
      <footer class="seed-statistics-actions">
        <UiButton variant="text" :disabled="loading" @click="check">检查校验</UiButton>
        <UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" :disabled="loading" @click="load">刷新</UiButton>
      </footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.seed-statistics-dialog{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);overflow:hidden;border:1px solid var(--app-border);border-radius:var(--app-dialog-radius, 16px)!important;background:var(--app-dialog-surface,var(--app-surface,#fff))!important;color:var(--app-text);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}
.seed-statistics-header{display:flex;box-sizing:border-box;flex:0 0 var(--app-plugin-dialog-header-height,58px);min-height:var(--app-plugin-dialog-header-height,58px);align-items:center;justify-content:space-between;gap:12px;padding:6px 24px;border-bottom:1px solid var(--app-border-subtle)}
.seed-statistics-header h2{margin:0;font-size:var(--app-font-size-section-title,18px);font-weight:var(--app-font-weight-heading, 600);line-height:1.2;overflow-wrap:anywhere}
.seed-statistics-content{display:grid;gap:18px;min-height:0;min-width:0;overflow:auto;padding:20px}
.seed-statistics-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0}
.seed-statistics-metrics>div{min-width:0;padding:15px 16px;border:1px solid var(--app-border-subtle);border-radius:12px;background:var(--app-surface-muted)}
.seed-statistics-metrics dt{color:var(--app-text-muted);font-size:12px}
.seed-statistics-metrics dd{margin:7px 0 0;color:var(--app-text);font-family:inherit;font-size:var(--app-font-size-metric,24px);font-weight:var(--app-font-weight-metric, 600);font-variant-numeric:tabular-nums;line-height:1.15;overflow-wrap:anywhere}
.seed-statistics-table{min-width:0;overflow:auto;border:1px solid var(--app-border-subtle);border-radius:var(--app-radius-panel, 12px)}
.seed-statistics-actions{display:flex;flex:0 0 auto;align-items:center;justify-content:flex-end;gap:8px;padding:10px 18px;border-top:1px solid var(--app-border-subtle);background:var(--app-surface,#fff)}
.seed-statistics-pagination{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;min-width:0;font-size:12px;color:var(--app-text-muted)}
.seed-statistics-pagination>div{display:flex;align-items:center;gap:6px;max-width:100%}
.seed-statistics-pagination button{display:grid;place-items:center;flex:0 0 32px;width:32px;height:32px;padding:0;border:0;border-radius:8px;background:none;color:inherit;cursor:pointer}
.seed-statistics-pagination .v-icon{font-size:18px}
.seed-statistics-pagination input{box-sizing:border-box;min-width:0;width:48px;height:32px;text-align:center;border:1px solid var(--app-border-subtle);border-radius:8px;padding:5px;background:var(--app-surface);color:inherit;font:inherit;appearance:textfield;-moz-appearance:textfield}
.seed-statistics-pagination input::-webkit-inner-spin-button,.seed-statistics-pagination input::-webkit-outer-spin-button{appearance:none;margin:0}
.seed-statistics-pagination button:disabled,.seed-statistics-pagination input:disabled{opacity:.35;cursor:default}
.seed-statistics-pagination button:focus-visible,.seed-statistics-pagination input:focus-visible{outline:2px solid rgb(var(--v-theme-primary));outline-offset:2px}
@media(max-width:700px){.seed-statistics-pagination>div{gap:4px}}
@media(max-width:700px){.seed-statistics-header{padding:6px 16px}.seed-statistics-content{padding:16px}.seed-statistics-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
