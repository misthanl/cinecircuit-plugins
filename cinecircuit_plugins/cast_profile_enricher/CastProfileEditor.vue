<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";

const ID = "cast-profile-enricher";
interface ResourceItem { id: string; label: string }
interface ResourceResponse { items?: ResourceItem[] }
type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

const props = defineProps<{
  modelValue: Record<string, unknown>;
  disabled?: boolean;
  request: Requester;
  cronFieldComponent: Component;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const servers = ref<ResourceItem[]>([]);
const loadingServers = ref(false);
const serverError = ref("");
const cronField = {
  key: "cron",
  input_type: "cron",
  label: "执行周期",
  placeholder: "5位cron表达式，留空自动",
};
const selectedServers = computed(() => Array.isArray(props.modelValue.selected_servers)
  ? props.modelValue.selected_servers.map(String)
  : []);
const selectedEvent = computed(() => {
  const value = String(props.modelValue.trigger_event || "").trim();
  return value || null;
});
const serverItems = computed(() => {
  const known = new Set(servers.value.map(item => item.id));
  return [
    ...servers.value,
    ...selectedServers.value.filter(id => !known.has(id)).map(id => ({ id, label: `已失效资源（${id}）` })),
  ];
});

function update(key: string, value: unknown): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
async function loadServers(): Promise<void> {
  loadingServers.value = true;
  serverError.value = "";
  try {
    const data = await props.request<ResourceResponse>(
      `/plugins/${ID}/sdk/resources/media_server?capability=read&capability=write_metadata&limit=100`,
    );
    servers.value = Array.isArray(data.items) ? data.items : [];
  } catch (error) {
    servers.value = [];
    serverError.value = error instanceof Error ? error.message : "媒体服务器读取失败";
  } finally {
    loadingServers.value = false;
  }
}
onMounted(loadServers);
</script>

<template>
  <div class="cast-editor plugin-config-grid app-form-layout">
    <VSwitch label="启用定时生成" :model-value="Boolean(modelValue.enabled)" :disabled="disabled" color="primary" hide-details @update:model-value="update('enabled', $event)" />
    <component :is="cronFieldComponent" :model-value="modelValue.cron || ''" :field="cronField" :disabled="disabled" @update:model-value="update('cron', $event)" />
    <VSelect label="触发事件" :model-value="selectedEvent" :disabled="disabled" :items="[
      { value: 'organizer.completed', title: '整理完成' },
      { value: 'sync.completed', title: '同步完成' },
      { value: 'metadata.scrape.completed', title: '刮削完成' },
    ]" clearable variant="outlined" hide-details @update:model-value="update('trigger_event', $event ?? null)" />
    <VTextField label="触发后延迟执行（秒）" type="number" min="0" max="3600" :model-value="modelValue.scrape_delay ?? 60" :disabled="disabled || !selectedEvent" variant="outlined" hide-details @update:model-value="update('scrape_delay', Number($event))" />
    <VSwitch label="补充人物简介" :model-value="modelValue.update_biography !== false" :disabled="disabled" color="primary" hide-details @update:model-value="update('update_biography', $event)" />
    <VSelect label="处理范围" :model-value="modelValue.condition || 'missing_any'" :disabled="disabled" :items="[
      { value: 'all', title: '全部人物' },
      { value: 'missing_any', title: '姓名或角色未中文化' },
      { value: 'missing_name', title: '姓名未中文化' },
      { value: 'missing_role', title: '角色未中文化' },
    ]" variant="outlined" hide-details @update:model-value="update('condition', $event)" />
    <VSwitch label="移除无法完善的人物" :model-value="Boolean(modelValue.remove_unresolved)" :disabled="disabled" color="primary" hide-details @update:model-value="update('remove_unresolved', $event)" />
    <VSelect class="server-select" label="媒体服务器" :items="serverItems" item-title="label" item-value="id" :model-value="selectedServers" multiple chips closable-chips clearable variant="outlined" hide-details="auto" :loading="loadingServers" :disabled="disabled" :error-messages="serverError || undefined" no-data-text="暂无可用媒体服务器" @update:model-value="update('selected_servers', $event || [])" />
  </div>
</template>

<style scoped>
.cast-editor{display:grid;row-gap:var(--app-plugin-config-row-gap,14px);column-gap:var(--app-plugin-config-column-gap,16px);align-items:start;color:var(--app-text)}.cast-editor :deep(.v-field){border-radius:11px}
</style>
