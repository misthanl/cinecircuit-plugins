<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";
import SavedSecretField from "../_shared/SavedSecretField.vue";

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
  schemaFieldsComponent?: Component;
  fields?: ConfigField[];
}>(), { disabled: false });

const emit = defineEmits<{
  "update:modelValue": [value: ConnectionConfig];
}>();

const topFields = computed(() => orderedFields(props.fields || [], ["enabled", "run_once"]));
const bottomFields = computed(() => orderedFields(props.fields || [], ["cron", "notification_enabled"]));
const shared = computed(() => Boolean(props.schemaFieldsComponent && topFields.value.length && bottomFields.value.length));
const restoredUserKey = ref("");
const revealError = ref("");

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
  if (failures.length) revealError.value = `${failures.join("和")}读取失败，请重试`;
});
</script>

<template>
  <div class="cookiecloud-config-fields plugin-config-grid app-form-layout">
    <p v-if="revealError" class="cookiecloud-config-hint" role="alert">{{ revealError }}</p>
    <component v-if="shared" :is="schemaFieldsComponent" class="shared-connection-fields standard-config-fields plugin-config-grid app-form-layout" :model-value="modelValue" :fields="topFields" :disabled="disabled" compact @update:model-value="emit('update:modelValue', $event)" />
    <template v-else>
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
    </template>
    <VTextField
      :model-value="modelValue.user_key || restoredUserKey"
      :disabled="disabled"
      label="用户 KEY"
      prepend-inner-icon="mdi-key-outline"
      autocomplete="off"
      hide-details
      @update:model-value="restoredUserKey = ''; update('user_key', $event)"
    />
    <SavedSecretField
      :model-value="modelValue.password"
      :disabled="disabled"
      label="端对端加密密码"
      :request="request"
      endpoint="/plugins/cookiecloud/config/secret/password"
      @update:model-value="update('password', $event)"
    />
    <component v-if="shared" :is="schemaFieldsComponent" class="shared-connection-fields standard-config-fields plugin-config-grid app-form-layout" :model-value="modelValue" :fields="bottomFields" :disabled="disabled" compact @update:model-value="emit('update:modelValue', $event)" />
    <template v-else>
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
    </template>
  </div>
</template>

<style scoped>
.shared-connection-fields { grid-column: 1 / -1; }
.cookiecloud-config-fields {
  display: grid;
  row-gap: var(--app-plugin-config-row-gap, 14px);
  column-gap: var(--app-plugin-config-column-gap, 16px);
}

.cookiecloud-config-hint {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--app-text-muted);
  font-size: var(--app-font-size-helper, 12px);
}


</style>
