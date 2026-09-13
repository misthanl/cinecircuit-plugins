<script setup lang="ts">
import { computed, type Component } from "vue";
import SavedSecretField from "../_shared/SavedSecretField.vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";

const props = defineProps<{
  modelValue: Record<string, unknown>;
  disabled?: boolean;
  fields?: ConfigField[];
  schemaFieldsComponent: Component;
  request: <T = unknown>(path: string, init?: RequestInit) => Promise<T>;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const top = computed(() => orderedFields(props.fields || [], ["enabled", "cron", "storage_id"]));
const bottom = computed(() => orderedFields(props.fields || [], ["confirm_permanent", "notification_enabled"]));
const password = computed(() => props.fields?.find(field => field.key === "password"));
const formValue = computed(() => ({ ...props.modelValue, storage_id: props.modelValue.storage_id || null }));
</script>

<template>
  <div class="plugin-config-grid app-form-layout">
    <component v-for="field in top" :key="field.key" :is="schemaFieldsComponent"
      :fields="[field]" :model-value="formValue" :disabled="disabled" compact plugin-id="storage-recycle-cleaner"
      @update:model-value="emit('update:modelValue', $event)" />
    <SavedSecretField :model-value="modelValue.password" :disabled="disabled"
      :label="password?.label || '回收站安全密钥'" :request="request"
      endpoint="/plugins/storage-recycle-cleaner/config/secret/password"
      @update:model-value="emit('update:modelValue', { ...modelValue, password: $event, password_clear: false })" />
    <component v-for="field in bottom" :key="field.key" :is="schemaFieldsComponent"
      :fields="[field]" :model-value="formValue" :disabled="disabled" compact plugin-id="storage-recycle-cleaner"
      @update:model-value="emit('update:modelValue', $event)" />
  </div>
</template>
