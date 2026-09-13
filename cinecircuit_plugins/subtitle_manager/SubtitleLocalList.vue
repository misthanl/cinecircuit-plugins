<script setup lang="ts">
import type { MediaItem, SubtitleFile } from "./workspaceTypes";
defineProps<{
  selected: MediaItem; inventoryLoading: boolean; activeActionMenu: string; activeActionMenuAbove: boolean;
  subtitleFormat: (name: string) => string; subtitleLanguage: (name: string) => string;
  formatSize: (size?: number) => string; closeActionMenu: (event: FocusEvent) => void;
  toggleActionMenu: (key: string, event: MouseEvent) => void; loadSelection: (item: MediaItem) => Promise<void>;
}>();
const emit = defineEmits<{ adjust: [subtitle: SubtitleFile]; delete: [subtitle: SubtitleFile]; searchOnline: [] }>();
</script>
<template>
            <div class="subtitle-local-panel">
              <div class="subtitle-table subtitle-local-list">
                <div class="subtitle-table-columns subtitle-local-columns" aria-hidden="true">
                  <span>文件名</span><span>语言</span><span>格式</span><span>大小</span>
                </div>
                <div v-if="selected.subtitles?.length" class="subtitle-file-list">
                  <div
                    v-for="subtitle in selected.subtitles"
                    :key="subtitle.name"
                    class="subtitle-file subtitle-table-row subtitle-local-file"
                  >
                    <span
                      :class="['subtitle-file-mark', `is-${subtitleFormat(subtitle.name).toLowerCase()}`]"
                      aria-hidden="true"
                    >{{ subtitleFormat(subtitle.name) }}</span>
                    <span class="subtitle-file-copy">
                      <strong
                        :title="subtitle.name"
                        :aria-label="subtitle.name"
                        tabindex="0"
                      >{{ subtitle.name }}</strong>
                    </span>
                    <span class="subtitle-mobile-meta">
                      {{ subtitleLanguage(subtitle.name) }} ·
                      {{ subtitleFormat(subtitle.name) }} ·
                      {{ formatSize(subtitle.size) }}
                    </span>
                    <span class="subtitle-file-meta">{{ subtitleLanguage(subtitle.name) }}</span>
                    <span class="subtitle-file-meta">{{ subtitleFormat(subtitle.name) }}</span>
                    <span class="subtitle-file-meta">{{ formatSize(subtitle.size) }}</span>
                    <span class="subtitle-row-actions" @focusout="closeActionMenu">
                      <button
                        type="button"
                        class="subtitle-action-trigger"
                        :aria-expanded="activeActionMenu === `local:${subtitle.name}`"
                        aria-haspopup="menu"
                        :aria-label="`操作 ${subtitle.name}`"
                        title="更多操作"
                        @click="toggleActionMenu(`local:${subtitle.name}`, $event)"
                      >⋮</button>
                      <span
                        v-if="activeActionMenu === `local:${subtitle.name}`"
                        :class="['subtitle-row-action-menu', { 'is-above': activeActionMenuAbove }]"
                        role="menu"
                      >
                        <button type="button" role="menuitem" @click="emit('adjust', subtitle)"><VIcon icon="mdi-clock-outline" size="18" aria-hidden="true" />调轴</button>
                        <button type="button" role="menuitem" class="is-danger" @click="emit('delete', subtitle)"><VIcon icon="mdi-trash-can-outline" size="18" aria-hidden="true" />删除</button>
                      </span>
                    </span>
                  </div>
                </div>
                <div v-else-if="inventoryLoading" class="subtitle-table-empty">正在读取字幕…</div>
                <div v-else-if="selected.subtitles === undefined" class="subtitle-table-empty">
                  <strong>字幕尚未读取成功</strong>
                  <button type="button" class="subtitle-text-button" @click="loadSelection(selected)">重试</button>
                </div>
                <div v-else class="subtitle-table-empty">
                  <strong>暂无本地字幕</strong>
                  <span>上传字幕文件，或切换到在线字幕进行搜索</span>
                  <button type="button" class="subtitle-text-button" @click="emit('searchOnline')">去在线搜索</button>
                </div>
              </div>
            </div>
</template>
