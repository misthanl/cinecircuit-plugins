const ID = "douban-hot";
const STYLE = `
.douban-statistics { display: grid; gap: 22px; min-width: 0; }
.douban-statistics__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; margin: 0 0 6px; }
.douban-statistics__metrics > div { padding: 18px 24px; border-radius: 16px; background: var(--app-surface-muted); }
.douban-statistics__metrics > div:first-child { background: var(--app-violet-soft); }
.douban-statistics__metrics dt { color: var(--app-text-muted); font-size: 14px; }
.douban-statistics__metrics > div:first-child dt { color: var(--app-violet-text); }
.douban-statistics__metrics dd { margin: 10px 0 0; color: var(--app-text); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.douban-statistics__metrics dd span { font-size: 18px; font-weight: 500; }
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
@media (max-width: 1250px) {
  .douban-statistics__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .douban-statistics__metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .douban-statistics__metrics > div { padding: 14px 16px; }
  .douban-statistics__grid { grid-template-columns: minmax(0, 1fr); }
}

.douban-dialog{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);border:1px solid var(--app-border);border-radius:18px!important;background:var(--app-dialog-surface)!important;color:var(--app-text)}
.douban-dialog__header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:20px 24px}.douban-dialog__header h2{margin:0;font-size:22px;font-weight:600}
.douban-dialog__content{min-height:0;overflow:auto;padding:20px 24px;background:var(--app-surface-subtle)}
.douban-dialog__actions{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:12px 24px;border-top:1px solid var(--app-border-subtle)}
.douban-dialog__config{border-radius:50%!important;color:var(--app-on-accent)!important;background:var(--app-violet-text)!important}
.douban-dialog__message{padding:40px 12px;text-align:center;color:var(--app-text-muted)}
.douban-statistics__pagination button:focus-visible{outline:2px solid var(--app-violet-text);outline-offset:2px}
@media(max-width:600px){.douban-dialog__content{padding:16px}.douban-dialog__header{padding:16px}.douban-dialog__header h2{font-size:18px}}
`;

export function install(sdk) {
  const { defineComponent, h, onMounted, ref } = sdk.vue;
  const { Button, Card, Dialog, Alert } = sdk.ui.components;
  function posterUrl(value) {
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
  function subscriptionTime(value) {
    const text = String(value || "");
    const date = new Date(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text) ? `${text.replace(" ", "T")}Z` : text);
    return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).replaceAll("/", "-") : "未知时间";
  }
  const Statistics = defineComponent({
    name: "DoubanStatistics", inheritAttrs: false,
    props: { context: { type: Object, required: true } },
    setup(props) {
      const history = ref({ items: [], total: 0, movie_count: 0, tv_count: 0, board_count: 0, page: 1, pages: 1 });
      const loading = ref(false), error = ref(""), failedPosters = ref(new Set());
      let requestedPage = 1;
      async function load(page = requestedPage) {
        if (loading.value) return;
        requestedPage = page; loading.value = true; error.value = "";
        try { history.value = await sdk.request(`/plugins/${ID}/api/statistics?page=${page}`); requestedPage = history.value.page; failedPosters.value = new Set(); }
        catch (reason) { error.value = reason.message || "订阅统计加载失败"; }
        finally { loading.value = false; }
      }
      onMounted(() => load());
      function overview() {
        const data = history.value;
        const metrics = [
          { label: "订阅记录", value: data.total, unit: "条" },
          { label: "电影", value: data.movie_count, unit: "条" },
          { label: "剧集／综艺", value: data.tv_count, unit: "条" },
          { label: "来源榜单", value: data.board_count, unit: "个" },
        ];
        return h("section", { class: "douban-statistics", "aria-label": "豆瓣榜单订阅统计" }, [
          h("dl", { class: "douban-statistics__metrics" }, metrics.map(metric => h("div", [h("dt", metric.label), h("dd", [String(metric.value), " ", h("span", metric.unit)])]))) ,
          data.total ? [
            h("div", { class: "douban-statistics__page-info", "aria-live": "polite" }, [h("span", `第 ${data.page} / ${data.pages} 页`), h("span", `本页 ${data.items.length} 条`)]),
            h("div", { class: "douban-statistics__grid" }, data.items.map(item => h("article", { class: "douban-subscription", key: item.id }, [
              h("div", { class: "douban-subscription__poster" }, posterUrl(item.poster) && !failedPosters.value.has(item.id) ? h("img", { src: posterUrl(item.poster), alt: `${item.title}海报`, loading: "lazy", onError: () => failedPosters.value.add(item.id) }) : h("span", "无海报")),
              h("div", { class: "douban-subscription__body" }, [h("h3", { title: item.title }, item.title), h("div", { class: "douban-subscription__tags" }, [h("span", item.media_label), h("span", { title: item.board }, item.board)]), h("p", { class: "douban-subscription__rating" }, Number.isFinite(item.rating) && item.rating > 0 ? `豆瓣评分 ${item.rating.toFixed(1)}` : "暂无评分"), h("p", { class: "douban-subscription__time" }, ["订阅时间：", h("time", { datetime: item.subscribed_at }, subscriptionTime(item.subscribed_at))])]),
            ]))),
            data.pages > 1 ? h("nav", { class: "douban-statistics__pagination", "aria-label": "订阅记录分页" }, [h(Button, { variant: "text", size: "small", prependIcon: "mdi-chevron-left", disabled: data.page <= 1 || loading.value, onClick: () => load(data.page - 1) }, () => "上一页"), h("span", `${data.page} / ${data.pages}`), h(Button, { variant: "text", size: "small", appendIcon: "mdi-chevron-right", disabled: data.page >= data.pages || loading.value, onClick: () => load(data.page + 1) }, () => "下一页")]) : null,
          ] : h("div", { class: "douban-dialog__message" }, [h("h3", "暂无订阅记录"), h("p", "豆瓣榜单中的作品成功加入订阅后，会显示在这里。")]),
        ]);
      }
      return () => h(Dialog, { modelValue: true, maxWidth: 1480, width: "calc(100vw - 32px)", "onUpdate:modelValue": open => { if (!open) props.context.close(); } }, () => h(Card, { class: "douban-dialog" }, () => [
        h("style", STYLE),
        h("header", { class: "douban-dialog__header" }, [h("h2", "豆瓣榜单订阅"), h(Button, { icon: "mdi-close", variant: "text", "aria-label": "关闭", onClick: props.context.close })]),
        h("div", { class: "douban-dialog__content" }, loading.value ? h("p", { class: "douban-dialog__message", role: "status" }, "正在读取订阅统计…") : error.value ? h(Alert, { type: "error", variant: "tonal" }, () => error.value) : overview()),
        h("footer", { class: "douban-dialog__actions" }, [h(Button, { prependIcon: "mdi-refresh", variant: "text", loading: loading.value, onClick: () => load() }, () => "刷新"), h(Button, { class: "douban-dialog__config", icon: "mdi-cog-outline", variant: "flat", "aria-label": "配置豆瓣榜单", title: "配置豆瓣榜单", onClick: props.context.configure })]),
      ]));
    },
  });
  sdk.registerContribution({ pluginId: ID, slot: "plugin.statistics", key: "subscriptions", component: Statistics });
}
