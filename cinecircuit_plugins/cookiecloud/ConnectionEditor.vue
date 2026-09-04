<script setup lang="ts">
import { onMounted, ref } from "vue";

interface SecretResponse {
  value?: string;
}

interface ConnectionConfig extends Record<string, unknown> {
  cron?: string;
  enabled?: boolean;
  notification_enabled?: boolean;
  password?: string;
  run_once?: boolean;
  user_key?: string;
}

type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

const props = withDefaults(defineProps<{
  disabled?: boolean;
  modelValue: ConnectionConfig;
  request: Requester;
}>(), { disabled: false });

const emit = defineEmits<{
  "update:modelValue": [value: ConnectionConfig];
}>();

const passwordVisible = ref(false);
const restoredPassword = ref("");
const restoredUserKey = ref("");
const revealError = ref("");
let passwordLoad: Promise<void> | null = null;

const periods = [
  { value: "0 */6 * * *", title: "每 6 小时" },
  { value: "0 */12 * * *", title: "每 12 小时" },
  { value: "", title: "每天" },
  { value: "0 0 * * 1", title: "每周" },
  { value: "0 0 1 * *", title: "每月" },
];

function update(key: keyof ConnectionConfig, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}

async function loadPassword() {
  if (props.modelValue.password || restoredPassword.value) return;
  passwordLoad ||= props.request<SecretResponse>("/plugins/cookiecloud/config/secret/password")
    .then(response => { restoredPassword.value = response.value || ""; });
  try { await passwordLoad; }
  catch (reason) { passwordLoad = null; throw reason; }
}

async function togglePassword() {
  if (passwordVisible.value) {
    passwordVisible.value = false;
    return;
  }
  revealError.value = "";
  try {
    await loadPassword();
    passwordVisible.value = true;
  } catch {
    revealError.value = "密码读取失败，请重试";
  }
}

onMounted(async () => {
  const failures: string[] = [];
  try {
    if (!props.modelValue.user_key) {
      const response = await props.request<SecretResponse>("/plugins/cookiecloud/config/secret/user_key");
      restoredUserKey.value = response.value || "";
    }
  } catch {
    failures.push("KEY");
  }
  try {
    await loadPassword();
  } catch {
    failures.push("密码");
  }
  if (failures.length) revealError.value = `${failures.join("和")}读取失败，请重试`;
});
</script>

<template>
  <div class="cookiecloud-config-fields">
    <p v-if="revealError" class="cookiecloud-config-hint" role="alert">{{ revealError }}</p>
    <VSwitch
      :model-value="Boolean(modelValue.enabled)"
      :disabled="disabled"
      label="启用站点 Cookie 同步"
      color="primary"
      hide-details
      @update:model-value="update('enabled', $event)"
    />
    <VSwitch
      :model-value="Boolean(modelValue.run_once)"
      :disabled="disabled"
      label="保存后立即运行一次"
      color="primary"
      hide-details
      @update:model-value="update('run_once', $event)"
    />
    <VTextField
      :model-value="modelValue.user_key || restoredUserKey"
      :disabled="disabled"
      label="用户 KEY"
      prepend-inner-icon="mdi-key-outline"
      autocomplete="off"
      hide-details
      @update:model-value="restoredUserKey = ''; update('user_key', $event)"
    />
    <VTextField
      :model-value="modelValue.password || restoredPassword"
      :disabled="disabled"
      label="端对端加密密码"
      :type="passwordVisible ? 'text' : 'password'"
      prepend-inner-icon="mdi-lock-outline"
      :append-inner-icon="passwordVisible ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
      autocomplete="off"
      hide-details
      @click:append-inner="togglePassword"
      @update:model-value="restoredPassword = ''; update('password', $event)"
    />
    <VSelect
      :model-value="modelValue.cron || ''"
      :disabled="disabled"
      label="定时检查周期"
      prepend-inner-icon="mdi-calendar-clock"
      :items="periods"
      hide-details
      @update:model-value="update('cron', $event)"
    />
    <VSwitch
      :model-value="Boolean(modelValue.notification_enabled)"
      :disabled="disabled"
      label="发送通知"
      color="primary"
      hide-details
      @update:model-value="update('notification_enabled', $event)"
    />
  </div>
</template>

<style scoped>
.cookiecloud-config-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 14px;
}

.cookiecloud-config-hint {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--app-text-muted);
  font-size: 12px;
}

@media (max-width: 600px) {
  .cookiecloud-config-fields {
    grid-template-columns: 1fr;
  }
}
</style>
