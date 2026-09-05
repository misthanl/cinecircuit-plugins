<script setup lang="ts">
import TargetSelector from './TargetSelector.vue';
const props=defineProps<{modelValue:Record<string,unknown>;disabled?:boolean;request:(path:string,init?:RequestInit)=>Promise<unknown>}>();
const emit=defineEmits<{ 'update:modelValue':[value:Record<string,unknown>] }>();
function update(key:string,value:unknown){emit('update:modelValue',{...props.modelValue,[key]:value});}
</script>
<template>
  <div class="cover-run-settings">
    <VSwitch label="启用定时生成" :model-value="Boolean(modelValue.enabled)" :disabled="disabled" hide-details color="primary" @update:model-value="update('enabled',$event)" />
    <VTextField label="执行周期" :model-value="modelValue.cron || ''" :disabled="disabled" variant="outlined" hide-details @update:model-value="update('cron',$event)" />
    <VSwitch label="刮削完成后更新封面" :model-value="Boolean(modelValue.transfer_monitor)" :disabled="disabled" hide-details color="primary" @update:model-value="update('transfer_monitor',$event)" />
    <VTextField label="延迟执行（秒）" type="number" min="0" max="3600" :model-value="modelValue.delay ?? 60" :disabled="disabled" variant="outlined" hide-details @update:model-value="update('delay',Number($event))" />
    <VSwitch label="预览模式（不上传）" :model-value="Boolean(modelValue.dry_run)" :disabled="disabled" hide-details color="primary" @update:model-value="update('dry_run',$event)" />
    <VTextField label="单次处理媒体库上限" type="number" min="1" max="50" :model-value="modelValue.max_libraries ?? 10" :disabled="disabled" variant="outlined" hide-details @update:model-value="update('max_libraries',Number($event))" />
    <TargetSelector :model-value="modelValue" :disabled="disabled" :request="request" @update:model-value="emit('update:modelValue',$event)" />
  </div>
</template>
<style scoped>
.cover-run-settings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;align-items:center}@media(max-width:680px){.cover-run-settings{grid-template-columns:1fr}}
</style>
