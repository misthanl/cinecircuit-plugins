<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface RunRecord { display_status?: string; status?: string; }
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
const runs = ref<RunRecord[]>([]);
const loading = ref(false);
const error = ref("");

const groups = computed(() => {
  const definitions = [
    { label: "成功", tone: "success", icon: "mdi-check-circle-outline", states: ["completed"] },
    { label: "异常", tone: "error", icon: "mdi-alert-circle-outline", states: ["failed", "partial"] },
    { label: "进行中", tone: "primary", icon: "mdi-refresh", states: ["running", "pending"] },
    { label: "已跳过", tone: "muted", icon: "", states: ["skipped"] },
    { label: "其他", tone: "muted", icon: "", states: [] },
  ];
  const known = definitions.flatMap(group => group.states);
  return definitions.map(group => ({ ...group, count: runs.value.filter(run => {
    const state = run.display_status || run.status || "";
    return group.states.includes(state) || (group.label === "其他" && !known.includes(state));
  }).length }));
});
const visibleGroups = computed(() => groups.value.filter(group => group.count > 0));
const metrics = computed(() => [
  { label: "运行次数", tone: "neutral", icon: "mdi-cloud-sync-outline", count: runs.value.length },
  ...groups.value.slice(0, 3),
]);

function localTime(value: unknown, fallback: string): string {
  if (!value) return fallback;
  const text = String(value);
  const date = new Date(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text) ? `${text.replace(" ", "T")}Z` : text);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { hour12: false }) : fallback;
}
async function load() {
  if (loading.value) return;
  loading.value = true; error.value = "";
  try { runs.value = (await props.request<RunResponse>("/plugins/cookiecloud/runs?limit=100")).items || []; }
  catch (reason: unknown) { error.value = reason && typeof reason === "object" && "message" in reason ? String(reason.message || "插件统计加载失败") : "插件统计加载失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiDialog :model-value="true" :max-width="780" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="cc-statistics-dialog">
      <header class="cc-statistics-header">
        <span class="cc-statistics-logo"><VIcon icon="mdi-cloud-sync-outline" :size="22" /></span>
        <div><h2>CookieCloud 站点同步 · 数据统计</h2><p>浏览器 Cookie 同步与站点更新概览</p></div>
        <UiButton icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <div class="cc-statistics-content">
        <p v-if="loading" class="cc-statistics-message" role="status">正在读取插件统计…</p>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <section v-else class="cookie-overview" aria-label="CookieCloud 同步概览">
          <div class="cookie-overview__heading"><h3>运行概览</h3><span>最近 100 次运行</span></div>
          <dl class="cookie-metrics">
            <div v-for="metric in metrics" :key="metric.label" class="cookie-metric" :class="`cookie-tone--${metric.tone}`">
              <dt><span>{{ metric.label }}</span><VIcon v-if="metric.icon" :icon="metric.icon" :size="18" /></dt>
              <dd>{{ metric.count }}<span>次</span></dd>
            </div>
          </dl>
          <div class="cookie-results">
            <template v-if="runs.length">
              <div class="cookie-results__bar" aria-hidden="true"><span v-for="group in visibleGroups" :key="group.label" :class="`cookie-tone--${group.tone}`" :style="{ flex: group.count }" /></div>
              <ul class="cookie-results__legend" aria-label="运行结果分布"><li v-for="group in visibleGroups" :key="group.label" :class="`cookie-tone--${group.tone}`"><i aria-hidden="true" />{{ group.label }}<strong>{{ group.count }}</strong></li></ul>
              <p>异常包含失败和部分成功</p>
            </template>
            <p v-else class="cookie-results__empty">暂无运行数据，首次同步后将在这里显示统计。</p>
          </div>
          <div class="cookie-schedule">
            <span class="cookie-schedule__icon"><VIcon icon="mdi-clock-outline" :size="22" /></span>
            <div class="cookie-schedule__time"><span>下次执行</span><strong>{{ context.installation?.enabled ? localTime(context.installation.next_run_at, "等待调度") : "已停用" }}</strong></div>
            <UiChip :color="context.installation?.enabled ? 'primary' : undefined" size="small" variant="tonal">{{ context.installation?.enabled ? "调度已启用" : "调度已停用" }}</UiChip>
          </div>
        </section>
      </div>
      <footer class="cc-statistics-actions"><UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</UiButton></footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.cc-statistics-dialog{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);border:1px solid var(--app-border);border-radius:18px!important;background:var(--app-dialog-surface)!important;color:var(--app-text)}
.cc-statistics-header{display:flex;align-items:center;gap:12px;padding:20px;border-bottom:1px solid var(--app-border-subtle)}
.cc-statistics-header>div{flex:1;min-width:0}.cc-statistics-header h2{font-size:19px;margin:0;line-height:1.5}.cc-statistics-header p{font-size:12px;color:var(--app-text-muted);margin:2px 0 0}
.cc-statistics-logo{display:grid;place-items:center;width:44px;height:44px;flex-shrink:0;border-radius:13px;background:var(--app-info-soft);color:rgb(var(--v-theme-primary))}
.cc-statistics-content{min-height:0;overflow:auto;padding:20px}.cc-statistics-actions{display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--app-border-subtle)}.cc-statistics-message{padding:40px 12px;text-align:center;color:var(--app-text-muted)}
.cookie-overview{display:grid;gap:18px;min-width:0;color:var(--app-text)}.cookie-tone--neutral{--cookie-tone:var(--app-text-secondary)}.cookie-tone--primary{--cookie-tone:rgb(var(--v-theme-primary))}.cookie-tone--success{--cookie-tone:rgb(var(--v-theme-success))}.cookie-tone--error{--cookie-tone:rgb(var(--v-theme-error))}.cookie-tone--muted{--cookie-tone:var(--app-text-muted)}
.cookie-overview__heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:6px}.cookie-overview__heading h3{margin:0;font-size:15px;font-weight:650}.cookie-overview__heading>span{color:var(--app-text-muted);font-size:12px}
.cookie-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0}.cookie-metric{padding:15px 16px 13px;border:1px solid color-mix(in srgb,var(--cookie-tone) 15%,transparent);border-radius:12px;background:color-mix(in srgb,var(--cookie-tone) 5%,transparent)}.cookie-metric dt{display:flex;align-items:center;justify-content:space-between;gap:8px;color:var(--app-text-secondary);font-size:12px}.cookie-metric dt .v-icon{color:var(--cookie-tone)}.cookie-metric dd{display:flex;align-items:baseline;gap:6px;margin:12px 0 0;color:var(--cookie-tone);font-family:"Bahnschrift","Aptos",sans-serif;font-size:32px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.1}.cookie-metric dd>span{color:var(--app-text-muted);font-size:11px;font-weight:400}
.cookie-results{display:grid;gap:12px}.cookie-results__bar{display:flex;gap:4px;height:6px;overflow:hidden;border-radius:4px}.cookie-results__bar>span{min-width:2px;background:var(--cookie-tone)}.cookie-results__legend{display:flex;flex-wrap:wrap;gap:10px 20px;padding:0;margin:0;list-style:none}.cookie-results__legend li{display:flex;align-items:center;gap:7px;color:var(--app-text-secondary);font-size:12px}.cookie-results__legend i{width:6px;height:6px;border-radius:50%;background:var(--cookie-tone)}.cookie-results__legend strong{color:var(--app-text);font-variant-numeric:tabular-nums}.cookie-results p{margin:0;color:var(--app-text-muted);font-size:11px}.cookie-results .cookie-results__empty{padding:8px 0;font-size:13px}
.cookie-schedule{display:flex;align-items:center;gap:12px;padding:18px 0 2px;border-top:1px solid var(--app-border-subtle)}.cookie-schedule__icon{display:grid;place-items:center;width:42px;height:42px;flex:0 0 auto;border-radius:12px;color:rgb(var(--v-theme-primary));background:rgba(var(--v-theme-primary),.08)}.cookie-schedule__time{display:grid;flex:1;gap:5px;min-width:0}.cookie-schedule__time>span{color:var(--app-text-muted);font-size:12px}.cookie-schedule__time strong{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
@media(max-width:600px){.cc-statistics-header h2{font-size:16px}.cookie-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.cookie-schedule{flex-wrap:wrap}}
</style>
