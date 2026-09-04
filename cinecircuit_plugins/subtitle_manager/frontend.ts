import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";

const PLUGIN_ID = "subtitle-manager";
const STYLE = `
.subtitle-workspace{width:100%;min-width:0;color:#17243a}.subtitle-workspace *{box-sizing:border-box}.subtitle-hero{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:24px 26px;border:1px solid rgba(137,156,185,.22);border-radius:24px;background:linear-gradient(135deg,rgba(47,116,246,.1),rgba(255,255,255,.94) 58%);box-shadow:0 18px 42px rgba(37,61,99,.07)}.subtitle-hero h1{margin:3px 0 6px;font-size:clamp(25px,3vw,36px)}.subtitle-hero p{margin:0;color:#71809a}.subtitle-kicker{font-size:12px;font-weight:800;letter-spacing:.12em;color:#2f74f6}.subtitle-controls{display:flex;gap:10px;align-items:center}.subtitle-search{width:min(390px,48vw);min-height:42px;padding:0 14px;border:1px solid #d7dfec;border-radius:13px;background:#fff;color:#22324b;outline:none}.subtitle-search:focus{border-color:#2f74f6;box-shadow:0 0 0 3px rgba(47,116,246,.12)}.subtitle-layout{display:grid;grid-template-columns:minmax(300px,.85fr) minmax(0,1.55fr);gap:18px;margin-top:18px}.subtitle-panel{min-width:0;padding:20px;border:1px solid rgba(137,156,185,.22);border-radius:22px;background:rgba(255,255,255,.9);box-shadow:0 16px 38px rgba(37,61,99,.06)}.subtitle-panel h2{margin:0 0 4px;font-size:18px}.subtitle-panel-note{margin:0 0 16px;color:#7a879c;font-size:13px}.subtitle-list{display:grid;gap:9px;max-height:620px;overflow:auto}.subtitle-media{width:100%;display:grid;grid-template-columns:5px minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px;border:1px solid transparent;border-radius:15px;background:#f7f9fc;text-align:left;cursor:pointer}.subtitle-media:hover,.subtitle-media.is-active{border-color:rgba(47,116,246,.25);background:#f1f6ff}.subtitle-rail{align-self:stretch;border-radius:8px;background:#cfd8e7}.subtitle-media.is-active .subtitle-rail{background:#2f74f6}.subtitle-media strong,.subtitle-media small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.subtitle-media small{margin-top:4px;color:#8591a5}.subtitle-count{padding:4px 8px;border-radius:999px;background:#e8eef8;color:#60708a;font-size:12px}.subtitle-detail{display:grid;gap:16px}.subtitle-path{padding:13px 15px;border-radius:14px;background:#f4f7fb;color:#66758d;word-break:break-all}.subtitle-timeline{position:relative;display:grid;gap:12px;padding-left:20px}.subtitle-timeline:before{content:"";position:absolute;left:5px;top:5px;bottom:5px;width:2px;background:#dce5f2}.subtitle-file{position:relative;display:flex;justify-content:space-between;gap:16px;padding:12px 14px;border-radius:14px;background:#f8fafc}.subtitle-file:before{content:"";position:absolute;left:-19px;top:18px;width:10px;height:10px;border:2px solid #fff;border-radius:50%;background:#2f74f6;box-shadow:0 0 0 2px rgba(47,116,246,.18)}.subtitle-file small{color:#8692a6}.subtitle-empty{display:grid;place-items:center;min-height:190px;color:#8995a8;text-align:center}.subtitle-upload{display:grid;grid-template-columns:minmax(0,1fr) 160px auto;gap:10px;padding-top:16px;border-top:1px solid #e5eaf2}.subtitle-upload input,.subtitle-upload select{min-width:0;min-height:42px;padding:0 12px;border:1px solid #d7dfec;border-radius:12px;background:#fff}.subtitle-button{min-height:42px;padding:0 16px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.subtitle-button:disabled{cursor:not-allowed;opacity:.45}.subtitle-status{min-height:22px;margin:0;color:#63728a}.subtitle-status.is-error{color:#d04444}@media(max-width:900px){.subtitle-layout{grid-template-columns:1fr}.subtitle-list{max-height:340px}}@media(max-width:620px){.subtitle-hero{align-items:stretch;flex-direction:column}.subtitle-controls{align-items:stretch;flex-direction:column}.subtitle-search{width:100%}.subtitle-upload{grid-template-columns:1fr}.subtitle-panel{padding:16px}}
@media(max-width:620px){.subtitle-file{flex-wrap:wrap;gap:8px}.subtitle-file strong{flex-basis:100%}}
`;

interface SubtitleFile {
  name: string;
  size?: number;
}

interface MediaItem {
  path: string;
  title?: string;
  subtitles?: SubtitleFile[];
}

interface OnlineSubtitle {
  title: string;
  provider: string;
  language?: string;
  url?: string;
}

interface ItemList<T> { items?: T[] }
interface AdjustmentResult { adjusted_count?: number }

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h, onMounted, ref } = sdk.vue;
  const Page = defineComponent({
  name: "SubtitleWorkspacePage",
    setup() {
      const items = ref<MediaItem[]>([]);
      const selected = ref<MediaItem | null>(null);
      const query = ref("");
      const loading = ref(false);
      const uploading = ref(false);
      const status = ref("");
      const error = ref("");
      const language = ref("zh-CN");
      const file = ref<File | null>(null);
      const online = ref<OnlineSubtitle[]>([]);
      const searching = ref(false);

      async function load() {
        loading.value = true;
        error.value = "";
        try {
          const result = await sdk.request<ItemList<MediaItem>>(`/plugins/${PLUGIN_ID}/api/catalog?query=${encodeURIComponent(query.value)}&limit=100`);
          items.value = Array.isArray(result?.items) ? result.items : [];
          selected.value = items.value.find((item) => item.path === selected.value?.path) || items.value[0] || null;
          status.value = items.value.length ? `已读取 ${items.value.length} 个本地媒体文件` : "没有找到可访问的本地整理记录";
        } catch (reason) {
          error.value = reason instanceof Error ? reason.message : "字幕目录读取失败";
        } finally {
          loading.value = false;
        }
      }

      async function upload() {
        if (!selected.value || !file.value || uploading.value) return;
        uploading.value = true;
        error.value = "";
        try {
          const params = new URLSearchParams({ media_path: selected.value.path, language: language.value });
          await sdk.request(`/plugins/${PLUGIN_ID}/api/upload?${params}`, {
            method: "POST",
            headers: { "Content-Type": file.value.type || "application/octet-stream", "X-Plugin-Filename": encodeURIComponent(file.value.name) },
            body: file.value,
          });
          status.value = `已写入 ${file.value.name}`;
          file.value = null;
          await load();
        } catch (reason) {
          error.value = reason instanceof Error ? reason.message : "字幕上传失败";
        } finally {
          uploading.value = false;
        }
      }

      async function searchOnline() {
        if (!selected.value || searching.value) return;
        searching.value = true;
        error.value = "";
        try {
          const keyword = selected.value.title || selected.value.path.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "";
          const result = await sdk.request<ItemList<OnlineSubtitle>>(`/plugins/${PLUGIN_ID}/api/online?query=${encodeURIComponent(keyword)}`);
          online.value = Array.isArray(result?.items) ? result.items : [];
          status.value = online.value.length ? `找到 ${online.value.length} 条在线字幕` : "在线字幕源暂无匹配结果";
        } catch (reason) {
          error.value = reason instanceof Error ? reason.message : "在线字幕搜索失败";
        } finally {
          searching.value = false;
        }
      }

      async function removeSubtitle(subtitle: SubtitleFile) {
        if (!selected.value || !window.confirm(`确定删除字幕 ${subtitle.name}？`)) return;
        try {
          await sdk.request(`/plugins/${PLUGIN_ID}/api/delete`, { method: "POST", body: JSON.stringify({ media_path: selected.value.path, subtitle_name: subtitle.name }) });
          status.value = `已删除 ${subtitle.name}`;
          await load();
        } catch (reason) {
          error.value = reason instanceof Error ? reason.message : "字幕删除失败";
        }
      }

      async function adjustSubtitle(subtitle: SubtitleFile) {
        if (!selected.value) return;
        const value = window.prompt("输入字幕偏移秒数：正数延后，负数提前", "0");
        if (value === null || !value.trim()) return;
        const offset = Number(value);
        if (!Number.isFinite(offset)) {
          error.value = "请输入有效的时间偏移秒数";
          return;
        }
        try {
          const result = await sdk.request<AdjustmentResult>(`/plugins/${PLUGIN_ID}/api/adjust`, {
            method: "POST",
            body: JSON.stringify({ media_path: selected.value.path, subtitle_name: subtitle.name, offset_seconds: offset }),
          });
          status.value = `已调整 ${result.adjusted_count || 0} 条字幕时间轴`;
          await load();
        } catch (reason) {
          error.value = reason instanceof Error ? reason.message : "字幕调轴失败";
        }
      }

      onMounted(load);
      return () => h("section", { class: "subtitle-workspace" }, [
        h("style", STYLE),
        h("header", { class: "subtitle-hero" }, [
      h("div", [h("div", { class: "subtitle-kicker" }, "SUBTITLE WORKSPACE"), h("h1", "字幕管理助手"), h("p", "在线搜索、手动上传、同名匹配与外挂字幕管理。")]),
          h("div", { class: "subtitle-controls" }, [
            h("input", { class: "subtitle-search", value: query.value, placeholder: "搜索媒体名称或路径", onInput: (event: Event) => { query.value = (event.currentTarget as HTMLInputElement).value; }, onKeyup: (event: KeyboardEvent) => { if (event.key === "Enter") load(); } }),
            h("button", { class: "subtitle-button", disabled: loading.value, onClick: load }, loading.value ? "读取中…" : "搜索"),
          ]),
        ]),
        h("div", { class: "subtitle-layout" }, [
          h("aside", { class: "subtitle-panel" }, [
            h("h2", "媒体目录"), h("p", { class: "subtitle-panel-note" }, "仅显示整理成功且当前可访问的本地媒体文件。"),
            h("div", { class: "subtitle-list" }, items.value.length ? items.value.map((item) => h("button", { class: ["subtitle-media", selected.value?.path === item.path && "is-active"], onClick: () => { selected.value = item; } }, [h("span", { class: "subtitle-rail" }), h("span", [h("strong", item.title || item.path.split(/[\\/]/).pop()), h("small", item.path)]), h("span", { class: "subtitle-count" }, `${item.subtitles?.length || 0} 条`)])) : [h("div", { class: "subtitle-empty" }, loading.value ? "正在读取媒体目录…" : "暂无可管理媒体")]),
          ]),
          h("main", { class: "subtitle-panel subtitle-detail" }, selected.value ? [
            h("div", [h("h2", selected.value.title || "字幕详情"), h("p", { class: "subtitle-path" }, selected.value.path)]),
            h("div", { class: "subtitle-timeline" }, selected.value.subtitles?.length ? selected.value.subtitles.map((subtitle) => h("div", { class: "subtitle-file" }, [h("strong", subtitle.name), h("small", `${Math.max(1, Math.round((subtitle.size || 0) / 1024))} KB`), h("button", { class: "subtitle-button", onClick: () => adjustSubtitle(subtitle) }, "调轴"), h("button", { class: "subtitle-button", onClick: () => removeSubtitle(subtitle) }, "删除")])) : [h("div", { class: "subtitle-file" }, [h("span", "尚未发现外挂字幕"), h("small", "可在线搜索或手动上传")])]),
            h("div", [h("button", { class: "subtitle-button", disabled: searching.value, onClick: searchOnline }, searching.value ? "搜索中…" : "在线搜索字幕")]),
            online.value.length ? h("div", { class: "subtitle-timeline" }, online.value.slice(0, 20).map((item) => h("div", { class: "subtitle-file" }, [h("a", { href: item.url || "#", target: "_blank", rel: "noopener noreferrer" }, item.title), h("small", `${item.provider}${item.language ? ` · ${item.language}` : ""}`)]))) : null,
            h("p", { class: ["subtitle-status", error.value && "is-error"] }, error.value || status.value),
            h("div", { class: "subtitle-upload" }, [
              h("input", { type: "file", accept: ".srt,.ass,.ssa,.sub,.vtt,.webvtt", onChange: (event: Event) => { file.value = (event.currentTarget as HTMLInputElement).files?.[0] || null; } }),
              h("select", { value: language.value, onChange: (event: Event) => { language.value = (event.currentTarget as HTMLSelectElement).value; } }, [["zh-CN", "简体中文"], ["zh-TW", "繁体中文"], ["zh", "中文"], ["en", "英语"], ["ja", "日语"], ["ko", "韩语"]].map(([value, label]) => h("option", { value }, label))),
              h("button", { class: "subtitle-button", disabled: !file.value || uploading.value, onClick: upload }, uploading.value ? "上传中…" : "上传字幕"),
            ]),
          ] : [h("div", { class: "subtitle-empty" }, "请先从左侧选择媒体")]),
        ]),
      ]);
    },
  });
  sdk.registerPage({ pluginId: PLUGIN_ID, route: `plugin-${PLUGIN_ID}`, title: "字幕大师", icon: "mdi-subtitles-outline", section: "tools", order: 65, component: Page });
}
