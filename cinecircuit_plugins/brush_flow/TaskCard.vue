<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{ task: Record<string, unknown>; siteName: string; downloaderName: string; cadence: string; globalLimit: number; disabled?: boolean }>();
const emit = defineEmits<{ edit: []; remove: [] }>();
const expanded = ref(false);
const name = computed(() => String(props.task.name || "未命名刷流任务"));
const detailsId = computed(() => props.task.id ? `brush-task-${encodeURIComponent(String(props.task.id))}-details` : undefined);
const rate = (value: unknown) => Number(value) > 0 ? `${Number(value).toLocaleString()} KiB/s` : "不限速";
const volume = computed(() => Number(props.task.seeding_limit_gib) > 0 ? `${props.task.seeding_limit_gib} GiB` : "不限体积");
const summary = computed(() => `${props.cadence} · 每次 ${props.task.max_add || 3} 个 · 保种${volume.value === "不限体积" ? "不限体积" : ` ≤ ${volume.value}`}`);
const cleanup = computed(() => !props.task.cleanup_enabled ? "不自动清理" : !props.task.delete_task ? "命中后暂停" : props.task.allow_delete_files ? "删种及文件" : "仅删种");
const keywords = computed(() => [props.task.include ? `包含：${props.task.include}` : "", props.task.exclude ? `排除：${props.task.exclude}` : ""].filter(Boolean).join("；") || "不限制");
const resourceScope = computed(() => props.task.promotion === "free" ? "免费资源" : props.task.promotion === "2xfree" ? "2X 免费资源" : "全部资源");
const groups = computed(() => [
  { title: "任务调度", icon: "mdi-clock-outline", rows: [
    ["执行周期", props.cadence], ["每次添加", `最多 ${props.task.max_add || 3} 个`],
    ["下载任务上限", Number(props.task.task_limit) > 0 ? `${props.task.task_limit} 个` : `遵循全局 · ${props.globalLimit} 个`],
  ] },
  { title: "保种与限速", icon: "mdi-database-outline", rows: [
    ["保种总体积上限", volume.value], ["单种上传限速", rate(props.task.upload_limit_kib)], ["单种下载限速", rate(props.task.download_limit_kib)],
  ] },
]);
</script>

<template>
  <article class="task-card app-surface-boundary" :class="{ paused: task.enabled === false, expanded }">
    <header class="task-header">
      <button class="task-disclosure" type="button" :aria-label="`${expanded ? '收起' : '展开'}${name}详情`" :aria-expanded="expanded" :aria-controls="detailsId" @click="expanded = !expanded">
        <span class="task-icon"><VIcon icon="mdi-swap-vertical" /></span>
        <span class="task-title">
          <span class="task-name">{{ name }}</span>
          <span class="task-metadata">
            <span class="task-route">{{ siteName }} <span aria-hidden="true">→</span> {{ downloaderName }}</span>
            <span v-if="!expanded" class="task-summary"><span aria-hidden="true">·</span> {{ summary }}</span>
          </span>
        </span>
      </button>
      <span class="task-status" :class="{ paused: task.enabled === false }">{{ task.enabled === false ? '已停用' : '已启用' }}</span>
      <div class="task-actions">
        <span class="task-menu">
          <VBtn icon="mdi-dots-vertical" variant="text" size="small" aria-label="更多任务操作" />
          <VMenu activator="parent" location="bottom end" :close-on-content-click="true">
            <VList class="card-action-menu" density="compact" nav min-width="128">
              <VListItem prepend-icon="mdi-pencil-outline" title="编辑任务" :disabled="disabled" @click="emit('edit')" />
              <VListItem prepend-icon="mdi-trash-can-outline" title="移除任务" base-color="error" :disabled="disabled" @click="emit('remove')" />
            </VList>
          </VMenu>
        </span>
        <VBtn :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" variant="text" size="small" :aria-label="expanded ? '收起任务详情' : '展开任务详情'" :aria-expanded="expanded" :aria-controls="detailsId" @click="expanded = !expanded" />
      </div>
    </header>
    <div v-if="expanded" :id="detailsId" class="task-details">
      <section v-for="group in groups" :key="group.title" class="task-detail-group" :aria-label="group.title">
        <h5><VIcon :icon="group.icon" size="20" />{{ group.title }}</h5>
        <dl><div v-for="[label, value] in group.rows" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl>
      </section>
      <section class="task-detail-group task-rules" aria-label="筛选与处理">
        <h5><VIcon icon="mdi-tune-variant" size="20" />筛选与处理</h5>
        <div class="task-rule-columns">
          <dl><div><dt>资源范围</dt><dd>{{ resourceScope }}</dd></div><div class="task-keywords" :class="{ 'long-rule': keywords.length > 24 }"><dt>关键词限制</dt><dd>{{ keywords }}</dd></div></dl>
          <dl><div><dt>删种策略</dt><dd>{{ cleanup }}</dd></div><div><dt>任务通知</dt><dd class="task-notification"><span v-if="task.notification_enabled" class="notification-dot" aria-hidden="true" />{{ task.notification_enabled ? '已开启' : '已关闭' }}</dd></div></dl>
        </div>
      </section>
    </div>
  </article>
</template>

<style scoped>
.task-card{border:1px solid var(--app-border-subtle);border-left:3px solid var(--app-success-text);border-radius:12px;background:var(--app-surface);color:var(--app-text);min-width:0}
.task-card.paused{border-left-color:var(--app-border-subtle)}
.task-header{display:flex;align-items:center;gap:12px;padding:14px 16px}
.task-disclosure{display:flex;align-items:center;flex:1;min-width:0;gap:14px;padding:0;border:0;background:transparent;color:inherit;text-align:left;font:inherit;cursor:pointer;border-radius:6px}
.task-disclosure:focus-visible{outline:2px solid rgb(var(--v-theme-primary));outline-offset:4px}
.task-icon{display:grid;place-items:center;width:40px;height:40px;border-radius:9px;background:var(--app-info-soft);color:rgb(var(--v-theme-primary));flex-shrink:0}
.task-title{display:grid;flex:1;gap:4px;min-width:0}
.task-name{font-size:var(--app-font-size-body);font-weight:var(--app-font-weight-heading);overflow-wrap:anywhere}
.task-metadata{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;color:var(--app-text-secondary);font-size:var(--app-table-field-content-font-size);font-weight:var(--app-font-weight-regular);line-height:var(--app-line-height-body)}
.task-route{min-width:0;overflow-wrap:anywhere}
.task-route>span{margin:0 6px}
.task-summary{min-width:0;overflow-wrap:anywhere}
.task-summary>span{margin-right:6px}
.task-status{border-radius:var(--app-radius-chip);background:var(--app-success-soft);color:var(--app-success-text);padding:4px 10px;font-size:var(--app-selection-chip-font-size);white-space:nowrap}
.task-status.paused{background:var(--app-surface-subtle);color:var(--app-text-secondary)}
.task-actions{display:flex;align-items:center;gap:4px;flex-shrink:0}
.task-menu{display:inline-flex}
.task-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 40px;margin:0 16px;padding:20px 0;border-top:1px solid var(--app-border-subtle)}
.task-detail-group{min-width:0}
.task-detail-group h5{display:flex;align-items:center;gap:10px;margin:0 0 14px;font-size:var(--app-font-size-body);font-weight:var(--app-font-weight-heading);color:var(--app-text)}
.task-detail-group h5 .v-icon{color:rgb(var(--v-theme-primary));flex-shrink:0}
.task-detail-group dl{display:grid;gap:10px;margin:0;font-size:var(--app-font-size-body);font-weight:var(--app-font-weight-regular)}
.task-detail-group dl>div{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:baseline}
.task-detail-group dt{color:var(--app-text);overflow-wrap:anywhere}
.task-detail-group dd{margin:0;text-align:right;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.task-rules{grid-column:1/-1;border-top:1px solid var(--app-border-subtle);padding-top:18px}
.task-rule-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:40px}
.task-detail-group .task-keywords.long-rule{grid-template-columns:minmax(0,1fr);gap:6px}
.task-keywords.long-rule dd{text-align:left}
.task-notification{display:flex;align-items:center;justify-content:flex-end;gap:8px}
.notification-dot{width:7px;height:7px;flex-shrink:0;border-radius:50%;background:var(--app-success-text)}
@media(max-width:700px){.task-disclosure{gap:12px}.task-details{gap:20px}.task-rule-columns{gap:20px}}
@media(max-width:480px){.task-header{flex-wrap:wrap;gap:8px}.task-disclosure{flex-basis:100%}.task-status{margin-left:52px;margin-right:auto}.task-details,.task-rule-columns{grid-template-columns:minmax(0,1fr)}.task-rule-columns{gap:10px}}
</style>
