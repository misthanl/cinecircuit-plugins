import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";

const PLUGIN_ID = "brush-flow";
const CSS = `
.brush{display:grid;gap:18px;color:var(--app-text,#17243a)}.brush *{box-sizing:border-box}.brush-head,.brush-panel{border:1px solid var(--app-border,#dfe6f0);border-radius:22px;background:var(--app-surface,#fff);box-shadow:0 14px 36px rgba(38,60,94,.06)}.brush-head{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:22px 24px}.brush h1,.brush h2{margin:0}.brush p{margin:5px 0 0;color:var(--app-text-muted,#71809a)}.brush-actions{display:flex;gap:9px}.brush button{min-height:40px;padding:0 15px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.brush button.ghost{background:#edf3ff;color:#245fc4}.brush button.warn{background:#fff1dc;color:#a86100}.brush button:disabled{opacity:.5}.brush-layout{display:grid;grid-template-columns:minmax(240px,.65fr) minmax(0,1.45fr);gap:16px}.brush-panel{padding:20px}.brush-list{display:grid;gap:9px;margin-top:15px}.brush-task{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:13px;border:1px solid var(--app-border,#dfe6f0);border-radius:14px;background:#f8fafc;cursor:pointer}.brush-task.on{border-color:#82adff;background:#f1f6ff}.brush-task strong,.brush-task small{display:block}.brush-task small{margin-top:4px;color:#7c899d}.brush-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.brush-field{display:grid;gap:6px}.brush-field.full{grid-column:1/-1}.brush-field span{font-size:13px;font-weight:700;color:#5e6d84}.brush-field input,.brush-field select{width:100%;min-height:42px;padding:0 12px;border:1px solid #d6deea;border-radius:11px;background:#fff}.brush-check{display:flex;gap:8px;align-items:center;min-height:42px}.brush-preview{grid-column:1/-1;display:grid;gap:7px;padding-top:13px;border-top:1px solid #e3e8f1}.brush-preview div{padding:9px 11px;border-radius:10px;background:#f5f8fc;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.brush-empty{padding:30px;text-align:center;color:#8290a5}@media(max-width:800px){.brush-layout{grid-template-columns:1fr}.brush-form{grid-template-columns:1fr}.brush-field.full{grid-column:auto}.brush-head{align-items:stretch;flex-direction:column}.brush-actions{display:grid}}
`;

interface SelectableItem { id: string; name: string }
interface PreviewItem { title: string }
interface TrafficTask {
  id: string;
  name: string;
  enabled: boolean;
  site_id: string;
  downloader_id: string;
  include: string;
  exclude: string;
  min_size: number;
  max_size: number;
  max_add: number;
  save_path: string;
  delete_ratio: number;
  delete_seed_hours: number;
  delete_task: boolean;
}
interface InventoryResponse {
  sites?: SelectableItem[];
  downloaders?: SelectableItem[];
  config?: Record<string, unknown>;
  tasks?: TrafficTask[];
}
interface RunResponse { items?: PreviewItem[]; count?: number; added?: number }
type TaskField = keyof TrafficTask;
type InputType = "text" | "number";
type RunAction = "run" | "preview";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
function inputTarget(event: Event): HTMLInputElement {
  return event.target as HTMLInputElement;
}
function selectTarget(event: Event): HTMLSelectElement {
  return event.target as HTMLSelectElement;
}

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h, onMounted, ref } = sdk.vue;
  const Page = defineComponent({
    name: "SiteTrafficPage",
    setup() {
      const sites = ref<SelectableItem[]>([]);
      const downloaders = ref<SelectableItem[]>([]);
      const tasks = ref<TrafficTask[]>([]);
      const config = ref<Record<string, unknown>>({});
      const selected = ref<TrafficTask | null>(null);
      const preview = ref<PreviewItem[]>([]);
      const message = ref("");
      const busy = ref(false);

      async function load(): Promise<void> {
        busy.value = true;
        try {
          const data = await sdk.request<InventoryResponse>(`/plugins/${PLUGIN_ID}/api/inventory`);
          sites.value = data.sites || [];
          downloaders.value = data.downloaders || [];
          config.value = data.config || {};
          tasks.value = data.tasks || [];
          selected.value = tasks.value.find((task) => task.id === selected.value?.id) || tasks.value[0] || null;
        } catch (error) {
          message.value = errorMessage(error, "读取失败");
        } finally {
          busy.value = false;
        }
      }

      function add(): void {
        const task: TrafficTask = {
          id: `task-${Date.now()}`, name: "新刷流任务", enabled: true,
          site_id: sites.value[0]?.id || "", downloader_id: downloaders.value[0]?.id || "",
          include: "", exclude: "", min_size: 0, max_size: 0, max_add: 3,
          save_path: "", delete_ratio: 0, delete_seed_hours: 0, delete_task: false,
        };
        tasks.value = [...tasks.value, task];
        selected.value = task;
      }

      function field(key: TaskField, value: TrafficTask[TaskField]): void {
        if (!selected.value) return;
        const updated = { ...selected.value, [key]: value } as TrafficTask;
        selected.value = updated;
        tasks.value = tasks.value.map((task) => task.id === updated.id ? updated : task);
      }

      async function save(): Promise<void> {
        busy.value = true;
        try {
          await sdk.request(`/plugins/${PLUGIN_ID}`, {
            method: "PATCH",
            body: JSON.stringify({ config: { ...config.value, tasks: tasks.value } }),
          });
          config.value = { ...config.value, tasks: tasks.value };
          message.value = "刷流任务已保存";
        } catch (error) {
          message.value = errorMessage(error, "保存失败");
        } finally {
          busy.value = false;
        }
      }

      async function run(action: RunAction = "run"): Promise<void> {
        if (!selected.value) return;
        busy.value = true;
        try {
          const data = await sdk.request<RunResponse>(`/plugins/${PLUGIN_ID}/api/${action}`, {
            method: "POST",
            body: JSON.stringify({ task_id: selected.value.id, ...selected.value }),
          });
          if (action === "preview") preview.value = data.items || [];
          message.value = action === "preview"
            ? `匹配 ${data.count || 0} 个候选`
            : `已添加 ${data.added || 0} 个任务`;
        } catch (error) {
          message.value = errorMessage(error, "执行失败");
        } finally {
          busy.value = false;
        }
      }

      const input = (label: string, key: TaskField, type: InputType = "text", full = false) => h(
        "label", { class: ["brush-field", full && "full"] }, [
          h("span", label),
          h("input", {
            type,
            value: selected.value?.[key] ?? "",
            onInput: (event: Event) => {
              const value = inputTarget(event).value;
              field(key, type === "number" ? Number(value) : value);
            },
          }),
        ],
      );
      const select = (label: string, key: TaskField, items: SelectableItem[]) => h(
        "label", { class: "brush-field" }, [
          h("span", label),
          h("select", {
            value: selected.value?.[key] || "",
            onChange: (event: Event) => field(key, selectTarget(event).value),
          }, items.map((item) => h("option", { value: item.id }, item.name))),
        ],
      );

      onMounted(load);
      return () => h("section", { class: "brush" }, [
        h("style", CSS),
        h("header", { class: "brush-head" }, [
          h("div", [h("h1", "站点刷流"), h("p", "任务、选种、下载和删种规则集中在同一个工作台。")]),
          h("div", { class: "brush-actions" }, [
            h("button", { class: "ghost", onClick: load, disabled: busy.value }, "刷新"),
            h("button", { onClick: save, disabled: busy.value }, "保存全部"),
          ]),
        ]),
        h("div", { class: "brush-layout" }, [
          h("aside", { class: "brush-panel" }, [
            h("div", { class: "brush-actions" }, [h("h2", "流量任务"), h("button", { class: "ghost", onClick: add }, "新增")]),
            h("div", { class: "brush-list" }, tasks.value.length
              ? tasks.value.map((task) => h("article", {
                class: ["brush-task", selected.value?.id === task.id && "on"],
                onClick: () => { selected.value = task; },
              }, [
                h("div", [h("strong", task.name), h("small", sites.value.find((site) => site.id === task.site_id)?.name || "未选择站点")]),
                h("span", task.enabled ? "启用" : "停用"),
              ]))
              : h("div", { class: "brush-empty" }, "还没有流量任务")),
          ]),
          h("main", { class: "brush-panel" }, selected.value
            ? h("div", { class: "brush-form" }, [
              input("任务名称", "name", "text", true), select("PT 站点", "site_id", sites.value),
              select("下载器", "downloader_id", downloaders.value), input("包含规则（正则）", "include"),
              input("排除规则（正则）", "exclude"), input("最小体积 GiB", "min_size", "number"),
              input("最大体积 GiB", "max_size", "number"), input("单次最多添加", "max_add", "number"),
              input("保存目录", "save_path"), input("分享率达到后处理", "delete_ratio", "number"),
              input("做种小时达到后处理", "delete_seed_hours", "number"),
              h("label", { class: "brush-check" }, [h("input", { type: "checkbox", checked: selected.value.enabled, onChange: (event: Event) => field("enabled", inputTarget(event).checked) }), "启用任务"]),
              h("label", { class: "brush-check" }, [h("input", { type: "checkbox", checked: selected.value.delete_task, onChange: (event: Event) => field("delete_task", inputTarget(event).checked) }), "条件满足时删种（否则暂停）"]),
              h("div", { class: "brush-actions brush-field full" }, [
                h("button", { class: "ghost", onClick: () => run("preview"), disabled: busy.value }, "预览选种"),
                h("button", { onClick: () => run("run"), disabled: busy.value }, "立即执行"),
              ]),
              preview.value.length ? h("div", { class: "brush-preview" }, preview.value.slice(0, 10).map((item) => h("div", item.title))) : null,
              h("p", { class: "brush-field full" }, message.value),
            ])
            : h("div", { class: "brush-empty" }, "选择或新建一个任务")),
        ]),
      ]);
    },
  });
  sdk.registerPage({ pluginId: PLUGIN_ID, route: `plugin-${PLUGIN_ID}`, title: "站点刷流", icon: "mdi-water-sync", section: "tools", order: 74, component: Page });
}
