<script setup lang="ts">
import type { Component } from "vue";
import { computed } from "vue";
import type { PreviewItem } from "./workspaceTypes";
const props = defineProps<{
activePreviewIndex: number | null;
dialogComponent: Component; previewItems: PreviewItem[]; savingPreview: boolean; previewSelected: number[];
previewProvider: string; closePreviewDialog: () => void; toggleAllPreviews: (checked: boolean) => void;
togglePreview: (index: number, checked: boolean) => void; confirmPreview: () => Promise<void>;
}>();
const emit = defineEmits<{ "update:activePreviewIndex": [value: number | null] }>();
const activePreviewIndex = computed({
  get: () => props.activePreviewIndex,
  set: (value: number | null) => emit("update:activePreviewIndex", value),
});

const activePreviewItem = computed(
  () =>
    props.previewItems.find((item) => item.index === activePreviewIndex.value) ||
    props.previewItems[0] ||
    null,
);
const allPreviewSelected = computed(
  () =>
    props.previewItems.length > 0 &&
    props.previewSelected.length === props.previewItems.length,
);
const somePreviewSelected = computed(
  () => props.previewSelected.length > 0 && !allPreviewSelected.value,
);

function previewLanguage(value: string) {
  const normalized = value.trim().toLowerCase();
  if (["zh-cn", "zh-hans", "chs"].includes(normalized)) return "简体中文";
  if (["zh-tw", "zh-hant", "cht"].includes(normalized)) return "繁体中文";
  if (normalized === "zh") return "中文";
  if (normalized === "en") return "英语";
  if (normalized === "ja") return "日语";
  if (normalized === "ko") return "韩语";
  return value || "自动识别";
}
</script>

<template>
    <component
      :is="props.dialogComponent"
      v-if="previewItems.length"
      :model-value="true"
      :persistent="savingPreview"
      :z-index="2200"
      class="subtitle-host-overlay"
      content-class="subtitle-host-dialog-content"
      @update:model-value="!$event && closePreviewDialog()"
    >
      <section
        :class="[
          'subtitle-dialog',
          'subtitle-preview-dialog',
          { 'is-single': previewItems.length === 1 },
        ]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-preview-title"
      >
        <header class="subtitle-dialog-heading">
          <div>
            <h2 id="subtitle-preview-title">字幕预览</h2>
            <p>保存前请确认字幕内容</p>
          </div>
          <button
            type="button"
            class="app-dialog-close subtitle-dialog-close"
            aria-label="关闭字幕预览窗口"
            :disabled="savingPreview"
            @click="closePreviewDialog"
          >×</button>
        </header>
        <div class="subtitle-preview-dialog-body">
          <aside
            v-if="previewItems.length > 1"
            class="subtitle-preview-files"
            aria-label="字幕文件"
          >
            <label class="subtitle-preview-files-heading">
              <span>字幕文件 <small>{{ previewItems.length }}</small></span>
              <span class="subtitle-preview-select-all">
                <input
                  type="checkbox"
                  :checked="allPreviewSelected"
                  :indeterminate="somePreviewSelected"
                  @change="toggleAllPreviews(($event.currentTarget as HTMLInputElement).checked)"
                />
                全选
              </span>
            </label>
            <div class="subtitle-preview-file-list">
              <div
                v-for="item in previewItems"
                :key="item.index"
                :class="[
                  'subtitle-preview-file',
                  { 'is-active': activePreviewItem?.index === item.index },
                ]"
              >
                <input
                  type="checkbox"
                  :checked="previewSelected.includes(item.index)"
                  :aria-label="`选择 ${item.name}`"
                  @change="togglePreview(item.index, ($event.currentTarget as HTMLInputElement).checked)"
                />
                <button
                  type="button"
                  class="subtitle-preview-file-open"
                  @click="activePreviewIndex = item.index"
                >
                  <span
                    :class="['subtitle-preview-format', `is-${item.format.toLowerCase()}`]"
                    aria-hidden="true"
                  >{{ item.format }}</span>
                  <span class="subtitle-preview-file-copy">
                    <strong :title="item.name">{{ item.name }}</strong>
                    <small>{{ previewLanguage(item.language) }} · {{ item.format }}</small>
                  </span>
                </button>
                <span class="subtitle-preview-valid" title="校验通过" aria-label="校验通过"></span>
              </div>
            </div>
          </aside>
          <main v-if="activePreviewItem" class="subtitle-preview-content">
            <div class="subtitle-preview-current">
              <span
                :class="['subtitle-preview-format', `is-${activePreviewItem.format.toLowerCase()}`]"
                aria-hidden="true"
              >{{ activePreviewItem.format }}</span>
              <span class="subtitle-preview-current-copy">
                <strong :title="activePreviewItem.name">{{ activePreviewItem.name }}</strong>
                <small>{{ previewLanguage(activePreviewItem.language) }} · {{ activePreviewItem.format }} · {{ previewProvider }}</small>
              </span>
              <span class="subtitle-preview-check"><i></i>校验通过</span>
            </div>
            <pre class="subtitle-preview-excerpt">{{ activePreviewItem.excerpt }}</pre>
          </main>
        </div>
        <footer class="subtitle-preview-footer">
          <span>已选择 {{ previewSelected.length }} / {{ previewItems.length }} 个字幕文件</span>
          <button
            type="button"
            class="subtitle-action is-primary"
            :disabled="!previewSelected.length || savingPreview"
            @click="confirmPreview"
          >{{ savingPreview ? "保存中…" : "保存所选" }}</button>
        </footer>
      </section>
    </component>
</template>
