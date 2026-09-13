<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ task: Record<string, unknown>; siteName: string; downloaderName: string; cadence: string; globalLimit: number; disabled?: boolean }>();
const emit = defineEmits<{ edit: []; remove: [] }>();
const rate = (value: unknown) => Number(value) > 0 ? `${Number(value).toLocaleString()} KiB/s` : "不限速";
const metrics = computed(() => [
  ["执行周期", props.cadence], ["每次添加", `最多 ${props.task.max_add || 3} 个`],
  ["下载数量上限", Number(props.task.task_limit) > 0 ? `${props.task.task_limit} 个` : `遵循全局 · ${props.globalLimit} 个`],
  ["保种总体积上限", Number(props.task.seeding_limit_gib) > 0 ? `${props.task.seeding_limit_gib} GiB` : "不限体积"],
  ["单种上传限速", rate(props.task.upload_limit_kib)], ["单种下载限速", rate(props.task.download_limit_kib)],
]);
const cleanup = computed(() => !props.task.cleanup_enabled ? "不自动清理" : !props.task.delete_task ? "命中后暂停" : props.task.allow_delete_files ? "删种及文件" : "仅删种");
</script>
<template>
  <article class="task-card app-surface-boundary">
    <header>
      <span class="task-icon"><VIcon icon="mdi-swap-vertical" /></span>
      <div class="task-title"><h4>{{ task.name || '未命名刷流任务' }}</h4><p>{{ siteName }} <span aria-hidden="true">→</span> {{ downloaderName }}</p></div>
      <span class="task-status" :class="{ paused: task.enabled === false }">{{ task.enabled === false ? '已停用' : '已启用' }}</span>
      <VBtn variant="text" size="small" :disabled="disabled" @click="$emit('edit')"><VIcon icon="mdi-pencil-outline" />编辑任务</VBtn>
      <span class="task-menu"><VBtn icon="mdi-dots-vertical" variant="text" size="small" aria-label="更多任务操作" /><VMenu activator="parent" location="bottom end" :close-on-content-click="true"><VList class="card-action-menu" density="compact" nav min-width="128"><VListItem prepend-icon="mdi-trash-can-outline" title="移除任务" base-color="error" :disabled="disabled" @click="emit('remove')" /></VList></VMenu></span>
    </header>
    <dl><div v-for="[label, value] in metrics" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl>
    <footer>
      <span class="rule"><VIcon icon="mdi-filter-outline" />{{ task.include ? '包含：' + task.include : '全部资源 · 不限制关键词' }}{{ task.exclude ? ' · 排除：' + task.exclude : '' }}</span>
      <span><VIcon icon="mdi-delete-outline" />{{ cleanup }}</span>
      <span><VIcon :icon="task.notification_enabled ? 'mdi-bell-outline' : 'mdi-bell-remove-outline'" />{{ task.notification_enabled ? '通知开启' : '通知关闭' }}</span>
    </footer>
  </article>
</template>
<style scoped>
.task-card{border:1px solid var(--app-border-subtle,#e1e7f0);border-radius:12px;background:var(--app-surface,#fff);color:var(--app-text);min-width:0}.task-card header{display:flex;align-items:center;gap:10px;padding:14px 16px}.task-icon{display:grid;place-items:center;width:40px;height:40px;border-radius:9px;background:rgba(var(--v-theme-primary),.09);color:rgb(var(--v-theme-primary));flex-shrink:0}.task-title{flex:1;min-width:0}.task-title h4{margin:0;font-size:15px;font-weight:650;overflow-wrap:anywhere}.task-title p{margin:5px 0 0;color:var(--app-text-muted,#7b89a4);font-size:12px;overflow-wrap:anywhere}.task-title p span{margin:0 6px}.task-status{border-radius:20px;background:var(--app-success-soft);color:var(--app-success-text);padding:4px 10px;font-size:12px;white-space:nowrap}.task-status.paused{background:var(--app-surface-subtle,#f1f3f7);color:var(--app-text-muted,#7b89a4)}dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:0}dl>div{padding:12px 16px;border-top:1px solid var(--app-border-subtle,#e1e7f0)}dt{font-size:12px;color:var(--app-text-muted,#7b89a4)}dd{margin:4px 0 0;font-size:14px;font-weight:600;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}footer{display:grid;grid-template-columns:1.5fr 1fr auto;gap:14px;border-radius:0 0 12px 12px;background:var(--app-surface-subtle,#f4f6fa);padding:10px 16px;font-size:12px;color:var(--app-text-secondary,#657087)}footer span{display:flex;align-items:center;gap:8px;overflow-wrap:anywhere}footer .v-icon{font-size:18px;flex-shrink:0}
@media(max-width:600px){.task-card header{flex-wrap:wrap;gap:8px}.task-title{min-width:calc(100% - 58px)}.task-status{margin-right:auto}dl{grid-template-columns:repeat(2,minmax(0,1fr))}footer{grid-template-columns:1fr 1fr}footer .rule{grid-column:1/-1}}
</style>
