<script setup lang="ts">
import { computed } from "vue";
import type { Component } from "vue";
import { ref } from "vue";
import type { MediaItem } from "./workspaceTypes";
const fileInput = ref<HTMLInputElement | null>(null);
function resetInput() { if (fileInput.value) fileInput.value.value = ""; }
defineExpose({ resetInput });
const props = defineProps<{
language: string;
dialogComponent: Component; uploadPanelOpen: boolean; uploading: boolean; selected: MediaItem | null;
file: File | null; error: string; languages: string[][]; mediaName: (item: MediaItem) => string | undefined;
closeUploadDialog: () => void; upload: (event?: Event) => Promise<void>; chooseFile: (event: Event) => void;
}>();
const emit = defineEmits<{ "update:language": [value: string] }>();
const language = computed({
  get: () => props.language,
  set: (value: string) => emit("update:language", value),
});

</script>

<template>
    <component
      :is="props.dialogComponent"
      v-if="uploadPanelOpen"
      :model-value="true"
      :persistent="uploading"
      :z-index="2200"
      class="subtitle-host-overlay"
      content-class="subtitle-host-dialog-content subtitle-compact-dialog-content"
      @update:model-value="!$event && closeUploadDialog()"
    >
      <form
        class="subtitle-dialog subtitle-upload-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-upload-title"
        @submit="upload"
      >
        <header class="subtitle-dialog-heading">
          <span class="subtitle-dialog-symbol is-upload" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg></span>
          <div>
            <h2 id="subtitle-upload-title">上传字幕</h2>
            <p>为当前媒体添加外挂字幕</p>
          </div>
          <VBtn icon="mdi-close" variant="text" title="关闭" class="app-dialog-close subtitle-compact-close" aria-label="关闭上传字幕窗口"
            :disabled="uploading"
            @click="closeUploadDialog"
           />
        </header>
        <div class="subtitle-dialog-body subtitle-upload-dialog-body">
          <span v-if="selected" class="subtitle-field-heading">当前媒体</span>
          <div v-if="selected" class="subtitle-dialog-target">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4M17 8h4m-4 8h4"/></svg>
            <strong :title="mediaName(selected)">{{ mediaName(selected) }}</strong>
          </div>
          <span class="subtitle-field-heading">字幕文件</span>
          <label class="subtitle-upload-file">
            <span>选择文件</span>
            <strong :title="file?.name">{{ file?.name || "未选择文件" }}</strong>
            <input
              ref="fileInput"
              type="file"
              accept=".srt,.ass,.ssa,.sbv,.sub,.vtt,.webvtt"
              @change="chooseFile"
            />
          </label>
          <p class="subtitle-dialog-hint">支持 SRT、ASS、SSA、VTT、SUB</p>
          <span id="subtitle-language-label" class="subtitle-field-heading">字幕语言</span>
          <VSelect
            aria-labelledby="subtitle-language-label"
            :model-value="language"
            @update:model-value="language = $event"
            :items="languages.map((option) => ({ value: option[0], title: option[1] }))"
            :menu-props="{ location: 'bottom', offset: 6, maxHeight: 280, zIndex: 2300 }"
            variant="outlined"
            density="compact"
            hide-details
          />
          <p v-if="error" class="subtitle-dialog-error" role="alert">
            {{ error }}
          </p>
        </div>
        <footer class="subtitle-dialog-actions">
          <button
            type="submit"
            class="subtitle-action is-primary"
            :disabled="!file || uploading"
          >
            {{ uploading ? "上传中…" : "上传字幕" }}
          </button>
        </footer>
      </form>
    </component>
</template>
