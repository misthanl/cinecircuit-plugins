<script setup lang="ts">
import { computed, type Component } from 'vue';
import TargetSelector from './TargetSelector.vue';
import { orderedFields, type ConfigField } from '../_shared/config-fields';
const props=defineProps<{modelValue:Record<string,unknown>;disabled?:boolean;request:(path:string,init?:RequestInit)=>Promise<unknown>;cronFieldComponent:Component;schemaFieldsComponent?:Component;fields?:ConfigField[]}>();
const emit=defineEmits<{ 'update:modelValue':[value:Record<string,unknown>] }>();
const cronField={key:'cron',input_type:'cron',label:'执行周期',placeholder:'5位cron表达式，留空自动',required:false};
const selectedEvent=computed(()=>String(props.modelValue.trigger_event || '').trim() || null);
const sharedFields=computed(()=>orderedFields(props.fields || [],['enabled','cron','trigger_event','delay','dry_run','max_libraries']).map(field=>({...field,icon:undefined,disabled:field.disabled || (field.key==='delay' && !selectedEvent.value)})));
function update(key:string,value:unknown){emit('update:modelValue',{...props.modelValue,[key]:value});}
</script>
<template>
  <div class="cover-run-settings plugin-config-grid app-form-layout">
    <component v-if="schemaFieldsComponent && sharedFields.length" :is="schemaFieldsComponent" class="shared-run-fields standard-config-fields plugin-config-grid app-form-layout" :fields="sharedFields" :model-value="modelValue" :disabled="disabled" compact @update:model-value="emit('update:modelValue',$event)" />
    <template v-else>
    <VSwitch label="启用定时生成" :model-value="Boolean(modelValue.enabled)" :disabled="disabled" hide-details color="primary" @update:model-value="update('enabled',$event)" />
    <component :is="cronFieldComponent" :model-value="modelValue.cron || ''" :field="cronField" :disabled="disabled" @update:model-value="update('cron',$event)" />
    <VSelect label="触发事件" :model-value="selectedEvent" :disabled="disabled" :items="[
      { value: 'organizer.completed', title: '整理完成' },
      { value: 'sync.completed', title: '同步完成' },
      { value: 'metadata.scrape.completed', title: '刮削完成' },
    ]" clearable variant="outlined" hide-details @update:model-value="update('trigger_event',$event ?? '')" />
    <VTextField label="触发后延迟执行（秒）" type="number" min="0" max="3600" :model-value="modelValue.delay ?? 60" :disabled="disabled || !selectedEvent" variant="outlined" hide-details @update:model-value="update('delay',Number($event))" />
    <VSwitch label="预览模式（不上传）" :model-value="Boolean(modelValue.dry_run)" :disabled="disabled" hide-details color="primary" @update:model-value="update('dry_run',$event)" />
    <VTextField label="单次处理媒体库上限" type="number" min="1" max="50" :model-value="modelValue.max_libraries ?? 10" :disabled="disabled" variant="outlined" hide-details @update:model-value="update('max_libraries',Number($event))" />
    </template>
    <TargetSelector :model-value="modelValue" :disabled="disabled" :request="request" @update:model-value="emit('update:modelValue',$event)" />
  </div>
</template>
<style scoped>
.shared-run-fields{grid-column:1/-1}
.cover-run-settings{display:grid;row-gap:var(--app-plugin-config-row-gap,14px);column-gap:var(--app-plugin-config-column-gap,16px);align-items:start}

</style>
