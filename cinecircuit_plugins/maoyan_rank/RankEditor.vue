<script setup lang="ts">
import { computed, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";

const props = defineProps<{
  modelValue: Record<string, unknown>;
  fields?: ConfigField[];
  disabled?: boolean;
  schemaFieldsComponent: Component;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const scheduleFields = computed(() => orderedFields(props.fields || [], ["clear", "cron"]));
const selected = computed(() => {
  const value = props.modelValue.type ?? ["movie"];
  return Array.isArray(value) ? value.map(String) : String(value).replaceAll("，", ",").split(",").map(item => item.trim()).filter(Boolean);
});
const movieTypes = ["movie", "web-movie"];
const typeField = computed(() => props.fields?.find(field => field.key === "type"));
const options = computed(() => (typeField.value?.options || []) as { value: string; label: string }[]);
const movies = computed(() => options.value.filter(option => movieTypes.includes(option.value)));
const hasTelevision = computed(() => selected.value.some(value => ["web-heat", "web-tv", "zongyi"].includes(value)));
const value = computed(() => ({ ...props.modelValue, web_movie_num: props.modelValue.web_movie_num ?? props.modelValue.num ?? "10" }));
const televisionValue = computed(() => ({ ...value.value, type: selected.value.filter(type => !movieTypes.includes(type)) }));
const televisionFields = computed(() => typeField.value ? [{
  ...typeField.value, label: "榜单类型", options: options.value.filter(option => !movieTypes.includes(option.value)),
  required: !selected.value.some(type => movieTypes.includes(type)),
}] : []);
const platforms = computed(() => (props.fields || []).filter(field => /^(all|tx|iqy|mg|yk)_(enabled|num)$/.test(field.key)).map(field => ({
  ...field, disabled: field.disabled || !hasTelevision.value || (field.key.endsWith("_num") && !props.modelValue[field.key.replace(/_num$/, "_enabled")]),
})));
function toggleMovie(type: string, enabled: unknown) {
  const types = selected.value.filter(value => value !== type);
  emit("update:modelValue", { ...props.modelValue, type: enabled ? [...types, type] : types });
}
function updateTelevision(next: Record<string, unknown>) {
  emit("update:modelValue", { ...props.modelValue, type: [...selected.value.filter(type => movieTypes.includes(type)), ...(Array.isArray(next.type) ? next.type : [])] });
}
function countFields(type: string) {
  return orderedFields(props.fields || [], [type === "movie" ? "num" : "web_movie_num"])
    .map(field => ({ ...field, disabled: field.disabled || !selected.value.includes(type) }));
}
</script>

<template>
  <div class="maoyan-rank-settings plugin-config-grid app-form-layout">
    <component v-for="field in scheduleFields" :key="field.key" :is="schemaFieldsComponent" class="rank-schedule"
      :fields="[field]" :model-value="value" :disabled="disabled" compact
      @update:model-value="emit('update:modelValue', $event)" />
    <h3>电影榜单</h3>
    <template v-for="movie in movies" :key="movie.value">
      <VSwitch :model-value="selected.includes(movie.value)" :label="movie.label" :disabled="disabled"
        color="primary" hide-details @update:model-value="toggleMovie(movie.value, $event)" />
      <component :is="schemaFieldsComponent" :fields="countFields(movie.value)" :model-value="value" :disabled="disabled" compact
        @update:model-value="emit('update:modelValue', $event)" />
    </template>
    <h3>电视剧与综艺</h3>
    <component :is="schemaFieldsComponent" class="rank-types" :fields="televisionFields" :model-value="televisionValue" :disabled="disabled" compact
      @update:model-value="updateTelevision" />
    <h3>播出平台</h3>
    <component v-for="field in platforms" :key="field.key" :is="schemaFieldsComponent" :fields="[field]" :model-value="value" :disabled="disabled" compact
      @update:model-value="emit('update:modelValue', $event)" />
  </div>
</template>

<style scoped>
.maoyan-rank-settings h3,.rank-types{grid-column:1 / -1}
.maoyan-rank-settings h3{margin:0;color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}
</style>
