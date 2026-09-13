<script setup lang="ts">
import { computed, ref, type Component } from "vue";
import { basicFields, limitFields, executionFields, selectionFields, deletionFields } from "./task-fields";
import { validCron, validRange, validIntakeTime } from "./task-validation";
interface Resource { id: string; name: string; enabled?: boolean; capabilities?: string[] }
type Task = Record<string, unknown>;
const props = defineProps<{ task: Task; isNew: boolean; sites: Resource[]; downloaders: Resource[];
  disabled?: boolean; loading?: boolean; schemaFieldsComponent: Component }>();
const emit = defineEmits<{ save: [task: Task]; close: [] }>();
const draft = ref<Task>({ check_interval_minutes: 5, cleanup_enabled: true, allow_delete_files: true, delete_task: true, ...props.task });
const error = ref("");
const section = ref("basic");
const siteOptions = computed(() => props.sites.map(site => {
  const unavailable = site.enabled === false || (site.capabilities && !site.capabilities.some(value => ["latest", "feed"].includes(value)));
  return { value: site.id, title: site.name + (unavailable ? "（请检查站点适配和凭据）" : ""), props: { disabled: !!unavailable } };
}));
const downloaderOptions = computed(() => props.downloaders.map(item => ({ value: item.id, title: item.name, props: { disabled: item.enabled === false } })));
function update(value: Task): void { if (!props.disabled) draft.value = { ...draft.value, ...value }; }
function validLimits(keys: string[]): boolean {
  return keys.every(key => {
    const value = Number(draft.value[key]);
    return Number.isInteger(value) && value >= (key === "task_limit" ? 0 : 1);
  });
}
function validateLimits(): boolean {
  if (!validLimits(["interval_minutes", "check_interval_minutes"])) {
    error.value = "刷新周期和状态检查周期须为大于 0 的整数。"; section.value = "basic"; return false;
  }
  if (!validLimits(["max_add", "task_limit"])) {
    error.value = "每次添加数量须为大于 0 的整数，任务上限须为非负整数。"; section.value = "limits"; return false;
  }
  const speeds = ["upload_limit_kib", "download_limit_kib"].map(key => Number(draft.value[key] || 0));
  const volume = Number(draft.value.seeding_limit_gib || 0);
  if (speeds.some(value => !Number.isInteger(value) || value < 0 || value > 2097151) || !Number.isFinite(volume) || volume < 0) {
    error.value = "限速须为非负整数，保种总体积须为非负数；0 表示不限。"; section.value = "limits"; return false;
  }
  return true;
}
function validatePatterns(): void {
  for (const key of ["include", "exclude"]) {
    if (draft.value[key]) new RegExp(String(draft.value[key]));
  }
}
function save(): void {
  if (props.disabled) return;
  if (!["size_range", "seeders_range", "publish_range"].every(key => validRange(draft.value[key]))) {
    error.value = "范围请填写非负单值或最小值-最大值，例如 0-100。"; section.value = "selection"; return;
  }
  if (!String(draft.value.name || "").trim() || !draft.value.site_id) {
    error.value = "请填写任务名称并选择 PT 站点。"; section.value = "basic"; return;
  }
  if (!validateLimits()) return;
  if (!validIntakeTime(draft.value.intake_time_range)) {
    error.value = "进种时间段请填写 00:00-08:00 格式，起止不能相同；留空表示全天。"; section.value = "basic"; return;
  }
  if (!validCron(draft.value.cron)) {
    error.value = "请填写有效的 5 位 Cron 表达式，或留空使用执行间隔。"; section.value = "basic"; return;
  }
  try { validatePatterns(); }
  catch { error.value = "请检查选种规则中的正则表达式。"; section.value = "selection"; return; }
  emit("save", { ...draft.value, name: String(draft.value.name).trim() });
}
</script>
<template>
  <VDialog :model-value="true" max-width="640" scrollable @update:model-value="!$event && emit('close')">
    <VCard class="traffic-dialog">
      <header class="traffic-dialog-heading"><div><h2>{{ isNew ? '添加任务' : '编辑任务' }}</h2></div><VBtn class="app-dialog-close" icon="mdi-close" variant="text" aria-label="关闭任务编辑" @click="emit('close')" /></header>
      <VTabs v-model="section" color="primary" class="traffic-dialog-tabs app-section-tabs app-section-tabs--line" show-arrows><VTab value="basic">基本设置</VTab><VTab value="limits">任务限制</VTab><VTab value="selection">选种规则</VTab><VTab value="deletion">删种规则</VTab></VTabs>
      <VCardText class="traffic-dialog-body">
        <p v-if="error" role="alert" class="traffic-dialog-error">{{ error }}</p>
        <section v-if="section === 'basic'" class="traffic-dialog-section">
          <component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="basicFields.slice(0, 2)" :model-value="draft" :disabled="disabled" compact @update:model-value="update" />
          <component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="basicFields.slice(2)" :model-value="draft" :disabled="disabled" compact @update:model-value="update" />
          <div class="traffic-resource-grid plugin-config-grid app-form-layout"><VSelect label="任务 PT 站点" :items="siteOptions" :model-value="draft.site_id || null" :disabled="disabled || loading" variant="outlined" density="comfortable" @update:model-value="update({ site_id: $event || '' })" />
            <VSelect label="任务下载器" :items="downloaderOptions" :model-value="draft.downloader_id || null" :disabled="disabled || loading" clearable variant="outlined" density="comfortable" @update:model-value="update({ downloader_id: $event || '' })" /></div>
          <component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="executionFields" :model-value="draft" :disabled="disabled" compact @update:model-value="update" />
        </section>
        <section v-if="section === 'limits'" class="traffic-dialog-section"><component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="limitFields" :model-value="draft" :disabled="disabled" compact @update:model-value="update" /><p>0 表示不限。保种体积包含下载中和已完成的本任务种子；限速用于新添加的种子。</p></section>
        <section v-if="section === 'selection'" class="traffic-dialog-section"><component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="selectionFields" :model-value="draft" :disabled="disabled" compact @update:model-value="update" /></section>
        <section v-if="section === 'deletion'" class="traffic-dialog-section">
          <component :is="schemaFieldsComponent" class="standard-config-fields plugin-config-grid app-form-layout" :layout="{ columns: 2, row_gap: 14, column_gap: 16 }" :fields="deletionFields" :model-value="draft" :disabled="disabled" compact @update:model-value="update" /></section>
      </VCardText>
      <VCardActions class="traffic-dialog-actions"><VBtn class="app-action-button" color="primary" variant="flat" :disabled="disabled" @click="save">{{ isNew ? '添加任务' : '确认修改' }}</VBtn></VCardActions>
    </VCard>
  </VDialog>
</template>
<style scoped>
.traffic-dialog{max-height:min(560px,calc(100dvh - 48px))}
.traffic-dialog-heading{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;border-bottom:1px solid var(--app-border-subtle,#e7ebf2)}
.traffic-dialog-heading h2{margin:0}
.traffic-dialog-tabs{padding:0 16px;border-bottom:1px solid var(--app-border-subtle,#e7ebf2);flex-shrink:0}
.traffic-dialog-body{padding:16px!important;min-height:0}
.traffic-dialog-section{display:grid;gap:10px}
.traffic-resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px}
.traffic-dialog-actions{gap:8px;flex-wrap:wrap;justify-content:flex-end}
.traffic-dialog-error{color:rgb(var(--v-theme-error));font-size:13px}
@media(max-width:560px){.traffic-resource-grid{grid-template-columns:1fr}}
</style>
