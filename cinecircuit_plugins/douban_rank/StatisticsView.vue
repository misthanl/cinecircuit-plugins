<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface SubscriptionRecord { id: string | number; title: string; poster?: string; media_label: string; board: string; rating: number | null; subscribed_at: string; }
interface RunItem { title: string; board: string; season: string; status: string; retry: boolean; reason: string; }
interface RunSnapshot { status: string; updated_at: string; items: RunItem[]; checked: number; subscribed: number; existing: number; retry: number; }
interface StatisticsResponse { items: SubscriptionRecord[]; total: number; movie_count: number; tv_count: number; board_count: number; page: number; pages: number; latest_run?: RunSnapshot | null; cumulative?: { checked: number; subscribed: number; existing: number; retry: number }; }

const props = defineProps<{
  context: PluginContributionContext;
  request: CineCircuitPluginSdk["request"];
  imageComponent?: Component;
  buttonComponent: Component;
  cardComponent: Component;
  dialogComponent: Component;
  alertComponent: Component;
}>();
const UiImage = props.imageComponent;
const UiButton = props.buttonComponent;
const UiCard = props.cardComponent;
const UiDialog = props.dialogComponent;
const UiAlert = props.alertComponent;
const ID = "douban-hot";
const history = ref<StatisticsResponse>({ items: [], total: 0, movie_count: 0, tv_count: 0, board_count: 0, page: 1, pages: 1 });
const loading = ref(false);
const loaded = ref(false);
const historyGrid = ref<HTMLElement | null>(null);
const historyHeight = ref(0);
const error = ref("");
const failedPosters = ref<Set<string | number>>(new Set());
let requestedPage = 1;
const expanded = ref(false);
const retryOnly = ref(false);
const detailPage = ref(1);
const latest = computed(() => history.value.latest_run);
const cumulative = computed(() => history.value.cumulative);
const detailItems = computed(() => (latest.value?.items || []).filter(item => !retryOnly.value || item.retry));
const detailPages = computed(() => Math.max(1, Math.ceil(detailItems.value.length / 5)));
const visibleDetails = computed(() => detailItems.value.slice((detailPage.value - 1) * 5, detailPage.value * 5));
function showRetry() { retryOnly.value = true; expanded.value = true; detailPage.value = 1; }
function toggleDetails() { expanded.value = !expanded.value; if (expanded.value) { retryOnly.value = false; detailPage.value = 1; } }
function statusLabel(item: RunItem) {
  return ({ subscribed: "新增订阅", already_subscribed: "已订阅", duplicate: "已订阅", in_library: "已入库", skipped: "已跳过", unknown: "待重试", not_recognized: "待重试" } as Record<string, string>)[item.status] || "待重试";
}

function failureMessage(reason: unknown, fallback: string): string {
  if (reason && typeof reason === "object" && "message" in reason) return String(reason.message || fallback);
  return fallback;
}
function ratingLabel(value: number | null) { return value && Number.isFinite(value) ? `豆瓣评分 ${value.toFixed(1)}` : "暂无评分"; }
function posterUrl(value: unknown) {
  const raw = String(value || "");
  if (!raw) return "";
  if (raw.startsWith("/explore/image-proxy?")) return raw;
  try {
    const url = new URL(raw);
    if (!["https:", "http:"].includes(url.protocol)) return "";
    if (url.hostname === "image.tmdb.org") return `/explore/image-proxy?source_key=tmdb&url=${encodeURIComponent(raw)}`;
    if (url.hostname === "doubanio.com" || url.hostname.endsWith(".doubanio.com")) return `/explore/image-proxy?source_key=douban&url=${encodeURIComponent(raw)}`;
    return raw;
  } catch { return ""; }
}
function subscriptionTime(value: unknown) {
  const text = String(value || "");
  const date = new Date(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text) ? `${text.replace(" ", "T")}Z` : text);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).replaceAll("/", "-") : "未知时间";
}
function markPosterFailed(id: string | number) { failedPosters.value = new Set([...failedPosters.value, id]); }
async function load(page = requestedPage) {
  if (loading.value) return;
  historyHeight.value = historyGrid.value?.getBoundingClientRect().height || historyHeight.value;
  loading.value = true; error.value = "";
  try {
    history.value = await props.request<StatisticsResponse>(`/plugins/${ID}/api/statistics?page=${page}`);
    detailPage.value = Math.min(detailPage.value, detailPages.value);
    requestedPage = history.value.page;
    loaded.value = true;
    failedPosters.value = new Set();
  } catch (reason: unknown) { error.value = failureMessage(reason, "订阅统计加载失败"); }
  finally { loading.value = false; }
}
onMounted(() => load());
</script>

<template>
  <UiDialog :model-value="true" :max-width="1000" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="douban-dialog">
      <header class="douban-dialog__header">
        <h2>豆瓣榜单追踪 · 数据统计</h2>
        <UiButton class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <div class="douban-dialog__content">
        <p v-if="loading && !loaded" class="douban-dialog__message" role="status">正在读取订阅统计…</p>
        <UiAlert v-if="error" type="error" variant="tonal" role="alert">{{ error }}</UiAlert>
        <section v-if="loaded" class="douban-statistics" aria-label="豆瓣榜单订阅统计">
          <dl class="douban-statistics__metrics">
            <div><dt>累计检查</dt><dd>{{ cumulative?.checked ?? '—' }}</dd></div>
            <div><dt>累计新增订阅</dt><dd>{{ cumulative?.subscribed ?? '—' }}</dd></div>
            <div><dt>累计已存在／已处理</dt><dd>{{ cumulative?.existing ?? '—' }}</dd></div>
            <div class="douban-retry-metric"><dt>累计需重试次数</dt><dd>{{ cumulative?.retry ?? '—' }}</dd></div>
          </dl>
          <section class="douban-run" aria-label="本次处理结果">
            <div class="douban-run__heading"><h3>本次处理结果<span> · {{ latest?.items.length ?? 0 }} 条</span></h3><UiButton variant="text" :disabled="!latest?.items.length" :aria-expanded="expanded" aria-controls="douban-run-details" @click="toggleDetails">{{ expanded ? '收起明细' : '查看明细' }}</UiButton></div>
            <div v-if="expanded" id="douban-run-details">
              <div class="douban-run__filters"><UiButton variant="text" :aria-pressed="!retryOnly" @click="retryOnly = false; detailPage = 1">全部</UiButton><UiButton variant="text" :aria-pressed="retryOnly" @click="showRetry">待重试</UiButton></div>
              <div class="douban-run__table"><table><colgroup><col style="width: 40%"><col style="width: 20%"><col style="width: 16%"><col style="width: 24%"></colgroup><thead><tr><th>作品／目标季</th><th>榜单来源</th><th>处理状态</th><th>原因</th></tr></thead><tbody><tr v-for="(item, index) in visibleDetails" :key="index"><td>{{ item.title }}<span v-if="item.season"> · {{ item.season }}</span></td><td>{{ item.board || '—' }}</td><td><span class="douban-run__status" :class="{ 'is-retry': item.retry }">{{ statusLabel(item) }}</span></td><td>{{ item.reason }}</td></tr></tbody></table></div>
              <p v-if="!detailItems.length" class="douban-statistics__page-info">暂无{{ retryOnly ? '待重试' : '处理' }}记录</p>
              <nav v-if="detailPages > 1" class="douban-statistics__pagination" aria-label="本次处理结果分页"><UiButton variant="text" :disabled="detailPage <= 1" @click="detailPage--">上一页</UiButton><span>{{ detailPage }} / {{ detailPages }}</span><UiButton variant="text" :disabled="detailPage >= detailPages" @click="detailPage++">下一页</UiButton></nav>
            </div>
          </section>
          <div class="douban-run__heading"><h3>订阅历史</h3><span>累计 {{ history.total }} 条</span></div>
          <template v-if="history.total">
            <div ref="historyGrid" class="douban-statistics__grid" :aria-busy="loading" :style="historyHeight ? { minHeight: `${historyHeight}px` } : undefined">
              <article v-for="item in history.items" :key="item.id" class="douban-subscription">
                <div class="douban-subscription__poster">
                  <UiImage v-if="UiImage && posterUrl(item.poster) && !failedPosters.has(item.id)" :src="posterUrl(item.poster)" :alt="`${item.title}海报`" loading="lazy" @error="markPosterFailed(item.id)" />
                  <span v-else>{{ UiImage ? "无海报" : "请更新主程序" }}</span>
                </div>
                <div class="douban-subscription__body">
                  <h3 :title="item.title">{{ item.title }}</h3>
                  <div class="douban-subscription__tags"><span>{{ item.media_label }}</span><span :title="item.board">{{ item.board }}</span></div>
                  <p class="douban-subscription__release" :title="ratingLabel(item.rating)">{{ ratingLabel(item.rating) }}</p>
                  <p class="douban-subscription__time" :title="`订阅时间：${subscriptionTime(item.subscribed_at)}`"><time :datetime="item.subscribed_at" :aria-label="`订阅时间：${subscriptionTime(item.subscribed_at)}`"><span>订阅时间：{{ subscriptionTime(item.subscribed_at).split(' ')[0] }}</span><span>{{ subscriptionTime(item.subscribed_at).split(' ')[1] || '—' }}</span></time></p>
                </div>
              </article>
            </div>
            <nav v-if="history.pages > 1" class="douban-statistics__pagination" aria-label="订阅记录分页">
              <UiButton variant="text" size="small" prepend-icon="mdi-chevron-left" :disabled="history.page <= 1 || loading" @click="load(history.page - 1)">上一页</UiButton>
              <span>{{ history.page }} / {{ history.pages }}</span>
              <UiButton variant="text" size="small" append-icon="mdi-chevron-right" :disabled="history.page >= history.pages || loading" @click="load(history.page + 1)">下一页</UiButton>
            </nav>
          </template>
          <div v-else class="douban-dialog__message"><h3>暂无订阅记录</h3><p>豆瓣榜单中的作品成功加入订阅后，会显示在这里。</p></div>
        </section>
      </div>
      <footer class="douban-dialog__actions">
        <UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load()">刷新</UiButton>
      </footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.douban-statistics { display: grid; gap: 22px; min-width: 0; }
.douban-run { border-block: 1px solid var(--app-border-subtle); padding-block: 12px; }
.douban-run__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.douban-run__heading h3 { margin: 0; color: var(--app-text); font-size: var(--app-font-size-body); }
.douban-run__heading span { color: var(--app-text-muted); font-weight: normal; }
.douban-run__filters { display: flex; gap: 8px; }
.douban-run__table { overflow-x: auto; }
.douban-run table { width: 100%; min-width: 640px; table-layout: fixed; border-collapse: collapse; text-align: left; }
.douban-run th, .douban-run td { padding: 14px 12px; border-bottom: 1px solid var(--app-border-subtle); }
.douban-run td { overflow-wrap: anywhere; }
.douban-run th { color: var(--app-text-muted); background: var(--app-surface-muted); white-space: nowrap; }
.douban-run__status { white-space: nowrap; color: var(--app-primary, #2968ff); }
.douban-run__status.is-retry { color: var(--app-warning, #b76a00); }
.douban-statistics__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 6px; }
.douban-statistics__metrics > div { padding: 15px 16px; border: 1px solid var(--app-border-subtle); border-radius: 12px; background: var(--app-surface-muted); }
.douban-statistics__metrics dt { color: var(--app-text-muted); font-size: 12px; }
.douban-statistics__metrics dd { margin: 10px 0 0; color: var(--app-text); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.douban-statistics__metrics dd span { font-size: 11px; font-weight: 400; }
.douban-statistics__page-info { display: flex; justify-content: space-between; color: var(--app-text-muted); font-size: 13px; }
.douban-statistics__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; align-items: start; margin-top: -10px; }
.douban-subscription { display: grid; grid-template-columns: 64px minmax(0, 1fr); grid-template-rows: 96px; align-items: start; gap: 10px; padding: 10px; min-width: 0; overflow: hidden; border: 1px solid var(--app-border-subtle); border-radius: 11px; background: var(--app-surface); }
.douban-subscription__poster { display: grid; place-items: center; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 6px; background: var(--app-surface-muted); color: var(--app-text-muted); font-size: var(--app-font-size-caption, 12px); }
.douban-subscription__poster img { width: 100%; height: 100%; min-height: 0; object-fit: contain; }
.douban-subscription__body { display: flex; flex-direction: column; gap: 5px; min-width: 0; height: 96px; max-height: 96px; overflow: hidden; }
.douban-subscription h3 { flex-shrink: 0; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--app-text); font-size: var(--app-font-size-caption, 12px); line-height: 18px; font-weight: 600; }
.douban-subscription__tags { display: flex; flex-wrap: nowrap; flex-shrink: 0; gap: 4px; min-width: 0; overflow: hidden; }
.douban-subscription__tags span { min-width: 0; max-width: 100%; padding: 1px 5px; border-radius: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: var(--app-surface-muted); color: var(--app-text-secondary); font-size: var(--app-font-size-helper, 10px); line-height: 16px; }
.douban-subscription__tags span:first-child { flex-shrink: 0; }
.douban-subscription__release { flex-shrink: 0; margin: 0; color: var(--app-text-secondary); font-size: var(--app-font-size-helper, 10px); line-height: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.douban-subscription__time { flex-shrink: 0; height: 28px; margin: 0; margin-top: auto; color: var(--app-text-muted); font-size: var(--app-font-size-helper, 10px); line-height: 14px; overflow: hidden; font-variant-numeric: tabular-nums; }
.douban-subscription__time span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.douban-statistics__pagination { display: flex; align-items: center; justify-content: center; gap: 14px; color: var(--app-text-muted); font-size: 12px; }
.douban-dialog { display: flex; flex-direction: column; max-height: calc(100dvh - 32px); border: 1px solid var(--app-border); border-radius: 18px !important; background: var(--app-dialog-surface) !important; color: var(--app-text); }
.douban-dialog__header { display: flex; box-sizing: border-box; height: var(--app-plugin-dialog-header-height, 58px); min-height: var(--app-plugin-dialog-header-height, 58px); max-height: var(--app-plugin-dialog-header-height, 58px); flex: 0 0 var(--app-plugin-dialog-header-height, 58px); align-items: center; justify-content: space-between; gap: 12px; padding: 6px 24px; }
.douban-dialog__header h2 { margin: 0; font-size: 18px; font-weight: 750; }
.douban-dialog__content { min-height: 0; overflow: auto; padding: 20px 24px; background: var(--app-surface-subtle); }
.douban-dialog__actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 12px 24px; border-top: 1px solid var(--app-border-subtle); }
.douban-dialog__message { padding: 40px 12px; text-align: center; color: var(--app-text-muted); }
.douban-statistics__pagination button:focus-visible { outline: 2px solid var(--app-violet-text); outline-offset: 2px; }
@media (max-width: 760px) {
  .douban-dialog { height: auto; max-height: min(680px, 76dvh); border-radius: 16px !important; }
  .douban-statistics__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .douban-statistics__metrics > div { padding: 14px 16px; }
  .douban-dialog__content { padding: 16px; }
  .douban-dialog__header { padding: 6px 16px; }
  .douban-dialog__header h2 { font-size: 18px; }
}
@media (max-width: 1100px) and (min-width: 851px) {
  .douban-statistics__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 850px) and (min-width: 601px) {
  .douban-statistics__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .douban-statistics__grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
