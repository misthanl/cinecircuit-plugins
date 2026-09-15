<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import type { ConfigField } from "../_shared/config-fields";
const props = defineProps<{ modelValue: Record<string, unknown>; fields: ConfigField[]; disabled?: boolean; schemaFieldsComponent: Component; request: <T = unknown>(path: string, init?: RequestInit) => Promise<T> }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const sources = ref<Array<{id: string; capabilities: string[]}>>([]);
const error = ref("");
const supportsEvents = computed(() => sources.value.some(item => item.id === props.modelValue.source && item.capabilities.includes("change_feed")));
const trigger = computed(() => props.modelValue.full_scan_enabled ? "full" : (supportsEvents.value && props.modelValue.life_events_enabled ? "events" : "manual"));
const triggerItems = computed(() => [
  { title: "手动全量", value: "manual" }, { title: "定时全量", value: "full" },
  ...(supportsEvents.value ? [{ title: "生活事件", value: "events" }] : []),
]);
const fieldModel = computed(() => ({ ...props.modelValue, source: props.modelValue.source || null, target: props.modelValue.target || null }));
const field = (key: string) => props.fields.filter(item => item.key === key).map(item => key === "policy" && !String(props.modelValue.temporary_directory || "").trim() ? {...item, options: Array.isArray(item.options) ? item.options.filter(option => option.value === "metadata") : []} : item);
function updateTrigger(value: string) {
  update({ full_scan_enabled: value === "full", life_events_enabled: value === "events" });
}
function update(next: Record<string, unknown>) {
  const merged = { ...props.modelValue, ...next };
  if (!String(merged.temporary_directory || "").trim()) merged.policy = "metadata";
  const sourceChanged = merged.source !== props.modelValue.source;
  if (sourceChanged) merged.source_root = "0";
  if (merged.target !== props.modelValue.target) merged.target_root = "0";
  const supported = sources.value.some(item => item.id === merged.source && item.capabilities.includes("change_feed"));
  if (merged.full_scan_enabled || !supported || sourceChanged) { merged.life_events_enabled = false; merged.life_events_since = 0; }
  if (merged.life_events_enabled && !props.modelValue.life_events_enabled) merged.life_events_since = Math.floor(Date.now() / 1000);
  emit("update:modelValue", merged);
}
onMounted(async () => {
  try { sources.value = (await props.request<{items: Array<{id:string;capabilities:string[]}>}>("/plugins/cloud-copy/sdk/resources/storage?capability=file_copy_source&limit=500")).items; }
  catch { error.value = "读取源网盘能力失败，请重新打开配置"; }
});
</script>
<template>
  <div class="copy-config plugin-config-grid app-form-layout">
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="copy-config-sidebar">
      <component :is="schemaFieldsComponent" :fields="field('show_sidebar_nav')" :model-value="fieldModel" :disabled="disabled" plugin-id="cloud-copy" compact @update:model-value="update" />
    </div>
    <component :is="schemaFieldsComponent" v-for="key in ['source', 'source_root', 'target', 'target_root']" :key="key" :fields="field(key)" :model-value="fieldModel" :disabled="disabled" plugin-id="cloud-copy" compact @update:model-value="update" />
    <div class="copy-config-trigger">
      <VSelect :model-value="trigger" :items="triggerItems" label="触发方式" variant="outlined" :disabled="disabled" @update:model-value="updateTrigger" />
      <VTextField v-if="modelValue.full_scan_enabled" :model-value="modelValue.full_scan_interval_minutes ?? 60" label="全量执行间隔（分钟）" type="number" min="1" step="1" variant="outlined" :disabled="disabled" :rules="[(value: string) => Number.isInteger(Number(value)) && Number(value) > 0 || '请输入大于 0 的整数分钟']" @update:model-value="update({full_scan_interval_minutes: $event === '' ? '' : Number($event)})" />
    </div>
    <component :is="schemaFieldsComponent" v-for="key in ['policy', 'temporary_directory', 'max_gib', 'followup']" :key="key" :fields="field(key)" :model-value="fieldModel" :disabled="disabled" plugin-id="cloud-copy" compact @update:model-value="update" />
  </div>
</template>
<style scoped>
.copy-config{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px}
.copy-config-sidebar,.copy-config>p{grid-column:1/-1}
.copy-config-trigger{display:contents}
.copy-config>p{color:var(--app-danger-text)}
@media(max-width:600px){.copy-config{grid-template-columns:1fr}}
</style>
