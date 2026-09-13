<script setup lang="ts">
import type { Component } from "vue";
import type { SubtitleFile } from "./workspaceTypes";
const props = defineProps<{
dialogComponent: Component; deletingSubtitle: SubtitleFile | null; deleting: boolean; deleteError: string;
closeDeleteDialog: () => void; removeSubtitle: (event?: Event) => Promise<void>;
}>();
</script>

<template>
    <component
      :is="props.dialogComponent"
      v-if="deletingSubtitle"
      :model-value="true"
      :persistent="deleting"
      :z-index="2200"
      class="subtitle-host-overlay"
      content-class="subtitle-host-dialog-content subtitle-compact-dialog-content"
      @update:model-value="!$event && closeDeleteDialog()"
    >
      <form
        class="subtitle-dialog subtitle-delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-delete-title"
        @submit="removeSubtitle"
      >
        <header class="subtitle-dialog-heading">
          <span class="subtitle-dialog-symbol is-danger" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/></svg></span>
          <div>
            <h2 id="subtitle-delete-title">删除字幕</h2>
            <p>删除后无法恢复</p>
          </div>
          <VBtn icon="mdi-close" variant="text" title="关闭" class="app-dialog-close subtitle-compact-close" aria-label="关闭删除字幕窗口"
            :disabled="deleting"
            @click="closeDeleteDialog"
           />
        </header>
        <div class="subtitle-dialog-body subtitle-delete-dialog-body">
          <p class="subtitle-delete-message">确定要删除这个字幕文件吗？</p>
          <div class="subtitle-dialog-target">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5"/></svg>
            <strong :title="deletingSubtitle.name">{{ deletingSubtitle.name }}</strong>
          </div>
          <p class="subtitle-dialog-hint">仅删除字幕文件，不影响视频文件</p>
          <p v-if="deleteError" class="subtitle-dialog-error" role="alert">
            {{ deleteError }}
          </p>
        </div>
        <footer class="subtitle-dialog-actions">
          <button
            type="submit"
            class="subtitle-action is-danger"
            :disabled="deleting"
          >
            {{ deleting ? "删除中…" : "删除字幕" }}
          </button>
        </footer>
      </form>
    </component>
</template>
