import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";

const ID = "emby-cover-generator";
const CSS = `.cover{display:grid;gap:18px;color:var(--app-text,#17243a)}.cover *{box-sizing:border-box}.cover-head,.cover-card{border:1px solid var(--app-border,#dfe5ef);border-radius:22px;background:#fff;box-shadow:0 14px 36px rgba(37,61,99,.06)}.cover-head{display:flex;justify-content:space-between;align-items:center;padding:24px}.cover h1,.cover h2{margin:0}.cover p{margin:5px 0 0;color:#71809a}.cover button{min-height:41px;padding:0 16px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.cover button.alt{background:#edf3ff;color:#245fc4}.cover-layout{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.25fr);gap:16px}.cover-card{padding:20px}.cover-list{display:grid;gap:9px;margin-top:14px}.cover-row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;padding:12px;border:1px solid #e0e6ef;border-radius:13px;background:#f8fafc}.cover-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cover-field{display:grid;gap:6px}.cover-field.full{grid-column:1/-1}.cover-field span{font-size:13px;font-weight:700;color:#60708a}.cover-field input,.cover-field select,.cover-field textarea{width:100%;min-height:42px;padding:0 12px;border:1px solid #d7dfeb;border-radius:11px;background:#fff}.cover-field textarea{min-height:90px;padding-top:10px}.cover-styles{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.cover-style{padding:14px 8px!important;background:#f0f4fa!important;color:#43536b!important}.cover-style.on{background:#2f74f6!important;color:#fff!important}@media(max-width:820px){.cover-layout{grid-template-columns:1fr}.cover-grid{grid-template-columns:1fr}.cover-field.full{grid-column:auto}.cover-styles{grid-column:auto;grid-template-columns:repeat(2,1fr)}.cover-head{align-items:stretch;flex-direction:column;gap:14px}}`;

type ConfigValue = string | number | boolean | string[];
interface CoverConfig {
  [key: string]: ConfigValue | undefined;
  selected_servers?: string[];
  include_libraries?: string[];
  dry_run?: boolean;
  cover_style_base?: string;
  resolution?: string;
  sort_by?: string;
  title_config?: string;
  show_item_count?: boolean;
}
interface MediaServer { id: string; name: string }
interface MediaLibrary { id: string; name: string; collection_type?: string }
interface InventoryResponse {
  servers?: MediaServer[];
  libraries?: MediaLibrary[];
  config?: CoverConfig;
}
interface LibrariesResponse { items?: MediaLibrary[] }
type FieldInputType = "text" | "number";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
function inputTarget(event: Event): HTMLInputElement {
  return event.target as HTMLInputElement;
}
function selectTarget(event: Event): HTMLSelectElement {
  return event.target as HTMLSelectElement;
}
function textAreaTarget(event: Event): HTMLTextAreaElement {
  return event.target as HTMLTextAreaElement;
}

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h, onMounted, ref } = sdk.vue;
  const Page = defineComponent({
    name: "LibraryArtworkPage",
    setup() {
      const servers = ref<MediaServer[]>([]);
      const libraries = ref<MediaLibrary[]>([]);
      const config = ref<CoverConfig>({});
      const busy = ref(false);
      const message = ref("");

      async function load(): Promise<void> {
        busy.value = true;
        try {
          const data = await sdk.request<InventoryResponse>(`/plugins/${ID}/api/inventory`);
          servers.value = data.servers || [];
          libraries.value = data.libraries || [];
          config.value = data.config || {};
        } catch (error) {
          message.value = errorMessage(error, "读取失败");
        } finally {
          busy.value = false;
        }
      }

      function set(key: string, value: ConfigValue): void {
        config.value = { ...config.value, [key]: value };
      }

      function toggle(key: string, value: string): void {
        const current = config.value[key];
        const selected = new Set(Array.isArray(current) ? current : []);
        if (selected.has(value)) selected.delete(value);
        else selected.add(value);
        set(key, [...selected]);
      }

      async function chooseServer(id: string): Promise<void> {
        set("selected_servers", id ? [id] : []);
        busy.value = true;
        try {
          const data = await sdk.request<LibrariesResponse>(`/plugins/${ID}/api/libraries?server_id=${encodeURIComponent(id)}`);
          libraries.value = data.items || [];
          set("include_libraries", []);
        } finally {
          busy.value = false;
        }
      }

      async function save(): Promise<void> {
        busy.value = true;
        try {
          config.value = { ...config.value, dry_run: false };
          await sdk.request(`/plugins/${ID}`, {
            method: "PATCH",
            body: JSON.stringify({ config: config.value }),
          });
          message.value = "封面设置已保存";
        } catch (error) {
          message.value = errorMessage(error, "保存失败");
        } finally {
          busy.value = false;
        }
      }

      async function generate(): Promise<void> {
        await save();
        busy.value = true;
        try {
          await sdk.request(`/plugins/${ID}/run`, { method: "POST", body: "{}" });
          message.value = "封面生成任务已加入后台队列";
        } catch (error) {
          message.value = errorMessage(error, "生成失败");
        } finally {
          busy.value = false;
        }
      }

      const field = (label: string, key: string, type: FieldInputType = "text") => h(
        "label", { class: "cover-field" }, [
          h("span", label),
          h("input", {
            type,
            value: config.value[key] ?? "",
            onInput: (event: Event) => {
              const value = inputTarget(event).value;
              set(key, type === "number" ? Number(value) : value);
            },
          }),
        ],
      );

      onMounted(load);
      return () => h("section", { class: "cover" }, [
        h("style", CSS),
        h("header", { class: "cover-head" }, [
          h("div", [h("h1", "媒体库视觉封面"), h("p", "选择媒体服务器和媒体库，再设置样式；不再要求手工填写服务器 ID。")]),
          h("div", [
            h("button", { class: "alt", onClick: load, disabled: busy.value }, "刷新"),
            " ",
            h("button", { onClick: generate, disabled: busy.value }, busy.value ? "处理中…" : "保存并生成"),
          ]),
        ]),
        h("div", { class: "cover-layout" }, [
          h("aside", { class: "cover-card" }, [
            h("h2", "生成范围"),
            h("div", { class: "cover-list" }, [
              h("label", { class: "cover-field" }, [
                h("span", "媒体服务器"),
                h("select", {
                  value: config.value.selected_servers?.[0] || "",
                  onChange: (event: Event) => chooseServer(selectTarget(event).value),
                }, [h("option", { value: "" }, "请选择"), ...servers.value.map((server) => h("option", { value: server.id }, server.name))]),
              ]),
              ...libraries.value.map((library) => h("label", { class: "cover-row" }, [
                h("input", {
                  type: "checkbox",
                  checked: (config.value.include_libraries || []).includes(library.id),
                  onChange: () => toggle("include_libraries", library.id),
                }),
                h("span", [h("strong", library.name), h("small", library.collection_type || "媒体库")]),
              ])),
            ]),
          ]),
          h("main", { class: "cover-card" }, [
            h("div", { class: "cover-grid" }, [
              h("div", { class: "cover-styles" }, ([
                ["single", "单图"], ["multi", "多图"], ["poster", "海报墙"], ["animated", "动态"],
              ] as const).map(([value, label]) => h("button", {
                class: ["cover-style", config.value.cover_style_base === value && "on"],
                onClick: () => set("cover_style_base", value),
              }, label))),
              h("label", { class: "cover-field" }, [
                h("span", "输出分辨率"),
                h("select", {
                  value: config.value.resolution || "480p",
                  onChange: (event: Event) => set("resolution", selectTarget(event).value),
                }, ["480p", "720p", "1080p", "custom"].map((value) => h("option", { value }, value))),
              ]),
              h("label", { class: "cover-field" }, [
                h("span", "媒体排序"),
                h("select", {
                  value: config.value.sort_by || "DateCreated",
                  onChange: (event: Event) => set("sort_by", selectTarget(event).value),
                }, ([
                  ["DateCreated", "入库时间"], ["PremiereDate", "首映时间"], ["Random", "随机"],
                ] as const).map(([value, label]) => h("option", { value }, label))),
              ]),
              field("中文字号", "zh_font_size", "number"),
              field("英文字号", "en_font_size", "number"),
              h("label", { class: "cover-field full" }, [
                h("span", "媒体库标题配置"),
                h("textarea", {
                  value: config.value.title_config || "",
                  placeholder: "电影=电影|MOVIES",
                  onInput: (event: Event) => set("title_config", textAreaTarget(event).value),
                }),
              ]),
              h("label", { class: "cover-field full" }, [
                h("input", {
                  type: "checkbox",
                  checked: Boolean(config.value.show_item_count),
                  onChange: (event: Event) => set("show_item_count", inputTarget(event).checked),
                }),
                " 显示媒体数量角标",
              ]),
              h("p", { class: "cover-field full" }, message.value),
            ]),
          ]),
        ]),
      ]);
    },
  });
  sdk.registerPage({ pluginId: ID, route: `plugin-${ID}`, title: "视觉封面", icon: "mdi-image-multiple-outline", section: "tools", order: 80, component: Page });
}
