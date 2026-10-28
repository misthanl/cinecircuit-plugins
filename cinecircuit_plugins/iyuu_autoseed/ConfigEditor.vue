<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import type { ConfigField } from "../_shared/config-fields";

const props = defineProps<{
  modelValue: Record<string, unknown>;
  disabled?: boolean;
  fields?: ConfigField[];
  schemaFieldsComponent: Component;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const fields = computed(() => (props.fields || []).filter(field => field.visible !== false && field.key !== "onlyonce"));
const error = ref("");
const restoring = ref(false);
let edited = false;
function update(key: string, value: unknown) {
  if (key === "token") edited = true;
  emit("update:modelValue", {
    ...props.modelValue, [key]: value ?? "",
    ...(key === "token" ? { token_clear: !value } : {}),
  });
}
async function restore() {
  if (edited || props.modelValue.token || restoring.value) return;
  restoring.value = true;
  error.value = "";
  try {
    const result = await props.request<{ value?: string }>("/plugins/iyuu-autoseed/config/secret/token");
    if (!edited) emit("update:modelValue", { ...props.modelValue, token: result.value || "", token_clear: false });
  } catch { error.value = "IYUU Token 读取失败，请重试"; }
  finally { restoring.value = false; }
}
onMounted(restore);
</script>

<template>
  <div class="iyuu-config" autocomplete="off" data-1p-ignore data-lpignore="true">
    <template v-for="field in fields" :key="field.key">
      <VTextField v-if="field.key === 'token'" :model-value="modelValue.token || ''" :label="field.label"
        type="text" autocomplete="off" name="iyuu-access-value" data-1p-ignore data-lpignore="true"
        :disabled="disabled" :error-messages="error" hide-details="auto"
        :append-inner-icon="error ? 'mdi-refresh' : undefined" @click:append-inner="restore"
        @update:model-value="update('token', $event)" />
      <VTextarea v-else-if="field.key === 'nopaths'" :model-value="modelValue.nopaths || ''" :label="field.label"
        :disabled="disabled" :rows="1" :auto-grow="false" :no-resize="false" autocomplete="off" hide-details="auto"
        @update:model-value="update('nopaths', $event)" />
      <component :is="schemaFieldsComponent" v-else :model-value="modelValue" :fields="[field]"
        :disabled="disabled" plugin-id="iyuu-autoseed" :layout="{ columns: 1 }"
        @update:model-value="emit('update:modelValue', $event)" />
    </template>
  </div>
</template>

<style scoped>
.iyuu-config{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px;align-items:start;color:var(--app-text);font-family:var(--app-font-family,inherit);font-size:var(--app-font-size-body,14px)}
.iyuu-config>*{min-width:0}
@media(max-width:700px){.iyuu-config{grid-template-columns:minmax(0,1fr)}}
</style>
