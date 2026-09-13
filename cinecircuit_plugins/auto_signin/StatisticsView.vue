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
type ResultState = "success" | "failed" | "empty";

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

const history = computed(() => Array.isArray(inventory.value.history) ? inventory.value.history : []);
const signSiteIds = computed(() => inventory.value.selected?.sign_sites || []);
const loginSiteIds = computed(() => inventory.value.selected?.login_sites || []);
const todayKey = computed(() => dateKey(new Date()));
const days = computed(() => Array.from({ length: 7 }, (_, index) => {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() - index);
  return { key: dateKey(date), short: `${date.getMonth() + 1}/${date.getDate()}`, weekday: index === 0 ? "今天" : weekday(date) };
}));
const siteRows = computed(() => {
  const ids = new Set(signSiteIds.value);
  history.value.forEach((item) => {
    if ((item.payload?.mode || "sign") === "sign" && item.payload?.site_id) ids.add(String(item.payload.site_id));
  });
  return [...ids].map((id) => ({ id, name: findSiteName(id), records: history.value.filter((item) => String(item.payload?.site_id || "") === id && (item.payload?.mode || "sign") === "sign").length }))
    .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));
});
const todaySigns = computed(() => recordsFor("sign", todayKey.value));
const todayLogins = computed(() => recordsFor("login", todayKey.value));
const signSuccess = computed(() => todaySigns.value.filter(isSuccess).length);
const signFailed = computed(() => todaySigns.value.filter((item) => !isSuccess(item)).length);
const loginSuccess = computed(() => todayLogins.value.filter(isSuccess).length);
const signUnrecorded = computed(() => Math.max(0, signSiteIds.value.length - new Set(todaySigns.value.map(siteId)).size));
const loginUnrecorded = computed(() => Math.max(0, loginSiteIds.value.length - new Set(todayLogins.value.map(siteId)).size));

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
function historyDate(item: HistoryItem) {
  if (!item.updated_at) return "";
  const parsed = new Date(item.updated_at);
  return Number.isFinite(parsed.getTime()) ? dateKey(parsed) : String(item.updated_at).slice(0, 10);
}
function weekday(date: Date) { return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()]; }
function siteId(item: HistoryItem) { return String(item.payload?.site_id || ""); }
function isSuccess(item: HistoryItem) { return item.result?.ok === true || item.status === "signed"; }
function recordsFor(mode: "sign" | "login", day: string) {
  return history.value.filter((item) => (item.payload?.mode || "sign") === mode && historyDate(item) === day);
}
function findSiteName(id: string) {
  const saved = history.value.find((item) => siteId(item) === id);
  const recordedName = saved?.payload?.site_name || saved?.result?.site_name;
  return recordedName || inventorySiteName(id);
}
function inventorySiteName(id: string) {
  return inventory.value.items?.find((site) => String(site.id) === id)?.name || id || "未知站点";
}
function recordFor(site: string, day: string) {
  return history.value.find((item) => siteId(item) === site && (item.payload?.mode || "sign") === "sign" && historyDate(item) === day);
}
function stateFor(site: string, day: string): ResultState {
  const item = recordFor(site, day);
  if (!item) return "empty";
  return isSuccess(item) ? "success" : "failed";
}
function stateLabel(state: ResultState) { return state === "success" ? "签到成功" : state === "failed" ? "签到失败，需要重试" : "暂无记录"; }
async function load() {
  loading.value = true;
  error.value = "";
  try { inventory.value = await props.request<InventoryResponse>("/plugins/auto-signin/api/inventory"); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "签到统计加载失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiDialog :model-value="true" :max-width="972" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="signin-stat-dialog">
      <header class="signin-stat-dialog__header">
        <h2>站点签到助手 · 数据统计</h2>
        <UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>

      <main class="signin-stat-dialog__content">
        <div v-if="loading && !history.length" class="signin-stat-empty"><span class="signin-stat-loader"></span>正在读取签到记录…</div>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <template v-else>
          <section class="signin-stat-metrics" aria-label="今日签到概览">
            <article class="metric metric--amber">
              <span class="metric__icon">✓</span>
              <div><span class="metric__label">今日签到</span><strong>{{ signSuccess }}<small>/{{ signSiteIds.length }}</small></strong><p>异常 {{ signFailed }} · 未记录 {{ signUnrecorded }}</p></div>
            </article>
            <article class="metric metric--red">
              <span class="metric__icon">!</span>
              <div><span class="metric__label">待处理异常</span><strong>{{ signFailed }}</strong><p>{{ signFailed ? "需要检查失败原因" : "今日暂无签到异常" }}</p></div>
            </article>
            <article class="metric metric--blue">
              <span class="metric__icon">↪</span>
              <div><span class="metric__label">今日登录</span><strong>{{ loginSuccess }}<small>/{{ loginSiteIds.length }}</small></strong><p>未记录 {{ loginUnrecorded }}</p></div>
            </article>
            <article class="metric metric--violet">
              <span class="metric__icon">↺</span>
              <div><span class="metric__label">历史范围</span><strong>7<small> 天</small></strong><p>按站点展示每日结果</p></div>
            </article>
          </section>

          <section class="signin-stat-board" aria-labelledby="signin-matrix-title">
            <header class="signin-stat-board__header">
              <div><h3 id="signin-matrix-title"><span aria-hidden="true">▣</span> 签到状态</h3><p>每一格代表该站点当天最后一次签到结果</p></div>
              <div class="signin-stat-legend" aria-label="状态图例"><span><i class="dot dot--success"></i>成功</span><span><i class="dot dot--failed"></i>异常</span><span><i class="dot dot--empty"></i>未记录</span><b>{{ siteRows.length }} 个站点</b></div>
            </header>

            <div v-if="siteRows.length" class="signin-stat-table-wrap">
              <table class="signin-stat-table">
                <thead><tr><th scope="col">站点</th><th scope="col">今日状态</th><th v-for="day in days" :key="day.key" scope="col"><span>{{ day.short }}</span><small>{{ day.weekday }}</small></th></tr></thead>
                <tbody>
                  <tr v-for="site in siteRows" :key="site.id">
                    <th scope="row"><strong>{{ site.name }}</strong><small>{{ site.records }} 条签到记录</small></th>
                    <td><span :class="['today-pill', `today-pill--${stateFor(site.id, todayKey)}`]"><i></i>{{ stateLabel(stateFor(site.id, todayKey)) }}</span></td>
                    <td v-for="day in days" :key="day.key">
                      <span :class="['status-cell', `status-cell--${stateFor(site.id, day.key)}`]" :title="`${site.name} · ${day.short} · ${stateLabel(stateFor(site.id, day.key))}`" :aria-label="stateLabel(stateFor(site.id, day.key))">{{ stateFor(site.id, day.key) === "success" ? "✓" : stateFor(site.id, day.key) === "failed" ? "!" : "−" }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="signin-stat-empty">还没有签到站点。先在插件设置中选择站点，任务运行后即可查看每日结果。</div>
          </section>
        </template>
      </main>

      <footer class="signin-stat-dialog__actions"><UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load">刷新</UiButton></footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.signin-stat-dialog{--stat-amber:#f5a524;--stat-red:#e45c72;--stat-blue:#2f93f1;--stat-violet:#7c64df;--stat-green:#39a96b;display:flex;max-height:calc(100dvh - 32px);flex-direction:column;overflow:hidden;border:1px solid var(--app-border-subtle);border-radius:20px!important;background:var(--app-surface);color:var(--app-text);box-shadow:0 28px 80px rgba(18,26,45,.22)}
.signin-stat-dialog__header{display:flex;box-sizing:border-box;height:var(--app-plugin-dialog-header-height,58px);min-height:var(--app-plugin-dialog-header-height,58px);max-height:var(--app-plugin-dialog-header-height,58px);flex:0 0 var(--app-plugin-dialog-header-height,58px);align-items:center;justify-content:space-between;gap:18px;padding:6px 24px;border-bottom:1px solid var(--app-border-subtle)}
.signin-stat-dialog__header h2{margin:0;font-size:18px;font-weight:750;line-height:1.2}
.signin-stat-dialog__content{display:grid;min-height:0;gap:20px;overflow:auto;padding:22px 24px;background:var(--app-surface-subtle)}
.signin-stat-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{position:relative;display:flex;min-width:0;align-items:flex-start;gap:12px;padding:16px 17px;overflow:hidden;border:1px solid var(--app-border-subtle);border-radius:14px;background:var(--app-surface)}.metric::before{position:absolute;inset:0 auto 0 0;width:3px;background:var(--metric-color);content:""}.metric__icon{display:grid;width:29px;height:29px;flex:0 0 auto;place-items:center;border-radius:9px;background:color-mix(in srgb,var(--metric-color) 14%,transparent);color:var(--metric-color);font-weight:850}.metric>div{min-width:0}.metric__label{display:block;color:var(--app-text-muted);font-size:12px;font-weight:700}.metric strong{display:block;margin-top:5px;color:var(--metric-color);font-size:27px;font-variant-numeric:tabular-nums;line-height:1}.metric strong small{font-size:16px;font-weight:720}.metric p{margin:7px 0 0;overflow:hidden;color:var(--app-text-muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.metric--amber{--metric-color:var(--stat-amber)}.metric--red{--metric-color:var(--stat-red)}.metric--blue{--metric-color:var(--stat-blue)}.metric--violet{--metric-color:var(--stat-violet)}
.signin-stat-board{overflow:hidden;border:1px solid var(--app-border-subtle);border-radius:16px;background:var(--app-surface)}.signin-stat-board__header{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:15px 16px;border-bottom:1px solid var(--app-border-subtle)}.signin-stat-board__header h3{margin:0;font-size:15px}.signin-stat-board__header h3 span{color:var(--stat-violet)}.signin-stat-board__header p{margin:4px 0 0;color:var(--app-text-muted);font-size:11px}.signin-stat-legend{display:flex;align-items:center;gap:13px;color:var(--app-text-muted);font-size:11px;white-space:nowrap}.signin-stat-legend span{display:flex;align-items:center;gap:5px}.signin-stat-legend b{padding:5px 9px;border-radius:999px;background:color-mix(in srgb,var(--stat-violet) 12%,transparent);color:var(--stat-violet);font-weight:750}.dot{width:7px;height:7px;border-radius:50%}.dot--success{background:var(--stat-green)}.dot--failed{background:var(--stat-red)}.dot--empty{border:1px solid var(--app-text-muted)}
.signin-stat-table-wrap{overflow:auto}.signin-stat-table{width:100%;min-width:890px;border-collapse:collapse;table-layout:fixed}.signin-stat-table th,.signin-stat-table td{height:54px;padding:8px 10px;border-bottom:1px solid var(--app-border-subtle);text-align:center}.signin-stat-table thead th{height:48px;background:var(--app-surface-muted);color:var(--app-text-muted);font-size:11px;font-weight:750}.signin-stat-table thead th:first-child,.signin-stat-table tbody th{width:190px;text-align:left}.signin-stat-table thead th:nth-child(2){width:175px;text-align:left}.signin-stat-table thead th span,.signin-stat-table thead th small{display:block}.signin-stat-table thead th span{color:var(--app-text);font-size:12px}.signin-stat-table thead th small{margin-top:2px;font-weight:500}.signin-stat-table tbody tr:last-child th,.signin-stat-table tbody tr:last-child td{border-bottom:0}.signin-stat-table tbody tr:hover{background:color-mix(in srgb,var(--stat-violet) 4%,transparent)}.signin-stat-table tbody th{position:sticky;left:0;z-index:1;background:var(--app-surface)}.signin-stat-table tbody th strong,.signin-stat-table tbody th small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.signin-stat-table tbody th strong{font-size:13px}.signin-stat-table tbody th small{margin-top:3px;color:var(--app-text-muted);font-size:10px;font-weight:500}.signin-stat-table tbody td:nth-child(2){text-align:left}
.today-pill{display:inline-flex;align-items:center;gap:6px;max-width:150px;padding:5px 9px;border-radius:999px;font-size:11px;font-weight:750;white-space:nowrap}.today-pill i{width:6px;height:6px;border-radius:50%;background:currentColor}.today-pill--success{background:color-mix(in srgb,var(--stat-green) 13%,transparent);color:var(--stat-green)}.today-pill--failed{background:color-mix(in srgb,var(--stat-red) 13%,transparent);color:var(--stat-red)}.today-pill--empty{background:var(--app-surface-muted);color:var(--app-text-muted)}
.status-cell{display:inline-grid;width:28px;height:28px;place-items:center;border-radius:50%;font-size:14px;font-weight:850}.status-cell--success{border:1px solid color-mix(in srgb,var(--stat-green) 48%,transparent);background:color-mix(in srgb,var(--stat-green) 16%,transparent);color:var(--stat-green)}.status-cell--failed{border:1px solid color-mix(in srgb,var(--stat-red) 48%,transparent);background:color-mix(in srgb,var(--stat-red) 15%,transparent);color:var(--stat-red)}.status-cell--empty{border:1px solid color-mix(in srgb,var(--app-text-muted) 38%,transparent);background:var(--app-surface-muted);color:var(--app-text-muted);font-weight:500}
.signin-stat-empty{display:flex;min-height:180px;align-items:center;justify-content:center;gap:10px;padding:30px;color:var(--app-text-muted);font-size:12px;text-align:center}.signin-stat-loader{width:18px;height:18px;border:2px solid var(--app-border-subtle);border-top-color:var(--stat-violet);border-radius:50%;animation:signin-spin .8s linear infinite}.signin-stat-dialog__actions{display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--app-border-subtle)}@keyframes signin-spin{to{transform:rotate(360deg)}}
@media(max-width:900px){.signin-stat-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.signin-stat-board__header{align-items:flex-start;flex-direction:column}.signin-stat-legend{width:100%;overflow:auto}}
@media(max-width:620px){.signin-stat-dialog{max-height:calc(100dvh - 16px);border-radius:16px!important}.signin-stat-dialog__header{padding:6px 16px}.signin-stat-dialog__content{padding:16px}.signin-stat-dialog__header h2{font-size:16px}.signin-stat-metrics{grid-template-columns:1fr 1fr;gap:8px}.metric{gap:8px;padding:13px 11px}.metric__icon{width:25px;height:25px}.metric strong{font-size:22px}.metric p{font-size:10px}.signin-stat-board__header{padding:13px}.signin-stat-dialog__actions{padding:10px 16px}}
@media(prefers-reduced-motion:reduce){.signin-stat-loader{animation:none}}
</style>
