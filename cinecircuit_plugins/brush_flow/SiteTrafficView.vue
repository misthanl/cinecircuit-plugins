<script setup lang="ts">
import { onMounted, ref } from "vue";

const PLUGIN_ID = "brush-flow";
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
interface InventoryResponse { sites?: SelectableItem[]; downloaders?: SelectableItem[]; config?: Record<string, unknown>; tasks?: TrafficTask[] }
interface RunResponse { items?: PreviewItem[]; count?: number; added?: number }
type TaskField = keyof TrafficTask;
type RunAction = "run" | "preview";
type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

const props = defineProps<{ request: Requester }>();
const sites = ref<SelectableItem[]>([]);
const downloaders = ref<SelectableItem[]>([]);
const tasks = ref<TrafficTask[]>([]);
const config = ref<Record<string, unknown>>({});
const selected = ref<TrafficTask | null>(null);
const preview = ref<PreviewItem[]>([]);
const message = ref("");
const busy = ref(false);

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
async function load(): Promise<void> {
  busy.value = true;
  try {
    const data = await props.request<InventoryResponse>(`/plugins/${PLUGIN_ID}/api/inventory`);
    sites.value = data.sites || [];
    downloaders.value = data.downloaders || [];
    config.value = data.config || {};
    tasks.value = data.tasks || [];
    selected.value = tasks.value.find(task => task.id === selected.value?.id) || tasks.value[0] || null;
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
  tasks.value = tasks.value.map(task => task.id === updated.id ? updated : task);
}
function inputField(key: TaskField, event: Event, numeric = false): void {
  const value = (event.target as HTMLInputElement).value;
  field(key, numeric ? Number(value) : value);
}
async function save(): Promise<void> {
  busy.value = true;
  try {
    await props.request(`/plugins/${PLUGIN_ID}`, { method: "PATCH", body: JSON.stringify({ config: { ...config.value, tasks: tasks.value } }) });
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
    const data = await props.request<RunResponse>(`/plugins/${PLUGIN_ID}/api/${action}`, { method: "POST", body: JSON.stringify({ task_id: selected.value.id, ...selected.value }) });
    if (action === "preview") preview.value = data.items || [];
    message.value = action === "preview" ? `匹配 ${data.count || 0} 个候选` : `已添加 ${data.added || 0} 个任务`;
  } catch (error) {
    message.value = errorMessage(error, "执行失败");
  } finally {
    busy.value = false;
  }
}
function siteName(task: TrafficTask): string {
  return sites.value.find(site => site.id === task.site_id)?.name || "未选择站点";
}

onMounted(load);
</script>

<template>
  <section class="brush">
    <header class="brush-head">
      <div><h1>站点刷流</h1><p>任务、选种、下载和删种规则集中在同一个工作台。</p></div>
      <div class="brush-actions"><button class="ghost" :disabled="busy" @click="load">刷新</button><button :disabled="busy" @click="save">保存全部</button></div>
    </header>
    <div class="brush-layout">
      <aside class="brush-panel">
        <div class="brush-actions"><h2>流量任务</h2><button class="ghost" @click="add">新增</button></div>
        <div class="brush-list">
          <template v-if="tasks.length">
            <article v-for="task in tasks" :key="task.id" class="brush-task" :class="{ on: selected?.id === task.id }" @click="selected = task">
              <div><strong>{{ task.name }}</strong><small>{{ siteName(task) }}</small></div><span>{{ task.enabled ? "启用" : "停用" }}</span>
            </article>
          </template>
          <div v-else class="brush-empty">还没有流量任务</div>
        </div>
      </aside>
      <main class="brush-panel">
        <div v-if="selected" class="brush-form">
          <label class="brush-field full"><span>任务名称</span><input :value="selected.name" @input="inputField('name', $event)"></label>
          <div class="brush-field"><VSelect label="PT 站点" :model-value="selected.site_id" @update:model-value="field('site_id', $event)" :items="sites.map(item => ({value:item.id,title:item.name}))" variant="outlined" density="comfortable" hide-details /></div>
          <div class="brush-field"><VSelect label="下载器" :model-value="selected.downloader_id" @update:model-value="field('downloader_id', $event)" :items="downloaders.map(item => ({value:item.id,title:item.name}))" variant="outlined" density="comfortable" hide-details /></div>
          <label class="brush-field"><span>包含规则（正则）</span><input :value="selected.include" @input="inputField('include', $event)"></label>
          <label class="brush-field"><span>排除规则（正则）</span><input :value="selected.exclude" @input="inputField('exclude', $event)"></label>
          <label class="brush-field"><span>最小体积 GiB</span><input type="number" :value="selected.min_size" @input="inputField('min_size', $event, true)"></label>
          <label class="brush-field"><span>最大体积 GiB</span><input type="number" :value="selected.max_size" @input="inputField('max_size', $event, true)"></label>
          <label class="brush-field"><span>单次最多添加</span><input type="number" :value="selected.max_add" @input="inputField('max_add', $event, true)"></label>
          <label class="brush-field"><span>保存目录</span><input :value="selected.save_path" @input="inputField('save_path', $event)"></label>
          <label class="brush-field"><span>分享率达到后处理</span><input type="number" :value="selected.delete_ratio" @input="inputField('delete_ratio', $event, true)"></label>
          <label class="brush-field"><span>做种小时达到后处理</span><input type="number" :value="selected.delete_seed_hours" @input="inputField('delete_seed_hours', $event, true)"></label>
          <label class="brush-check"><input type="checkbox" :checked="selected.enabled" @change="field('enabled', ($event.target as HTMLInputElement).checked)">启用任务</label>
          <label class="brush-check"><input type="checkbox" :checked="selected.delete_task" @change="field('delete_task', ($event.target as HTMLInputElement).checked)">条件满足时删种（否则暂停）</label>
          <div class="brush-actions brush-field full"><button class="ghost" :disabled="busy" @click="run('preview')">预览选种</button><button :disabled="busy" @click="run('run')">立即执行</button></div>
          <div v-if="preview.length" class="brush-preview"><div v-for="item in preview.slice(0, 10)" :key="item.title">{{ item.title }}</div></div>
          <p class="brush-field full">{{ message }}</p>
        </div>
        <div v-else class="brush-empty">选择或新建一个任务</div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.brush{display:grid;gap:18px;color:var(--app-text,#17243a)}.brush *{box-sizing:border-box}.brush-head,.brush-panel{border:1px solid var(--app-border,#dfe6f0);border-radius:22px;background:var(--app-surface,#fff);box-shadow:0 14px 36px rgba(38,60,94,.06)}.brush-head{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:22px 24px}.brush h1,.brush h2{margin:0}.brush p{margin:5px 0 0;color:var(--app-text-muted,#71809a)}.brush-actions{display:flex;gap:9px}.brush button{min-height:40px;padding:0 15px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.brush button.ghost{background:#edf3ff;color:#245fc4}.brush button.warn{background:#fff1dc;color:#a86100}.brush button:disabled{opacity:.5}.brush-layout{display:grid;grid-template-columns:minmax(240px,.65fr) minmax(0,1.45fr);gap:16px}.brush-panel{padding:20px}.brush-list{display:grid;gap:9px;margin-top:15px}.brush-task{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:13px;border:1px solid var(--app-border,#dfe6f0);border-radius:14px;background:#f8fafc;cursor:pointer}.brush-task.on{border-color:#82adff;background:#f1f6ff}.brush-task strong,.brush-task small{display:block}.brush-task small{margin-top:4px;color:#7c899d}.brush-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.brush-field{display:grid;gap:6px}.brush-field.full{grid-column:1/-1}.brush-field span{font-size:13px;font-weight:700;color:#5e6d84}.brush-field input,.brush-field select{width:100%;min-height:42px;padding:0 12px;border:1px solid #d6deea;border-radius:11px;background:#fff}.brush-check{display:flex;gap:8px;align-items:center;min-height:42px}.brush-preview{grid-column:1/-1;display:grid;gap:7px;padding-top:13px;border-top:1px solid #e3e8f1}.brush-preview div{padding:9px 11px;border-radius:10px;background:#f5f8fc;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.brush-empty{padding:30px;text-align:center;color:#8290a5}@media(max-width:800px){.brush-layout{grid-template-columns:1fr}.brush-form{grid-template-columns:1fr}.brush-field.full{grid-column:auto}.brush-head{align-items:stretch;flex-direction:column}.brush-actions{display:grid}}
</style>
