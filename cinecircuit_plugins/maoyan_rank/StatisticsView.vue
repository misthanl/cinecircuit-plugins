<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { Component } from "vue";
import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";

interface SubscriptionRecord { id: string | number; title: string; poster?: string; media_label: string; platform: string; release_info: string; subscribed_at: string; }
interface StatisticsResponse { items: SubscriptionRecord[]; total: number; movie_count: number; tv_count: number; platform_count: number; page: number; pages: number; }

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
const ID = "maoyan-rank";
const history = ref<StatisticsResponse>({ items: [], total: 0, movie_count: 0, tv_count: 0, platform_count: 0, page: 1, pages: 1 });
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
    <UiCard class="maoyan-dialog">
      <header class="maoyan-dialog__header">
        <div><h2>猫眼榜单订阅</h2><p>只统计已被插件成功加入订阅的作品，可按来源平台核对自动订阅结果。</p></div>
        <UiButton icon="mdi-close" variant="text" aria-label="关闭" @click="context.close" />
      </header>
      <div class="maoyan-dialog__content">
        <p v-if="loading" class="maoyan-dialog__message" role="status">正在读取订阅统计…</p>
        <UiAlert v-else-if="error" type="error" variant="tonal">{{ error }}</UiAlert>
        <section v-else class="maoyan-statistics" aria-label="猫眼榜单订阅统计">
          <dl class="maoyan-statistics__metrics">
            <div><dt>订阅记录</dt><dd>{{ history.total }} <span>条</span></dd></div>
            <div><dt>电影</dt><dd>{{ history.movie_count }} <span>条</span></dd></div>
            <div><dt>剧集／综艺</dt><dd>{{ history.tv_count }} <span>条</span></dd></div>
            <div><dt>来源平台</dt><dd>{{ history.platform_count }} <span>个</span></dd></div>
          </dl>
          <template v-if="history.total">
            <div class="maoyan-statistics__page-info" aria-live="polite"><span>第 {{ history.page }} / {{ history.pages }} 页</span><span>本页 {{ history.items.length }} 条</span></div>
            <div class="maoyan-statistics__grid">
              <article v-for="item in history.items" :key="item.id" class="maoyan-subscription">
                <div class="maoyan-subscription__poster">
                  <img v-if="posterUrl(item.poster) && !failedPosters.has(item.id)" :src="posterUrl(item.poster)" :alt="`${item.title}海报`" loading="lazy" @error="markPosterFailed(item.id)">
                  <span v-else>无海报</span>
                </div>
                <div class="maoyan-subscription__body">
                  <h3 :title="item.title">{{ item.title }}</h3>
                  <div class="maoyan-subscription__tags"><span>{{ item.media_label }}</span><span :title="item.platform">{{ item.platform }}</span></div>
                  <p class="maoyan-subscription__release">{{ item.release_info || "暂无上线信息" }}</p>
                  <p class="maoyan-subscription__time">订阅时间：<time :datetime="item.subscribed_at">{{ subscriptionTime(item.subscribed_at) }}</time></p>
                </div>
              </article>
            </div>
            <nav v-if="history.pages > 1" class="maoyan-statistics__pagination" aria-label="订阅记录分页">
              <UiButton variant="text" size="small" prepend-icon="mdi-chevron-left" :disabled="history.page <= 1 || loading" @click="load(history.page - 1)">上一页</UiButton>
              <span>{{ history.page }} / {{ history.pages }}</span>
              <UiButton variant="text" size="small" append-icon="mdi-chevron-right" :disabled="history.page >= history.pages || loading" @click="load(history.page + 1)">下一页</UiButton>
            </nav>
          </template>
          <div v-else class="maoyan-dialog__message"><h3>暂无订阅记录</h3><p>猫眼榜单中的作品成功加入订阅后，会显示在这里。</p></div>
        </section>
      </div>
      <footer class="maoyan-dialog__actions">
        <UiButton prepend-icon="mdi-refresh" variant="text" :loading="loading" @click="load()">刷新</UiButton>
        <UiButton class="maoyan-dialog__config" prepend-icon="mdi-cog-outline" variant="flat" aria-label="配置猫眼榜单" @click="context.configure">调整榜单设置</UiButton>
      </footer>
    </UiCard>
  </UiDialog>
</template>

<style scoped>
.maoyan-statistics { display: grid; gap: 22px; min-width: 0; }
.maoyan-statistics__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; margin: 0 0 6px; }
.maoyan-statistics__metrics > div { padding: 18px 24px; border-radius: 16px; background: var(--app-surface-muted); }
.maoyan-statistics__metrics > div:first-child { background: var(--app-violet-soft); }
.maoyan-statistics__metrics dt { color: var(--app-text-muted); font-size: 14px; }
.maoyan-statistics__metrics > div:first-child dt { color: var(--app-violet-text); }
.maoyan-statistics__metrics dd { margin: 10px 0 0; color: var(--app-text); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.maoyan-statistics__metrics dd span { font-size: 18px; font-weight: 500; }
.maoyan-statistics__page-info { display: flex; justify-content: space-between; color: var(--app-text-muted); font-size: 13px; }
.maoyan-statistics__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: -10px; }
.maoyan-subscription { display: grid; grid-template-columns: 96px minmax(0, 1fr); align-items: start; gap: 14px; padding: 14px; min-width: 0; border: 1px solid var(--app-border-subtle); border-radius: 14px; background: var(--app-surface); }
.maoyan-subscription__poster { display: grid; place-items: center; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; border-radius: 8px; background: var(--app-surface-muted); color: var(--app-text-muted); font-size: 12px; }
.maoyan-subscription__poster img { width: 100%; height: 100%; object-fit: cover; }
.maoyan-subscription__body { min-width: 0; padding-top: 2px; }
.maoyan-subscription h3 { margin: 0 0 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--app-text); font-size: 15px; font-weight: 600; }
.maoyan-subscription__tags { display: flex; flex-wrap: wrap; gap: 5px; }
.maoyan-subscription__tags span { max-width: 100%; padding: 3px 8px; border-radius: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: var(--app-surface-muted); color: var(--app-text-secondary); font-size: 10px; }
.maoyan-subscription__release { margin: 11px 0 6px; color: var(--app-text-secondary); font-size: 14px; overflow-wrap: anywhere; }
.maoyan-subscription__time { margin: 0; color: var(--app-text-muted); font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.maoyan-statistics__pagination { display: flex; align-items: center; justify-content: center; gap: 14px; color: var(--app-text-muted); font-size: 12px; }
.maoyan-dialog { display: flex; flex-direction: column; max-height: calc(100dvh - 32px); border: 1px solid var(--app-border); border-radius: 18px !important; background: var(--app-dialog-surface) !important; color: var(--app-text); }
.maoyan-dialog__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 20px 24px; }
.maoyan-dialog__header h2 { margin: 0; font-size: 22px; font-weight: 600; }.maoyan-dialog__header p{margin:3px 0 0;color:var(--app-text-muted);font-size:11px}
.maoyan-dialog__content { min-height: 0; overflow: auto; padding: 20px 24px; background: var(--app-surface-subtle); }
.maoyan-dialog__actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 12px 24px; border-top: 1px solid var(--app-border-subtle); }
.maoyan-dialog__config { color: var(--app-on-accent) !important; background: var(--app-violet-text) !important; }
.maoyan-dialog__message { padding: 40px 12px; text-align: center; color: var(--app-text-muted); }
.maoyan-statistics__pagination button:focus-visible { outline: 2px solid var(--app-violet-text); outline-offset: 2px; }
@media (max-width: 1250px) { .maoyan-statistics__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) {
  .maoyan-statistics__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .maoyan-statistics__metrics > div { padding: 14px 16px; }
  .maoyan-statistics__grid { grid-template-columns: minmax(0, 1fr); }
  .maoyan-dialog__content, .maoyan-dialog__header { padding: 16px; }
  .maoyan-dialog__header h2 { font-size: 18px; }
}
</style>
