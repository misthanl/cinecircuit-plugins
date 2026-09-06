<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface SiteItem { id: string; name: string }
interface HistoryItem {
  status?: string;
  updated_at?: string;
  payload?: { site_id?: string; site_name?: string; mode?: "sign" | "login" };
  result?: { ok?: boolean; message?: string; status?: string; site_name?: string };
}
interface InventoryResponse {
  items?: SiteItem[];
  selected?: { sign_sites?: string[]; login_sites?: string[] };
  history?: HistoryItem[];
}

const props = defineProps<{
  context: PluginContributionContext;
  request: CineCircuitPluginSdk["request"];
  buttonComponent: Component;
  cardComponent: Component;
  dialogComponent: Component;
  alertComponent: Component;
}>();
const UiButton = props.buttonComponent;
const UiCard = props.cardComponent;
const UiDialog = props.dialogComponent;
const UiAlert = props.alertComponent;
const loading = ref(false);
const error = ref("");
const inventory = ref<InventoryResponse>({});
const history = computed(() => inventory.value.history || []);
const loginCount = computed(() => inventory.value.selected?.login_sites?.length || 0);
const signCount = computed(() => inventory.value.selected?.sign_sites?.length || 0);
const successful = computed(() => history.value.filter((item) => item.result?.ok || item.status === "signed").length);
const failed = computed(() => history.value.filter((item) => item.result?.ok === false || item.status === "failed").length);

function siteName(item: HistoryItem) {
  const id = String(item.payload?.site_id || "");
  return item.payload?.site_name || item.result?.site_name || inventory.value.items?.find((site) => site.id === id)?.name || id || "未知站点";
}
function modeName(item: HistoryItem) { return item.payload?.mode === "login" ? "保持登录" : "签到"; }
function resultText(item: HistoryItem) {
  if (item.result?.message) return item.result.message;
  if (item.result?.ok || item.status === "signed") return item.payload?.mode === "login" ? "登录状态正常" : "签到完成";
  return item.result?.status || "执行失败";
}
function localTime(value?: string) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { hour12: false }) : value;
}
async function load() {
  loading.value = true; error.value = "";
  try { inventory.value = await props.request<InventoryResponse>("/plugins/auto-signin/api/inventory"); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "签到统计加载失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiDialog :model-value="true" :max-width="1080" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="signin-stat-dialog">
      <header class="signin-stat-dialog__header">
        <div><h2>站点签到与登录统计</h2><p>签到和保持登录分别统计，同一站点的两类结果不会合并。</p></div>
        <UiButton icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <main class="signin-stat-dialog__content">
        <p v-if="loading" class="signin-stat-empty">正在读取统计…</p>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <template v-else>
          <dl class="signin-stat-metrics">
            <div><dt>保持登录站点</dt><dd>{{ loginCount }}</dd></div>
            <div><dt>签到站点</dt><dd>{{ signCount }}</dd></div>
            <div><dt>最近成功</dt><dd>{{ successful }}</dd></div>
            <div><dt>最近失败</dt><dd>{{ failed }}</dd></div>
          </dl>
          <section v-if="history.length" class="signin-stat-results" aria-label="最近站点结果">
            <header><strong>最近站点结果</strong><span>最多显示 100 条</span></header>
            <article v-for="(item, index) in history" :key="`${item.payload?.site_id}-${item.payload?.mode}-${index}`">
              <div><strong>{{ siteName(item) }}</strong><span>{{ modeName(item) }}</span></div>
              <p :class="{ bad: item.result?.ok === false || item.status === 'failed' }">{{ resultText(item) }}</p>
              <time>{{ localTime(item.updated_at) }}</time>
            </article>
          </section>
          <p v-else class="signin-stat-empty">还没有执行记录。任务运行后，这里会按站点名称显示签到和登录结果。</p>
        </template>
      </main>
      <footer class="signin-stat-dialog__actions">
        <UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</UiButton>
        <UiButton prepend-icon="mdi-cog-outline" variant="flat" color="primary" @click="context.configure">调整设置</UiButton>
      </footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.signin-stat-dialog{display:flex;max-height:calc(100dvh - 32px);flex-direction:column;border-radius:18px!important;color:var(--app-text)}
.signin-stat-dialog__header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 24px;border-bottom:1px solid var(--app-border-subtle)}
.signin-stat-dialog__header h2{margin:0;font-size:21px}.signin-stat-dialog__header p{margin:4px 0 0;color:var(--app-text-muted);font-size:12px}
.signin-stat-dialog__content{display:grid;min-height:0;gap:18px;overflow:auto;padding:22px 24px;background:var(--app-surface-subtle)}
.signin-stat-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0}.signin-stat-metrics>div{padding:16px 18px;border:1px solid var(--app-border-subtle);border-radius:14px;background:var(--app-surface)}.signin-stat-metrics dt{color:var(--app-text-muted);font-size:12px}.signin-stat-metrics dd{margin:7px 0 0;font-size:28px;font-weight:720}
.signin-stat-results{overflow:hidden;border:1px solid var(--app-border-subtle);border-radius:14px;background:var(--app-surface)}.signin-stat-results>header,.signin-stat-results article{display:grid;grid-template-columns:minmax(180px,1fr) minmax(220px,2fr) auto;align-items:center;gap:16px;padding:13px 16px;border-bottom:1px solid var(--app-border-subtle)}.signin-stat-results>header{display:flex;justify-content:space-between;background:var(--app-surface-muted)}.signin-stat-results>header span,.signin-stat-results article span,.signin-stat-results time{color:var(--app-text-muted);font-size:11px}.signin-stat-results article:last-child{border-bottom:0}.signin-stat-results article div{display:grid;gap:3px}.signin-stat-results article p{margin:0;color:#16865b;font-size:12px;overflow-wrap:anywhere}.signin-stat-results article p.bad{color:#d04444}.signin-stat-results time{white-space:nowrap}
.signin-stat-empty{padding:40px 16px;text-align:center;color:var(--app-text-muted)}.signin-stat-dialog__actions{display:flex;justify-content:flex-end;gap:10px;padding:12px 24px;border-top:1px solid var(--app-border-subtle)}
@media(max-width:700px){.signin-stat-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.signin-stat-results article{grid-template-columns:1fr}.signin-stat-dialog__header,.signin-stat-dialog__content{padding:16px}}
</style>
