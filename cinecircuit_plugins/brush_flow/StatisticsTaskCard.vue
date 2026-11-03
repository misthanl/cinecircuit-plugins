<script setup lang="ts">
import { computed, ref } from "vue";
import StatisticValue from "../_shared/StatisticValue.vue";
import type { StatisticsTask } from "./statistics-types";

const props = defineProps<{ task: StatisticsTask; siteName: string; downloaderName: string; globalEnabled: boolean; formatBytes: (value: number) => string }>();
const expanded = ref(false);
const enabled = computed(() => !props.task.removed && props.task.enabled && props.globalEnabled);
const detailsId = computed(() => `brush-stat-${encodeURIComponent(props.task.id)}-details`);
const schedule = computed(() => !enabled.value ? "调度已停止" : props.task.cron ? `Cron：${props.task.cron}` : `每 ${props.task.interval_minutes} 分钟执行`);
const capacity = computed(() => props.task.seeding_limit_gib > 0 ? `${props.task.seeding_limit_gib} GiB` : "不限体积");
const percent = computed(() => Math.max(0, Math.min(100, props.task.size / (props.task.seeding_limit_gib * 1024 ** 3) * 100)));
const metrics = computed(() => [
  { label: "下载中", icon: "mdi-download-outline", value: props.task.download_count },
  { label: "保种中", icon: "mdi-database-outline", value: props.task.seed_count },
  { label: "上传速度", icon: "mdi-arrow-up", value: `${props.formatBytes(props.task.upload_speed)}/s` },
  { label: "下载速度", icon: "mdi-download-outline", value: `${props.formatBytes(props.task.download_speed)}/s` },
]);
</script>

<template>
  <article class="stat-task app-surface-boundary" :class="{ paused: !enabled, expanded }">
    <button class="stat-task-toggle" type="button" :aria-label="`${expanded ? '收起' : '展开'}${task.name}统计详情`" :aria-expanded="expanded" :aria-controls="detailsId" @click="expanded = !expanded">
      <span class="stat-task-info">
        <span class="stat-task-name">{{ task.name }}</span>
        <span class="stat-task-metadata">
          <span>{{ siteName }} → {{ downloaderName }}</span>
          <span><span aria-hidden="true">·</span> 保种 <StatisticValue :value="task.available ? formatBytes(task.size) : '—'" /> / {{ capacity }}</span>
          <span><span aria-hidden="true">·</span> {{ schedule }}</span>
        </span>
      </span>
      <span class="stat-task-status" :class="{ paused: !enabled }">{{ task.removed ? '已移除' : enabled ? '已启用' : '已停用' }}</span>
      <VIcon class="stat-task-chevron" :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="20" />
    </button>
    <div v-if="expanded" :id="detailsId" class="stat-task-details">
      <dl class="stat-task-metrics">
        <div v-for="metric in metrics" :key="metric.label">
          <VIcon :icon="metric.icon" size="20" />
          <dt>{{ metric.label }}</dt>
          <dd><StatisticValue :value="task.available ? metric.value : '—'" /></dd>
        </div>
      </dl>
      <progress v-if="task.available && task.seeding_limit_gib > 0" class="stat-task-capacity" :value="percent" max="100" :aria-label="task.name + '保种体积占用'" />
      <p v-if="!task.available" class="stat-task-note">暂无实时数据，历史累计统计仍保留。</p>
    </div>
  </article>
</template>

<style scoped>
.stat-task{min-width:0;border:1px solid var(--app-border-subtle);border-left:3px solid var(--app-success-text);border-radius:var(--app-radius-panel);background:var(--app-surface);color:var(--app-text)}
.stat-task.paused{border-left-color:var(--app-border-subtle)}
.stat-task-toggle{display:flex;align-items:center;width:100%;gap:16px;padding:16px;border:0;border-radius:var(--app-radius-panel);background:transparent;color:inherit;text-align:left;font:inherit;cursor:pointer}
.stat-task-toggle:focus-visible{outline:2px solid rgb(var(--v-theme-primary));outline-offset:2px}
.stat-task-info{display:grid;flex:1;min-width:0;gap:5px}
.stat-task-name{font-size:var(--app-font-size-body);font-weight:var(--app-font-weight-heading);overflow-wrap:anywhere}
.stat-task-metadata{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;font-size:var(--app-table-field-content-font-size);font-weight:var(--app-font-weight-regular);line-height:var(--app-line-height-body);color:var(--app-text-secondary)}
.stat-task-metadata>span{min-width:0;overflow-wrap:anywhere}
.stat-task-status{flex-shrink:0;padding:4px 9px;border-radius:var(--app-radius-chip);font-size:var(--app-selection-chip-font-size);font-weight:var(--app-font-weight-regular);background:var(--app-success-soft);color:var(--app-success-text);white-space:nowrap}
.stat-task-status.paused{background:var(--app-surface-muted);color:var(--app-text-secondary)}
.stat-task-chevron{flex-shrink:0}
.stat-task-details{margin:0 16px;padding:16px 0;border-top:1px solid var(--app-border-subtle)}
.stat-task-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;margin:0}
.stat-task-metrics>div{display:grid;grid-template-columns:20px minmax(0,1fr);gap:6px 12px;align-items:center;min-width:0}
.stat-task-metrics .v-icon{grid-column:1;grid-row:1/3;color:rgb(var(--v-theme-primary))}
.stat-task-metrics dt{font-size:var(--app-table-field-content-font-size);font-weight:var(--app-font-weight-regular);color:var(--app-text)}
.stat-task-metrics dd{grid-column:2;margin:0;font-size:var(--app-font-size-body);font-weight:var(--app-font-weight-medium);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.stat-task-note{margin:16px 0 0;font-size:var(--app-font-size-explanation);font-weight:var(--app-font-weight-regular);color:var(--app-text-secondary)}
.stat-task-capacity{appearance:none;display:block;width:100%;height:6px;margin-top:16px;border:0;border-radius:var(--app-radius-chip);overflow:hidden}
.stat-task-capacity::-webkit-progress-bar{background:var(--app-surface-disabled)}
.stat-task-capacity::-webkit-progress-value{background:rgb(var(--v-theme-primary))}
.stat-task-capacity::-moz-progress-bar{background:rgb(var(--v-theme-primary))}
@media(max-width:600px){.stat-task-toggle{gap:10px}.stat-task-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.stat-task-status{font-size:var(--app-font-size-explanation)}}
</style>
