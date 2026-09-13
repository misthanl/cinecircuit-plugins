<script setup lang="ts">
import { computed, type Component } from "vue";
import SavedSecretField from "../_shared/SavedSecretField.vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";

const props = defineProps<{
  modelValue: Record<string, unknown>;
  fields?: ConfigField[];
  disabled?: boolean;
  schemaFieldsComponent: Component;
  request: <T = unknown>(path: string, init?: RequestInit) => Promise<T>;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const top = computed(() => orderedFields(props.fields || [], ["online_providers", "online_use_proxy"]));
const selected = computed(() => {
  const value = props.modelValue.online_providers ?? props.fields?.find(field => field.key === "online_providers")?.default ?? ["subhd", "zimuku"];
  return Array.isArray(value) ? value.map(String) : [];
});
const groups = [
  { key: "subdl", title: "SubDL", fields: ["subdl_api_url", "subdl_api_key"] },
  { key: "shooter", title: "射手影音", fields: ["shooter_api_url"] },
  { key: "xunlei", title: "迅雷看看", fields: ["xunlei_api_url"] },
  { key: "subhd", title: "SubHD", fields: ["subhd_url"] },
  { key: "zimuku", title: "字幕库", fields: ["zimuku_url"] },
  { key: "assrt", title: "ASSRT", fields: ["assrt_api_url", "assrt_api_key", "assrt_search_url"] },
  { key: "opensubtitles", title: "OpenSubtitles", fields: ["opensubtitles_api_url", "opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"] },
];
const visibleGroups = computed(() => groups.filter(group => selected.value.includes(group.key)));
function fieldsFor(keys: string[]) { return orderedFields(props.fields || [], keys); }
function update(next: Record<string, unknown>) {
  emit("update:modelValue", { ...props.modelValue, ...next });
}
</script>

<template>
  <div class="online-source-settings plugin-config-grid app-form-layout">
    <component v-for="field in top" :key="field.key" :is="schemaFieldsComponent"
      :fields="[field]" :model-value="modelValue" :disabled="disabled" compact
      @update:model-value="update" />
    <template v-for="group in visibleGroups" :key="group.key">
      <h3>{{ group.title }}</h3>
      <template v-for="field in fieldsFor(group.fields)" :key="field.key">
        <SavedSecretField v-if="field.secret" :model-value="modelValue[field.key]"
          :disabled="disabled" :label="field.label || field.key" :request="request"
          :endpoint="`/plugins/subtitle-manager/config/secret/${field.key}`"
          @update:model-value="update({ [field.key]: $event, [field.key + '_clear']: false })" />
        <component v-else :is="schemaFieldsComponent" :fields="[field]"
          :model-value="modelValue" :disabled="disabled" compact @update:model-value="update" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.online-source-settings h3{grid-column:1 / -1;margin:0;color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}
</style>
