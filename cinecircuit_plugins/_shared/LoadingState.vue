<script setup lang="ts">
withDefaults(defineProps<{ label?: string; inline?: boolean; minHeight?: number }>(), { label: "正在加载", minHeight: 54 });
</script>
<template>
  <div class="plugin-loading-state" :class="{ 'is-inline': inline }" :style="{ '--loading-height': `${minHeight}px` }" role="status" aria-live="polite" :aria-label="label">
    <span class="plugin-loading-ring" aria-hidden="true" /><span v-if="label">{{ label }}</span>
  </div>
</template>
<style scoped>
.plugin-loading-state{display:grid;min-height:var(--loading-height);place-content:center;justify-items:center;gap:8px;color:var(--app-text-secondary);font-size:11px;font-weight:400;line-height:1.4}
.plugin-loading-ring{box-sizing:border-box;width:20px;height:20px;border:2px solid rgba(var(--v-theme-primary,36,107,253),.16);border-top-color:var(--app-primary,#246bfd);border-radius:50%;animation:plugin-loading-spin .9s linear infinite}
.plugin-loading-state.is-inline{display:inline-flex;min-height:0;align-items:center;gap:6px}.is-inline .plugin-loading-ring{width:14px;height:14px}
@keyframes plugin-loading-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.plugin-loading-ring{animation:none;border-right-color:var(--app-primary,#246bfd)}}
</style>
