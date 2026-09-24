<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";
const props = defineProps<{ modelValue: Record<string, unknown>; fields?: ConfigField[]; disabled?: boolean; schemaFieldsComponent: Component; loadConfig?: (signal: AbortSignal) => Promise<Record<string, unknown>> }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const loading = ref(Boolean(props.loadConfig));
const loadError = ref("");
const controller = new AbortController();
const controlsDisabled = computed(() => props.disabled || loading.value || Boolean(loadError.value));
onMounted(async () => {
  if (!props.loadConfig) return;
  try {
    const config = await props.loadConfig(controller.signal);
    if (!controller.signal.aborted) emit("update:modelValue", normalize(config));
  } catch {
    if (!controller.signal.aborted) loadError.value = "配置读取失败，请关闭后重试，避免覆盖原有设置。";
  } finally {
    loading.value = false;
  }
});
onUnmounted(() => controller.abort());
function normalize(config: Record<string, unknown>) {
  const old = Array.isArray(config.type) ? config.type.map(String) : String(config.type ?? "movie").replaceAll("，", ",").split(",");
  const categories = config.platform_types ?? [
    ...(old.some(key => ["web-heat", "web-tv"].includes(key)) ? ["tv"] : []),
    ...(old.includes("zongyi") ? ["variety"] : []),
  ];
  const current = Object.fromEntries(Object.entries(config).filter(([key]) => !["type", "all_enabled", "all_num", "web_movie_num"].includes(key)));
  return { ...current, movie_enabled: config.movie_enabled ?? old.includes("movie"),
    platform_types: Array.isArray(categories) ? categories : String(categories).split(","),
    ...Object.fromEntries(["tx", "iqy", "mg", "yk"].map(key => [key + "_enabled",
      config.platform_types === undefined && config.all_enabled ? true : config[key + "_enabled"] ?? false])),
  } as Record<string, unknown>;
}
const value = computed(() => normalize(props.modelValue));
const schedule = computed(() => orderedFields(props.fields || [], ["clear", "cron"]));
const movies = computed(() => orderedFields(props.fields || [], ["movie_enabled", "num"]).map(field => ({ ...field, disabled: field.disabled || (field.key === "num" && !value.value.movie_enabled) })));
const categories = computed(() => orderedFields(props.fields || [], ["platform_types"]));
const platforms = computed(() => orderedFields(props.fields || [], ["tx", "iqy", "mg", "yk"].flatMap(key => [key + "_enabled", key + "_num"])).map(field => {
  const key = field.key.split("_")[0];
  const selected = value.value.platform_types as string[];
  return { ...field, disabled: field.disabled || !selected.some(category => key !== "mg" || category !== "documentary") || (field.key.endsWith("_num") && !value.value[key + "_enabled"]) };
}));
function update(next: Record<string, unknown>) {
  emit("update:modelValue", normalize({ ...value.value, ...next }));
}
</script>
<template>
  <div class="maoyan-rank-settings plugin-config-grid app-form-layout">
    <VTextField v-if="loadConfig" class="rank-load-validation" :model-value="loading || loadError ? '' : 'ready'" :rules="[() => (!loading && !loadError) || '请等待配置读取成功后保存']" hide-details />
    <p v-if="loading || loadError" class="rank-help" role="status">{{ loadError || '正在读取榜单配置…' }}</p>
    <component v-for="field in schedule" :key="field.key" :is="schemaFieldsComponent" class="rank-schedule" :fields="[field]" :model-value="value" :disabled="controlsDisabled" compact @update:model-value="update" />
    <h3>猫眼电影榜单</h3>
    <component v-for="field in movies" :key="field.key" :is="schemaFieldsComponent" :fields="[field]" :model-value="value" :disabled="controlsDisabled" compact @update:model-value="update" />
    <h3>平台影视榜单</h3>
    <component :is="schemaFieldsComponent" class="rank-types" :fields="categories" :model-value="value" :disabled="controlsDisabled" compact @update:model-value="update" />
    <h3>播出平台</h3>
    <component v-for="field in platforms" :key="field.key" :is="schemaFieldsComponent" :fields="[field]" :model-value="value" :disabled="controlsDisabled" compact @update:model-value="update" />
  </div>
</template>
<style scoped>
.maoyan-rank-settings h3,.rank-types,.rank-help{grid-column:1 / -1}
.rank-load-validation{display:none}
.rank-help{margin:0;color:var(--app-text-muted);font-size:12px}
.maoyan-rank-settings h3{margin:0;color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}
</style>
