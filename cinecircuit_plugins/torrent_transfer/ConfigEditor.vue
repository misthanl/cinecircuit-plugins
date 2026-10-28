<script setup lang="ts">
import { computed, ref, type Component } from "vue";
import type { ConfigField } from "../_shared/config-fields";

const props = defineProps<{
  modelValue: Record<string, unknown>;
  disabled?: boolean;
  fields?: ConfigField[];
  schemaFieldsComponent: Component;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const focusedField = ref("");
const fields = computed<ConfigField[]>(() => (props.fields || [])
  .filter(field => field.visible !== false && !["onlyonce", "frompath", "topath"].includes(field.key))
  .map(field => ({ ...field, description: "", description_display: "hidden" })));
function legacyMappings() {
  const lines = (value: unknown) => String(value || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const sources = lines(props.modelValue.frompath), targets = lines(props.modelValue.topath);
  return Array.from({ length: Math.max(sources.length, targets.length) }, (_, index) => `${sources[index] || ""}#${targets[index] || ""}`).join("\n");
}
const form = computed<Record<string, unknown>>(() => ({
  ...props.modelValue,
  fromdownloader: props.modelValue.fromdownloader ?? "",
  todownloader: props.modelValue.todownloader ?? "",
  path_mappings: props.modelValue.path_mappings || legacyMappings(),
}));
function update(key: string, value: unknown) {
  emit("update:modelValue", { ...form.value, [key]: value ?? "", ...(key === "path_mappings" ? { frompath: "", topath: "" } : {}) });
}
function mappingRule(value: unknown): true | string {
  return String(value || "").split(/\r?\n/).every(line => !line.trim() || (line.split("#").length === 2 && line.split("#").every(part => part.trim())))
    || "每行请填写：源目录#目标目录";
}
</script>

<template>
  <div class="torrent-transfer-config">
    <template v-for="field in fields" :key="field.key">
      <VTextarea v-if="field.input_type === 'textarea'" :model-value="form[field.key] ?? ''"
        :label="field.label" :disabled="disabled || field.disabled" :rows="1"
        :placeholder="focusedField === field.key ? String(field.placeholder || '') : undefined"
        :error-messages="field.error || undefined" hide-details="auto"
        :rules="field.key === 'path_mappings' ? [mappingRule] : []"
        @update:focused="focusedField = $event ? field.key : ''"
        @update:model-value="update(field.key, $event)" />
      <component :is="schemaFieldsComponent" v-else :model-value="form" :fields="[field]"
        :disabled="disabled" plugin-id="torrent-transfer" :layout="{ columns: 1 }"
        @update:model-value="emit('update:modelValue', $event)" />
    </template>
  </div>
</template>

<style scoped>
.torrent-transfer-config{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px;align-items:start;color:var(--app-text);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}
.torrent-transfer-config>*{min-width:0}
@media(max-width:700px){.torrent-transfer-config{grid-template-columns:minmax(0,1fr)}}
</style>
