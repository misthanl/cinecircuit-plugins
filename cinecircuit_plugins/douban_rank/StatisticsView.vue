<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface SubscriptionRecord { id: string | number; title: string; poster?: string; media_label: string; board: string; rating: number; subscribed_at: string; }
interface StatisticsResponse { items: SubscriptionRecord[]; total: number; movie_count: number; tv_count: number; board_count: number; page: number; pages: number; }

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
const ID = "douban-hot";
const history = ref<StatisticsResponse>({ items: [], total: 0, movie_count: 0, tv_count: 0, board_count: 0, page: 1, pages: 1 });
const loading = ref(false);
const error = ref("");
const failedPosters = ref<Set<string | number>>(new Set());
let requestedPage = 1;

function failureMessage(reason: unknown, fallback: string): string {
  if (reason && typeof reason === "object" && "message" in reason) return String(reason.message || fallback);
  return fallback;
}
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
  requestedPage = page; loading.value = true; error.value = "";
  try {
    history.value = await props.request<StatisticsResponse>(`/plugins/${ID}/api/statistics?page=${page}`);
    requestedPage = history.value.page;
    failedPosters.value = new Set();
  } catch (reason: unknown) { error.value = failureMessage(reason, "订阅统计加载失败"); }
  finally { loading.value = false; }
}
onMounted(() => load());
</script>

<template>
  <UiDialog :model-value="true" :max-width="1480" width="calc(100vw - 32px)" @update:model-value="(open: boolean) => { if (!open) context.close(); }">
    <UiCard class="douban-dialog">
      <header class="douban-dialog__header">
        <div><h2>豆瓣榜单订阅</h2><p>只统计已被插件成功加入订阅的作品，不包含仅浏览或被评分过滤的条目。</p></div>
        <UiButton icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <div class="douban-dialog__content">
        <p v-if="loading" class="douban-dialog__message" role="status">正在读取订阅统计…</p>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <section v-else class="douban-statistics" aria-label="豆瓣榜单订阅统计">
          <dl class="douban-statistics__metrics">
            <div><dt>订阅记录</dt><dd>{{ history.total }} <span>条</span></dd></div>
            <div><dt>电影</dt><dd>{{ history.movie_count }} <span>条</span></dd></div>
            <div><dt>剧集／综艺</dt><dd>{{ history.tv_count }} <span>条</span></dd></div>
            <div><dt>来源榜单</dt><dd>{{ history.board_count }} <span>个</span></dd></div>
          </dl>
          <template v-if="history.total">
            <div class="douban-statistics__page-info" aria-live="polite"><span>第 {{ history.page }} / {{ history.pages }} 页</span><span>本页 {{ history.items.length }} 条</span></div>
            <div class="douban-statistics__grid">
              <article v-for="item in history.items" :key="item.id" class="douban-subscription">
                <div class="douban-subscription__poster">
                  <img v-if="posterUrl(item.poster) && !failedPosters.has(item.id)" :src="posterUrl(item.poster)" :alt="`${item.title}海报`" loading="lazy" @error="markPosterFailed(item.id)">
                  <span v-else>无海报</span>
                </div>
                <div class="douban-subscription__body">
                  <h3 :title="item.title">{{ item.title }}</h3>
                  <div class="douban-subscription__tags"><span>{{ item.media_label }}</span><span :title="item.board">{{ item.board }}</span></div>
                  <p class="douban-subscription__rating">{{ Number.isFinite(item.rating) && item.rating > 0 ? `豆瓣评分 ${item.rating.toFixed(1)}` : "暂无评分" }}</p>
                  <p class="douban-subscription__time">订阅时间：<time :datetime="item.subscribed_at">{{ subscriptionTime(item.subscribed_at) }}</time></p>
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
        <UiButton class="douban-dialog__config" prepend-icon="mdi-cog-outline" variant="flat" aria-label="配置豆瓣榜单" @click="context.configure">调整榜单设置</UiButton>
      </footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.douban-statistics { display: grid; gap: 22px; min-width: 0; }
.douban-statistics__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 6px; }
.douban-statistics__metrics > div { padding: 15px 16px; border: 1px solid var(--app-border-subtle); border-radius: 12px; background: var(--app-surface-muted); }
.douban-statistics__metrics > div:first-child { background: var(--app-violet-soft); }
.douban-statistics__metrics dt { color: var(--app-text-muted); font-size: 12px; }
.douban-statistics__metrics > div:first-child dt { color: var(--app-violet-text); }
.douban-statistics__metrics dd { margin: 10px 0 0; color: var(--app-text); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.douban-statistics__metrics dd span { font-size: 11px; font-weight: 400; }
.douban-statistics__page-info { display: flex; justify-content: space-between; color: var(--app-text-muted); font-size: 13px; }
.douban-statistics__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: -10px; }
.douban-subscription { display: grid; grid-template-columns: 96px minmax(0, 1fr); align-items: start; gap: 14px; padding: 14px; min-width: 0; border: 1px solid var(--app-border-subtle); border-radius: 14px; background: var(--app-surface); }
.douban-subscription__poster { display: grid; place-items: center; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 8px; background: var(--app-surface-muted); color: var(--app-text-muted); font-size: 12px; }
.douban-subscription__poster img { width: 100%; height: 100%; object-fit: cover; }
.douban-subscription__body { min-width: 0; padding-top: 2px; }
.douban-subscription h3 { margin: 0 0 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--app-text); font-size: 15px; font-weight: 600; }
.douban-subscription__tags { display: flex; flex-wrap: wrap; gap: 5px; }
.douban-subscription__tags span { max-width: 100%; padding: 3px 8px; border-radius: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: var(--app-surface-muted); color: var(--app-text-secondary); font-size: 10px; }
.douban-subscription__rating { margin: 11px 0 6px; color: var(--app-text-secondary); font-size: 14px; overflow-wrap: anywhere; }
.douban-subscription__time { margin: 0; color: var(--app-text-muted); font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.douban-statistics__pagination { display: flex; align-items: center; justify-content: center; gap: 14px; color: var(--app-text-muted); font-size: 12px; }
.douban-dialog { display: flex; flex-direction: column; max-height: calc(100dvh - 32px); border: 1px solid var(--app-border); border-radius: 18px !important; background: var(--app-dialog-surface) !important; color: var(--app-text); }
.douban-dialog__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 20px 24px; }
.douban-dialog__header h2 { margin: 0; font-size: 18px; font-weight: 750; }.douban-dialog__header p{margin:3px 0 0;color:var(--app-text-muted);font-size:10px}
.douban-dialog__content { min-height: 0; overflow: auto; padding: 20px 24px; background: var(--app-surface-subtle); }
.douban-dialog__actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 12px 24px; border-top: 1px solid var(--app-border-subtle); }
.douban-dialog__config { color: var(--app-on-accent) !important; background: var(--app-violet-text) !important; }
.douban-dialog__message { padding: 40px 12px; text-align: center; color: var(--app-text-muted); }
.douban-statistics__pagination button:focus-visible { outline: 2px solid var(--app-violet-text); outline-offset: 2px; }
@media (max-width: 1250px) { .douban-statistics__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) {
  .douban-statistics__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .douban-statistics__metrics > div { padding: 14px 16px; }
  .douban-statistics__grid { grid-template-columns: minmax(0, 1fr); }
  .douban-dialog__content, .douban-dialog__header { padding: 16px; }
  .douban-dialog__header h2 { font-size: 18px; }
}
</style>
