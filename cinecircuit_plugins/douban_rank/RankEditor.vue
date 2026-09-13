<script setup lang="ts">
import { computed, type Component } from "vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";

const props = defineProps<{ modelValue: Record<string, unknown>; fields?: ConfigField[]; disabled?: boolean; schemaFieldsComponent: Component }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const scheduleFields = computed(() => orderedFields(props.fields || [], ["clear", "cron", "proxy", "vote"]));
const rssFields = computed(() => orderedFields(props.fields || [], ["rsshub", "rss_addrs"]));
const selected = computed(() => {
  const value = props.modelValue.ranks ?? ["movie-real-time", "tv-hot"];
  return Array.isArray(value) ? value.map(String) : String(value).split(/[\n,，]+/).map(item => item.trim()).filter(Boolean);
});
const groups = [{ title: "电影榜单", movie: true }, { title: "电视剧与综艺", movie: false }];
function groupFields(movie: boolean) {
  return orderedFields(props.fields || [], ["ranks"]).map(field => ({ ...field, label: "榜单类型", options: ((field.options || []) as { value: string; label: string }[]).filter(option => String(option.value).startsWith("movie-") === movie) }));
}
function updateRanks(next: Record<string, unknown>, movie: boolean) {
  emit("update:modelValue", { ...props.modelValue, ranks: [...selected.value.filter(rank => rank.startsWith("movie-") !== movie), ...(Array.isArray(next.ranks) ? next.ranks : [])] });
}
</script>

<template>
  <div class="douban-rank-settings plugin-config-grid app-form-layout">
    <component v-for="field in scheduleFields" :key="field.key" :is="schemaFieldsComponent" :fields="[field]" :model-value="modelValue" :disabled="disabled" compact @update:model-value="emit('update:modelValue', $event)" />
    <template v-for="group in groups" :key="group.title">
      <h3>{{ group.title }}</h3>
      <component :is="schemaFieldsComponent" class="rank-types" :fields="groupFields(group.movie)" :model-value="{ ...modelValue, ranks: selected.filter(rank => rank.startsWith('movie-') === group.movie) }" :disabled="disabled" compact @update:model-value="updateRanks($event, group.movie)" />
    </template>
    <h3>自定义榜单</h3>
    <component v-for="field in rssFields" :key="field.key" :is="schemaFieldsComponent" class="rank-types" :fields="[field]" :model-value="modelValue" :disabled="disabled" compact @update:model-value="emit('update:modelValue', $event)" />
  </div>
</template>

<style scoped>
.douban-rank-settings h3,.rank-types{grid-column:1 / -1}
.douban-rank-settings h3{margin:0;color:var(--app-text);font-size:var(--app-font-size-body,14px);font-weight:var(--app-font-weight-heading,600)}
</style>
