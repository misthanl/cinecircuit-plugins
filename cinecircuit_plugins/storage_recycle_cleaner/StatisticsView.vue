<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface Run { status?: string; display_status?: string; }
const props = defineProps<{
  context: PluginContributionContext;
  request: CineCircuitPluginSdk["request"];
  buttonComponent: Component;
  cardComponent: Component;
  dialogComponent: Component;
  chipComponent: Component;
  alertComponent: Component;
}>();
const runs = ref<Run[]>([]);
const loading = ref(false);
const error = ref(false);
const metrics = computed(() => {
  const states = runs.value.map(run => run.display_status || run.status || "");
  const count = (values: string[]) => states.filter(state => values.includes(state)).length;
  return [
    { label: "清理次数", count: count(["completed", "failed", "partial", "running", "pending"]), tone: "neutral", icon: "mdi-trash-can-outline" },
    { label: "成功", count: count(["completed"]), tone: "success", icon: "mdi-check-circle-outline" },
    { label: "失败", count: count(["failed", "partial"]), tone: "error", icon: "mdi-close-circle-outline" },
    { label: "进行中", count: count(["running", "pending"]), tone: "primary", icon: "mdi-refresh" },
  ];
});
const scheduled = computed(() => {
  const installation = props.context.installation;
  const config = installation?.config;
  return Boolean(installation?.enabled && config && typeof config === "object" && "enabled" in config && config.enabled === true);
});
const nextRun = computed(() => {
  if (!scheduled.value) return "未启用";
  const value = props.context.installation?.next_run_at;
  if (!value) return "等待调度";
  const normalized = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(value) ? `${value.replace(" ", "T")}Z` : value;
  const date = new Date(normalized);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { hour12: false }) : "等待调度";
});
async function load() {
  if (loading.value) return;
  loading.value = true;
  error.value = false;
  try { runs.value = (await props.request<{ items?: Run[] }>("/plugins/storage-recycle-cleaner/runs?limit=100")).items || []; }
  catch { error.value = true; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <component :is="dialogComponent" :model-value="true" :max-width="780" width="calc(100vw - 32px)"
    @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <component :is="cardComponent" class="recycle-statistics">
      <header class="recycle-header">
        <h2>网盘回收站清理 · 数据统计</h2>
        <component class="app-dialog-close" :is="buttonComponent" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <main class="recycle-content">
        <p v-if="loading" class="recycle-message" role="status">正在读取插件统计…</p>
        <component v-else-if="error" :is="alertComponent" type="error" variant="tonal">统计加载失败，请点击刷新重试。</component>
        <section v-else class="recycle-overview" aria-label="回收站清理概览">
          <div class="recycle-heading"><h3>运行概览</h3><span>最近 100 次运行</span></div>
          <dl class="recycle-metrics">
            <div v-for="metric in metrics" :key="metric.label" class="recycle-metric" :class="`tone-${metric.tone}`">
              <dt><span>{{ metric.label }}</span><VIcon :icon="metric.icon" :size="18" /></dt>
              <dd>{{ metric.count }}<span>次</span></dd>
            </div>
          </dl>
          <div class="recycle-schedule">
            <span class="recycle-clock"><VIcon icon="mdi-clock-outline" :size="22" /></span>
            <div class="recycle-time"><span>下次执行</span><strong>{{ nextRun }}</strong></div>
            <component :is="chipComponent" :color="scheduled ? 'primary' : undefined" size="small" variant="tonal">
              {{ scheduled ? "定时清理已启用" : "定时清理未启用" }}
            </component>
          </div>
        </section>
      </main>
      <footer class="recycle-actions">
        <component :is="buttonComponent" prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</component>
      </footer>
    </component>
  </component>
</template>

<style scoped>
.recycle-statistics{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);border:1px solid var(--app-border);border-radius:18px!important;background:var(--app-dialog-surface)!important;color:var(--app-text);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}
.recycle-header{display:flex;box-sizing:border-box;flex:0 0 var(--app-plugin-dialog-header-height,58px);height:var(--app-plugin-dialog-header-height,58px);align-items:center;justify-content:space-between;gap:12px;padding:6px 24px;border-bottom:1px solid var(--app-border-subtle)}
.recycle-header h2{margin:0;font-size:var(--app-font-size-section-title,18px);font-weight:700;line-height:1.2}
.recycle-content{min-height:0;overflow:auto;padding:20px}.recycle-actions{display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--app-border-subtle)}
.recycle-message{padding:32px 0;text-align:center;color:var(--app-text-muted)}
.recycle-overview{display:grid;gap:20px;min-width:0}.recycle-heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.recycle-heading h3{margin:0;font-size:var(--app-font-size-body,14px);font-weight:650}.recycle-heading>span{font-size:var(--app-font-size-helper,12px);color:var(--app-text-muted)}
.recycle-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0}.recycle-metric{padding:16px;border:1px solid color-mix(in srgb,var(--tone) 18%,transparent);border-radius:12px;background:color-mix(in srgb,var(--tone) 5%,transparent)}
.tone-neutral{--tone:var(--app-text-secondary)}.tone-success{--tone:rgb(var(--v-theme-success))}.tone-error{--tone:rgb(var(--v-theme-error))}.tone-primary{--tone:rgb(var(--v-theme-primary))}
.recycle-metric dt{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:var(--app-font-size-label,13px);color:var(--app-text-secondary)}.recycle-metric dt .v-icon{color:var(--tone)}
.recycle-metric dd{display:flex;align-items:baseline;gap:6px;margin:12px 0 0;color:var(--tone);font-size:calc(var(--app-font-size-body,14px) * 2);font-weight:700;line-height:1.15;font-variant-numeric:tabular-nums}.recycle-metric dd span{font-size:var(--app-font-size-helper,12px);font-weight:400;color:var(--app-text-muted)}
.recycle-schedule{display:flex;align-items:center;gap:12px;padding-top:20px;border-top:1px solid var(--app-border-subtle)}.recycle-clock{display:grid;place-items:center;width:42px;height:42px;flex:0 0 auto;border-radius:12px;color:rgb(var(--v-theme-primary));background:rgba(var(--v-theme-primary),.08)}.recycle-time{display:grid;flex:1;gap:5px;min-width:0}.recycle-time>span{font-size:var(--app-font-size-helper,12px);color:var(--app-text-muted)}.recycle-time strong{font-size:var(--app-font-size-body,14px);font-weight:600;overflow-wrap:anywhere}
@media(max-width:760px){.recycle-header{padding:6px 16px}.recycle-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.recycle-schedule{flex-wrap:wrap}}
</style>
