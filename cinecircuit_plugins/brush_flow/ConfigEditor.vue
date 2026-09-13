<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";
import TaskDialog from "./TaskDialog.vue";
import TaskCard from "./TaskCard.vue";
import { newTaskId } from "./task-id";
interface Resource { id: string; name: string; enabled?: boolean; capabilities?: string[] }
type Task = Record<string, unknown>;
const props = defineProps<{ modelValue: Task; fields?: ConfigField[]; disabled?: boolean; schemaFieldsComponent: Component; request: <T>(path: string, init?: RequestInit) => Promise<T> }>();
const emit = defineEmits<{ "update:modelValue": [value: Task] }>();
const sites = ref<Resource[]>([]), downloaders = ref<Resource[]>([]);
const loading = ref(false), error = ref("");
const editing = ref<Task | null>(null), editingIndex = ref(-1);
const tasks = computed(() => Array.isArray(props.modelValue.tasks) ? props.modelValue.tasks as Task[] : []);
const globalFields = computed(() => orderedFields(props.fields || [], ["enabled", "max_tasks"]).map(field => field.key === "max_tasks" ? { ...field, label: "全局下载任务上限" } : field));
function resolved(task: Task): Task {
  return { exclude_tags: "CineCircuit,H&R", promotion: "free", exclude_hr: true,
    notification_enabled: props.modelValue.notification_enabled ?? false, cron: props.modelValue.cron || "", interval_minutes: 10, task_limit: 0, max_add: 3, cleanup_enabled: true, allow_delete_files: true, delete_task: true, ...task,
    site_id: task.site_id || props.modelValue.default_site_id || "", downloader_id: task.downloader_id || props.modelValue.default_downloader_id || "" };
}
function editTask(index = -1): void {
  if (props.disabled) return;
  editingIndex.value = index;
  editing.value = index >= 0 ? resolved(tasks.value[index]) : {
    exclude_tags: "CineCircuit,H&R", promotion: "free", exclude_hr: true, id: newTaskId(), name: "", enabled: true, site_id: "", downloader_id: "",
    max_add: 3, interval_minutes: 10, cron: "", task_limit: 0, cleanup_enabled: true, notification_enabled: false, allow_delete_files: true, delete_task: true,
  };
}
function saveTask(task: Task): void {
  if (props.disabled) return;
  const next = tasks.value.map(resolved);
  if (editingIndex.value < 0) next.push(task); else next[editingIndex.value] = task;
  emit("update:modelValue", { ...props.modelValue, tasks: next });
  editing.value = null;
}
function removeTask(index: number): void {
  if (!props.disabled) emit("update:modelValue", { ...props.modelValue, tasks: tasks.value.filter((_, i) => i !== index) });
}
function resourceName(resources: Resource[], id: unknown, empty: string): string {
  return resources.find(row => row.id === id)?.name || (id ? "资源不可用" : empty);
}
function cadence(task: Task): string {
  const value = resolved(task);
  return value.cron ? `Cron ${value.cron}` : `每 ${value.interval_minutes || 10} 分钟`;
}
async function loadResources(): Promise<void> {
  loading.value = true; error.value = "";
  try {
    const result = await props.request<{ sites?: Resource[]; downloaders?: Resource[]; tasks?: Task[] }>("/plugins/brush-flow/api/inventory");
    sites.value = result.sites || []; downloaders.value = result.downloaders || [];
    // The inventory is the authoritative persisted task source. The plugin card's
    // cached config can still be stale when its dialog is closed and immediately
    // reopened, so restore the task list from the backend on every fresh mount.
    if (Array.isArray(result.tasks)) {
      emit("update:modelValue", { ...props.modelValue, tasks: result.tasks });
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "读取站点与下载器失败"; }
  finally { loading.value = false; }
}
onMounted(loadResources);
</script>
<template>
  <div class="traffic-config app-form-layout">
    <header class="global-heading"><h3>全局控制</h3><p>统一控制刷流任务的运行状态和下载数量。</p></header>
    <component :is="schemaFieldsComponent" class="global-config-fields standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 16, column_gap: 20 }" :fields="globalFields" :model-value="modelValue" :disabled="disabled" compact @update:model-value="emit('update:modelValue', $event)" />
    <div class="traffic-heading"><div><h3>刷流任务 <span>{{ tasks.length }}</span></h3><p>任务调整后，使用页面底部的保存按钮应用更改。</p></div>
      <VBtn class="app-action-button" color="primary" variant="flat" :disabled="disabled" @click="editTask()">添加任务</VBtn></div>
    <div v-if="error" class="traffic-error" role="alert"><span>{{ error }}</span><VBtn variant="text" :loading="loading" @click="loadResources">重试</VBtn></div>
    <div v-if="!tasks.length" class="traffic-empty"><VIcon icon="mdi-swap-vertical" size="32"/><h4>创建第一个刷流任务</h4><p>选择 PT 站点和下载器，设置选种与删种规则。</p>
      <p v-if="!loading && !sites.length && !error">没有已配置的 PT 站点，请先在站点管理中添加。</p></div>
    <div class="traffic-tasks">
      <TaskCard v-for="(task, index) in tasks" :key="String(task.id || index)" :task="resolved(task)"
        :site-name="resourceName(sites, resolved(task).site_id, '未选择站点')"
        :downloader-name="resourceName(downloaders, resolved(task).downloader_id, '当前默认下载器')"
        :cadence="cadence(task)" :global-limit="Number(modelValue.max_tasks || 30)" :disabled="disabled"
        @edit="editTask(index)" @remove="removeTask(index)" />
    </div>
    <TaskDialog v-if="editing" :task="editing" :is-new="editingIndex < 0" :sites="sites" :downloaders="downloaders" :disabled="disabled" :loading="loading" :schema-fields-component="schemaFieldsComponent" @save="saveTask" @close="editing = null" />
  </div>
</template>
<style scoped>
.traffic-config{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;grid-column:1/-1;min-width:0}
.traffic-config h3,.traffic-config h4,.traffic-config p{margin:0}
.traffic-config h3,.traffic-config h4{color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600);overflow-wrap:anywhere}
.traffic-config p{font-size:var(--app-font-size-helper,12px);line-height:1.5;color:var(--app-text-muted,#7a869d)}
.global-heading{display:grid;gap:5px;min-width:0}
.global-config-fields:deep(> .v-input){min-width:0}
.traffic-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:16px;border-top:1px solid var(--app-border-subtle,#e7ebf2)}
.traffic-heading h3 span{font-size:12px;margin-left:8px;color:var(--app-text-muted,#7a869d);font-weight:400}
.traffic-empty{text-align:center;padding:28px 16px;border:1px solid var(--app-border-subtle,#e7ebf2);border-radius:12px}
.traffic-empty h4{margin:10px 0 4px}.traffic-empty .v-icon{color:var(--app-text-muted,#7a869d)}
.traffic-tasks{display:grid;gap:12px}
.traffic-task{border:1px solid var(--app-border-subtle,#e7ebf2);border-radius:12px;padding:15px 16px;min-width:0;background:var(--app-surface,#fff)}
.traffic-task header,.traffic-task footer{display:flex;align-items:center;justify-content:space-between;gap:12px}
.traffic-status{white-space:nowrap;font-size:12px;color:var(--app-text-secondary,#657087)}
.paused .traffic-status{color:var(--app-text-muted,#7a869d)}
.traffic-route{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0;color:var(--app-text-secondary,#657087);font-size:var(--app-font-size-body,14px)}
.traffic-route span:nth-child(2){color:var(--app-text-muted,#7a869d)}
.traffic-task dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;margin:0 0 12px}
.traffic-task dt{font-size:12px;color:var(--app-text-muted,#7a869d)}
.traffic-task dd{margin:4px 0 0;font-size:var(--app-font-size-body,14px);overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.traffic-rule{overflow-wrap:anywhere}
.traffic-task footer{margin-top:12px;padding-top:12px;border-top:1px solid var(--app-border-subtle,#e7ebf2);font-size:12px;color:var(--app-text-muted,#7a869d)}
.traffic-error{display:flex;align-items:center;gap:8px;color:rgb(var(--v-theme-error));font-size:13px;line-height:1.5}
.traffic-error>span{min-width:0;overflow-wrap:anywhere}
.traffic-error:deep(> .v-btn){flex:0 0 auto;align-self:center;margin:0}
@media(max-width:480px){.traffic-heading{align-items:flex-start}.traffic-task footer{align-items:flex-start;flex-wrap:wrap}}
</style>

