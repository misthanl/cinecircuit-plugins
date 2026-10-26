<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
const props = defineProps<{
  pluginId: string;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  cardComponent: Component; buttonComponent: Component; alertComponent: Component;
}>();
type Entry = { id: string; name: string; hash: string; status: string; error: string; timestamp: number };
type Report = { counts: Record<string, number>; items: Entry[] };
const UiCard = props.cardComponent, UiButton = props.buttonComponent, UiAlert = props.alertComponent;
const report = ref<Report>({ counts: {}, items: [] }), loading = ref(false), error = ref("");
const names: Record<string, string> = { submitted: "已提交", checking: "校验中", ready: "待确认", seeding: "做种中", paused: "已暂停", failed: "失败", attention: "需检查", duplicate: "已存在", missing: "任务已变化" };
const items = computed(() => report.value.items.map(item => ({ ...item, statusLabel: names[item.status] || item.status,
  date: item.timestamp ? new Date(item.timestamp * 1000).toLocaleString("zh-CN") : "—" })));
const headers = [{ title: "任务", key: "name" }, { title: "状态", key: "statusLabel" }, { title: "时间", key: "date" }, { title: "说明", key: "error" }];
const totals = computed(() => [
  { label: "做种中", count: report.value.counts.seeding || 0 },
  { label: "待校验", count: (report.value.counts.checking || 0) + (report.value.counts.submitted || 0) },
  { label: "已暂停", count: report.value.counts.paused || 0 },
  { label: "需处理", count: (report.value.counts.failed || 0) + (report.value.counts.attention || 0) },
]);
async function load(): Promise<void> {
  loading.value = true; error.value = "";
  try { report.value = await props.request<Report>(`/plugins/${props.pluginId}/api/statistics`); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "读取统计失败"; }
  finally { loading.value = false; }
}
async function check(): Promise<void> {
  loading.value = true; error.value = "";
  try { await props.request(`/plugins/${props.pluginId}/api/check`, { method: "POST", body: "{}" }); await load(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "检查失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <UiCard>
    <VCardText>
      <div class="d-flex align-center justify-space-between mb-4">
        <span>任务统计</span>
        <div class="d-flex ga-2">
          <UiButton variant="text" :loading="loading" @click="check">检查校验</UiButton>
          <UiButton variant="text" :loading="loading" @click="load">刷新</UiButton>
        </div>
      </div>
      <UiAlert v-if="error" type="error" class="mb-4">{{ error }}</UiAlert>
      <VRow>
        <VCol v-for="total in totals" :key="total.label" cols="6" md="3">
          <UiCard variant="tonal"><VCardText><div class="text-body-2">{{ total.label }}</div><div class="text-h5">{{ total.count }}</div></VCardText></UiCard>
        </VCol>
      </VRow>
      <VDataTable :headers="headers" :items="items" :loading="loading" :items-per-page="10" item-value="id" density="compact" no-data-text="暂无任务记录" />
    </VCardText>
  </UiCard>
</template>
