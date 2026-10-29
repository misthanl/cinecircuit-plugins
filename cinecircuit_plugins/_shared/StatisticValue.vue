<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ value: string | number | null | undefined }>();
const missing = computed(() => props.value == null || props.value === "—");
</script>

<template>
  <span v-if="missing" class="plugin-statistic-placeholder" aria-label="暂无数据">—</span>
  <template v-else>{{ value }}</template>
</template>

<style scoped>
.plugin-statistic-placeholder {
  display: inline-block;
  color: var(--app-text-muted, #7b89a4);
  font-size: 12px;
  font-weight: 400;
  line-height: 1;
  vertical-align: middle;
}
</style>
