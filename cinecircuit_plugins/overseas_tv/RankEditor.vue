<script setup lang="ts">
import { computed, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";
const props = defineProps<{ modelValue: Record<string, unknown>; fields?: ConfigField[]; disabled?: boolean; schemaFieldsComponent: Component }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const scheduleFields = computed(() => orderedFields(props.fields || [], ["clear", "cron"]));
const sections = [
  { title: "订阅设置", keys: ["max_new", "modes", "past_days", "future_days"] },
  { title: "内容筛选", keys: ["min_rating", "min_votes", "allow_unrated", "country", "language", "include_types"] },
  { title: "播出平台", keys: ["netflix_enabled", "netflix_num", "hbo_enabled", "hbo_num", "disney_enabled", "disney_num", "apple_enabled", "apple_num", "amazon_enabled", "amazon_num", "hulu_enabled", "hulu_num"] },
];
function sectionFields(keys: string[]) {
  return orderedFields(props.fields || [], keys).map(field => ({ ...field,
    disabled: field.disabled || (field.key.endsWith("_num") && props.modelValue[field.key.replace(/_num$/, "_enabled")] === false),
  }));
}
function update(value: Record<string, unknown>) { emit("update:modelValue", { ...props.modelValue, ...value }); }
</script>
<template>
  <div class="maoyan-rank-settings plugin-config-grid app-form-layout">
    <component v-for="field in scheduleFields" :key="field.key" :is="schemaFieldsComponent" class="rank-schedule"
      :fields="[field]" :model-value="modelValue" :disabled="disabled" compact @update:model-value="update" />
    <template v-for="section in sections" :key="section.title">
      <h3>{{ section.title }}</h3>
      <component v-for="field in sectionFields(section.keys)" :key="field.key" :is="schemaFieldsComponent"
        :fields="[field]" :model-value="modelValue" :disabled="disabled" compact @update:model-value="update" />
    </template>
  </div>
</template>
<style scoped>
.maoyan-rank-settings h3{grid-column:1 / -1;margin:0;color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}
</style>
