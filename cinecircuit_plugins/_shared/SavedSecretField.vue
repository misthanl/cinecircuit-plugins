<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

const props = defineProps<{
  modelValue?: unknown;
  disabled?: boolean;
  label: string;
  endpoint: string;
  request: <T = unknown>(path: string, init?: RequestInit) => Promise<T>;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const restored = ref("");
const edited = ref(false);
const visible = ref(false);
const error = ref("");
const value = computed(() => edited.value ? String(props.modelValue || "") : String(props.modelValue || restored.value));
let pending: Promise<void> | null = null;

async function load() {
  if (edited.value || value.value) return;
  pending ||= props.request<{ value?: string }>(props.endpoint)
    .then(result => { if (!edited.value) restored.value = result.value || ""; })
    .finally(() => { pending = null; });
  await pending;
}
async function restore() {
  error.value = "";
  try { await load(); return true; }
  catch { error.value = "密钥读取失败，请点击眼睛重试"; return false; }
}
async function toggle() {
  if (props.disabled) return;
  if (visible.value) { visible.value = false; return; }
  if (await restore()) visible.value = true;
}
function update(next: string | null) {
  edited.value = true;
  restored.value = "";
  emit("update:modelValue", next || "");
}
onMounted(restore);
</script>

<template>
  <VTextField
    :model-value="value" :disabled="disabled" :label="label"
    :type="visible ? 'text' : 'password'" prepend-inner-icon="mdi-lock-outline"
    :append-inner-icon="visible ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
    autocomplete="off" :hide-details="!error" :error-messages="error"
    @click:append-inner="toggle" @update:model-value="update"
  />
</template>
