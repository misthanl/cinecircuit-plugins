<script setup lang="ts">
import { computed } from "vue";
import type { Component } from "vue";
import type { SubtitleFile } from "./workspaceTypes";
const props = defineProps<{
adjustmentSeconds: string;
dialogComponent: Component; adjustingSubtitle: SubtitleFile | null; adjusting: boolean; adjustmentError: string;
closeAdjustment: () => void; submitAdjustment: (event?: Event) => Promise<void>;
}>();
const emit = defineEmits<{ "update:adjustmentSeconds": [value: string] }>();
const adjustmentSeconds = computed({
  get: () => props.adjustmentSeconds,
  set: (value: string) => emit("update:adjustmentSeconds", value),
});

</script>

<template>
    <component
      :is="props.dialogComponent"
      v-if="adjustingSubtitle"
      :model-value="true"
      :persistent="adjusting"
      :z-index="2200"
      class="subtitle-host-overlay"
      content-class="subtitle-host-dialog-content subtitle-compact-dialog-content"
      @update:model-value="!$event && closeAdjustment()"
    >
      <form
        class="subtitle-dialog subtitle-adjustment-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-adjustment-title"
        @submit="submitAdjustment"
      >
        <header class="subtitle-dialog-heading">
          <span class="subtitle-dialog-symbol is-timeline" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 6v6h5"/></svg></span>
          <div>
            <h2 id="subtitle-adjustment-title">调整字幕时间轴</h2>
            <p>正数延后字幕，负数提前字幕</p>
          </div>
          <VBtn icon="mdi-close" variant="text" title="关闭" class="app-dialog-close subtitle-compact-close" aria-label="关闭调轴窗口"
            :disabled="adjusting"
            @click="closeAdjustment"
           />
        </header>
        <div class="subtitle-dialog-body">
          <span class="subtitle-field-heading">当前字幕</span>
          <div class="subtitle-dialog-target">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5"/></svg>
            <strong :title="adjustingSubtitle.name">{{ adjustingSubtitle.name }}</strong>
          </div>
          <label class="subtitle-adjustment-field">
            <span class="subtitle-field-heading">偏移时间</span>
            <span class="subtitle-adjustment-input">
              <input
                :value="adjustmentSeconds"
                autofocus
                type="number"
                step="0.1"
                min="-300"
                max="300"
                inputmode="decimal"
                aria-describedby="subtitle-adjustment-help"
                :disabled="adjusting"
                @input="
                  adjustmentSeconds = (
                    $event.currentTarget as HTMLInputElement
                  ).value
                "
              />
              <span aria-hidden="true">秒</span>
            </span>
          </label>
          <small id="subtitle-adjustment-help">例如 +1.5 延后 1.5 秒；−2 提前 2 秒<br />可输入 −300 至 300 秒</small>
          <p v-if="adjustmentError" class="subtitle-dialog-error" role="alert">
            {{ adjustmentError }}
          </p>
        </div>
        <footer class="subtitle-dialog-actions">
          <button
            type="submit"
            class="subtitle-action is-primary"
            :disabled="adjusting || !adjustmentSeconds.trim()"
          >
            {{ adjusting ? "调整中…" : "确认调整" }}
          </button>
        </footer>
      </form>
    </component>
</template>
