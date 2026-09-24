<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import SubtitleLocalList from "./SubtitleLocalList.vue";
import SubtitleMediaSummary from "./SubtitleMediaSummary.vue";
import SubtitleDeleteDialog from "./SubtitleDeleteDialog.vue";
import SubtitleAdjustmentDialog from "./SubtitleAdjustmentDialog.vue";
import SubtitlePreviewDialog from "./SubtitlePreviewDialog.vue";
import SubtitleUploadDialog from "./SubtitleUploadDialog.vue";
import { createInlineSearchViewport } from "./inlineSearchViewport";
import { trackWorkspaceBounds } from "./workspaceBounds";
const searchViewport = createInlineSearchViewport();
const workspaceRoot = ref<HTMLElement | null>(null);
let releaseWorkspaceBounds: (() => void) | undefined;
let sourceResizeObserver: ResizeObserver | undefined;
function disposeWorkspace() { catalogRequest++; selectionRequest++; onlineSession.reset(); searchViewport.dispose(); sourceResizeObserver?.disconnect(); releaseWorkspaceBounds?.(); }

import type { SubtitleFile, MediaItem, ItemList, AdjustmentResult, Requester, CaptchaChallenge, SourceStatus } from "./workspaceTypes";
import { SubtitleOnlineSession } from "./onlineWorkspace";

const props = defineProps<{ request: Requester; alertComponent?: Component; dialogComponent: Component }>();
const items = ref<MediaItem[]>([]);
const selected = ref<MediaItem | null>(null);
const query = ref("");
const loading = ref(false);
const offset = ref(0);
const hasMore = ref(false);
let loadedQuery = "";
const inventoryLoading = ref(false);
let catalogRequest = 0;
let selectionRequest = 0;
const uploading = ref(false);
const status = ref("");
const error = ref("");
const onlineSession = new SubtitleOnlineSession((path, init) => props.request(path, init), selected, error, status);
const { online, onlineQuery, sourceStatuses, activeSource, manualActions, captchaChallenges, selectedCandidate, previewToken, previewItems, previewSelected, activePreviewIndex, previewing, previewCaptcha, captchaInput, solvingCaptcha, seasonPack, searching } = onlineSession;
const language = ref("auto");
const file = ref<File | null>(null);
const uploadDialog = ref<InstanceType<typeof SubtitleUploadDialog> | null>(null);
const savingPreview = ref(false);
const adjustingSubtitle = ref<SubtitleFile | null>(null);
const adjustmentSeconds = ref("0");
const adjustmentError = ref("");
const adjusting = ref(false);
const deletingSubtitle = ref<SubtitleFile | null>(null);
const deleteError = ref("");
const deleting = ref(false);
const uploadPanelOpen = ref(false);
const activePanel = ref<"local" | "online">("local");
const posterFailed = ref(false);
const activeActionMenu = ref("");
const activeActionMenuAbove = ref(false);
const mobileSearchOpen = ref(false);
const sourceScroller = ref<HTMLElement | null>(null);
const sourceCanScrollLeft = ref(false);
const sourceCanScrollRight = ref(false);

const onlineSearchInput = ref<HTMLInputElement | null>(null);
const noticeText = computed(() => error.value || status.value);
const showNotice = computed(
  () => Boolean(error.value || (status.value && !status.value.startsWith("已读取 "))),
);
// Keep the host alert bridge's source mounted without showing a duplicate banner.
const notificationOnly = computed(() => !error.value && /^(?:找到 |在线字幕源)/.test(status.value));
const noticeTitle = computed(() => {
  if (error.value) return "操作失败";
  if (status.value.startsWith("找到 ") || status.value.startsWith("在线字幕源"))
    return "搜索完成";
  if (status.value.startsWith("已写入 ")) return "上传完成";
  if (status.value.startsWith("已保存 ")) return "保存完成";
  if (status.value.startsWith("已删除 ")) return "删除完成";
  if (status.value.startsWith("已调整 ")) return "调整完成";
  if (status.value.includes("验证码")) return "需要验证码";
  if (status.value.startsWith("已下载并校验 ")) return "预览就绪";
  return "提示";
});
const visibleOnline = computed(() =>
  activeSource.value
    ? online.value.filter((item) => item.provider === activeSource.value)
    : online.value,
);
const previewProvider = computed(
  () =>
    online.value.find(
      (item) => item.candidate_handle === selectedCandidate.value,
    )?.provider || "在线字幕",
);
const providerClasses: Record<string, string> = {
  ASSRT: "is-assrt",
  OpenSubtitles: "is-opensubtitles",
  SubHD: "is-subhd",
  字幕库: "is-zimuku",
};
const providerMarks: Record<string, string> = {
  ASSRT: "A",
  OpenSubtitles: "O",
  SubHD: "S",
  字幕库: "字",
};
const languages = [
  ["auto", "自动识别"],
  ["zh-CN", "简体中文"],
  ["zh-TW", "繁体中文"],
  ["zh", "中文（未区分简繁）"],
  ["en", "英语"],
  ["ja", "日语"],
  ["ko", "韩语"],
];

function toggleActionMenu(key: string, event: MouseEvent) {
  if (activeActionMenu.value === key) {
    activeActionMenu.value = "";
    activeActionMenuAbove.value = false;
    return;
  }
  const trigger = event.currentTarget as HTMLElement | null;
  const scrollport = trigger?.closest(
    ".subtitle-local-list, .subtitle-online-results",
  );
  const triggerBox = trigger?.getBoundingClientRect();
  const boundaryBox = scrollport?.getBoundingClientRect();
  activeActionMenuAbove.value = Boolean(
    triggerBox && boundaryBox && triggerBox.bottom + 108 > boundaryBox.bottom,
  );
  activeActionMenu.value = key;
}

function handleWorkspacePointerDown(event: PointerEvent) {
  const target = event.target as Element | null;
  if (!target?.closest(".subtitle-row-actions")) activeActionMenu.value = "";
  if (
    !target?.closest(
      ".subtitle-mobile-search-trigger, .subtitle-tab-search-controls",
    )
  )
    mobileSearchOpen.value = false;
}

function toggleMobileSearch() {
  mobileSearchOpen.value = !mobileSearchOpen.value;
  if (mobileSearchOpen.value) {
    requestAnimationFrame(() => onlineSearchInput.value?.focus());
  }
}

function closeActionMenu(event?: FocusEvent) {
  const current = event?.currentTarget as HTMLElement | null;
  const next = event?.relatedTarget as Node | null;
  if (!current || !next || !current.contains(next)) activeActionMenu.value = "";
}

function restoreSelection() {
    const next =
      items.value.find((item) => item.path === selected.value?.path) ||
      items.value[0] ||
      null;
    if (next && next.path !== selected.value?.path) selectMedia(next);
    else {
      selected.value = next;
      if (next) void loadSelection(next);
      else { selectionRequest++; inventoryLoading.value = false; }
    }
}

function applyCatalogPage(result: ItemList<MediaItem> & { has_more?: boolean }, nextOffset: number, keyword: string) {
  loadedQuery = keyword;
  offset.value = nextOffset;
  hasMore.value = Boolean(result?.has_more);
  items.value = Array.isArray(result?.items) ? result.items : [];
  restoreSelection();
  status.value = items.value.length
    ? `已读取 ${items.value.length} 个本地媒体文件`
    : "没有找到可访问的同步或整理媒体";
}

async function load(nextOffset = 0) {
  const requestId = ++catalogRequest;
  const keyword = query.value;
  if (keyword !== loadedQuery) nextOffset = 0;
  loading.value = true;
  error.value = "";
  try {
    const result = await props.request<ItemList<MediaItem> & { has_more?: boolean }>(
      `/plugins/subtitle-manager/api/catalog?query=${encodeURIComponent(keyword)}&limit=100&offset=${nextOffset}`,
    );
    if (requestId !== catalogRequest) return;
    applyCatalogPage(result, nextOffset, keyword);
  } catch (reason) {
    if (requestId === catalogRequest) error.value = reason instanceof Error ? reason.message : "媒体记录读取失败";
  } finally {
    if (requestId === catalogRequest) loading.value = false;
  }
}

async function upload(event?: Event) {
  event?.preventDefault();
  if (!selected.value || !file.value || uploading.value) return;
  uploading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      media_path: selected.value.path,
      language: language.value,
    });
    await props.request(`/plugins/subtitle-manager/api/upload?${params}`, {
      method: "POST",
      headers: {
        "Content-Type": file.value.type || "application/octet-stream",
        "X-Plugin-Filename": encodeURIComponent(file.value.name),
      },
      body: file.value,
    });
    status.value = `已写入 ${file.value.name}`;
    file.value = null;
    uploadDialog.value?.resetInput();
    await load(offset.value);
    uploadPanelOpen.value = false;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "字幕上传失败";
  } finally {
    uploading.value = false;
  }
}

function openUploadDialog() {
  error.value = "";
  uploadPanelOpen.value = true;
}

function closeUploadDialog() {
  if (uploading.value) return;
  uploadPanelOpen.value = false;
  file.value = null;
  uploadDialog.value?.resetInput();
}



async function searchOnline(event?: Event) {
  event?.preventDefault();
  if (!selected.value || searching.value) return;
  activePanel.value = "online";
  await onlineSession.search();
  scheduleSourceOverflow();
}
const previewOnline = (candidateToken: string) => onlineSession.preview(candidateToken);
async function submitCaptcha(challenge: CaptchaChallenge | null) {
  await onlineSession.submitCaptcha(challenge);
  scheduleSourceOverflow();
}

async function confirmPreview() {
  if (
    !selected.value ||
    !previewToken.value ||
    !previewSelected.value.length ||
    savingPreview.value
  )
    return;
  savingPreview.value = true;
  error.value = "";
  try {
    const result = await props.request<{
      saved?: unknown[];
      errors?: string[];
    }>("/plugins/subtitle-manager/api/online-confirm", {
      method: "POST",
      body: JSON.stringify({
        media_path: selected.value.path,
        preview_handle: previewToken.value,
        selected: previewSelected.value,
      }),
    });
    status.value = `已保存 ${result.saved?.length || 0} 个字幕文件`;
    previewToken.value = "";
    previewItems.value = [];
    previewSelected.value = [];
    activePreviewIndex.value = null;
    await load(offset.value);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "字幕保存失败";
  } finally {
    savingPreview.value = false;
  }
}

function openDeleteDialog(subtitle: SubtitleFile) {
  deletingSubtitle.value = subtitle;
  deleteError.value = "";
}

function closeDeleteDialog() {
  if (deleting.value) return;
  deletingSubtitle.value = null;
  deleteError.value = "";
}



async function removeSubtitle(event?: Event) {
  event?.preventDefault();
  if (!selected.value || !deletingSubtitle.value || deleting.value) return;
  const subtitle = deletingSubtitle.value;
  deleting.value = true;
  deleteError.value = "";
  try {
    await props.request("/plugins/subtitle-manager/api/delete", {
      method: "POST",
      body: JSON.stringify({
        media_path: selected.value.path,
        subtitle_name: subtitle.name,
      }),
    });
    status.value = `已删除 ${subtitle.name}`;
    deletingSubtitle.value = null;
    await load(offset.value);
  } catch (reason) {
    deleteError.value = reason instanceof Error ? reason.message : "字幕删除失败";
  } finally {
    deleting.value = false;
  }
}

function openAdjustment(subtitle: SubtitleFile) {
  adjustingSubtitle.value = subtitle;
  adjustmentSeconds.value = "0";
  adjustmentError.value = "";
}

function closeAdjustment() {
  if (adjusting.value) return;
  adjustingSubtitle.value = null;
  adjustmentError.value = "";
}



async function submitAdjustment(event?: Event) {
  event?.preventDefault();
  if (!selected.value || !adjustingSubtitle.value || adjusting.value) return;
  const seconds = Number(adjustmentSeconds.value);
  if (!Number.isFinite(seconds)) {
    adjustmentError.value = "请输入有效的时间偏移秒数";
    return;
  }
  adjusting.value = true;
  adjustmentError.value = "";
  try {
    const result = await props.request<AdjustmentResult>(
      "/plugins/subtitle-manager/api/adjust",
      {
        method: "POST",
        body: JSON.stringify({
          media_path: selected.value.path,
          subtitle_name: adjustingSubtitle.value.name,
          offset_seconds: seconds,
        }),
      },
    );
    status.value = `已调整 ${result.adjusted_count || 0} 条字幕时间轴`;
    adjustingSubtitle.value = null;
    await load(offset.value);
  } catch (reason) {
    adjustmentError.value =
      reason instanceof Error ? reason.message : "字幕调轴失败";
  } finally {
    adjusting.value = false;
  }
}

function mediaName(item: MediaItem) {
  return item.title || item.path.split(/[\\/]/).pop();
}
function identityQuery(item: MediaItem) {
  const identity = item.identity || {};
  const title = identity.title || item.title || mediaName(item) || "";
  if (identity.season != null && identity.episode != null)
    return `${title} S${String(identity.season).padStart(2, "0")}E${String(identity.episode).padStart(2, "0")}`;
  return `${title}${identity.year ? ` ${identity.year}` : ""}`;
}
function selectMedia(item: MediaItem) {
  onlineSession.reset();
  selected.value = item;
  adjustingSubtitle.value = null;
  adjustmentError.value = "";
  deletingSubtitle.value = null;
  deleteError.value = "";
  seasonPack.value = false;
  activePanel.value = "local";
  mobileSearchOpen.value = false;
  uploadPanelOpen.value = false;
  posterFailed.value = false;
  onlineQuery.value = identityQuery(item);
  error.value = "";
  void loadSelection(item);
  if (!item.poster_url) void loadPoster(item);
}
async function loadSelection(item: MediaItem) {
  const requestId = ++selectionRequest;
  inventoryLoading.value = item.subtitles === undefined;
  const params = `media_path=${encodeURIComponent(item.path)}`;
  const current = () => requestId === selectionRequest && selected.value?.path === item.path;
  await Promise.all([
    item.subtitles !== undefined ? Promise.resolve() : props.request<ItemList<SubtitleFile>>(
      `/plugins/subtitle-manager/api/inventory?${params}`,
    ).then((result) => {
      if (current()) item.subtitles = Array.isArray(result?.items) ? result.items : [];
    }).catch((reason) => {
      if (current()) error.value = reason instanceof Error ? reason.message : "字幕读取失败";
    }).finally(() => { if (current()) inventoryLoading.value = false; }),
    props.request<MediaItem>(`/plugins/subtitle-manager/api/detail?${params}`).then((result) => {
      if (!current()) return;
      const previousQuery = identityQuery(item);
      if (result?.identity) item.identity = result.identity;
      if (result?.title) item.title = result.title;
      if (onlineQuery.value === previousQuery) onlineQuery.value = identityQuery(item);
    }).catch((reason) => {
      if (current()) error.value = reason instanceof Error ? reason.message : "媒体详情读取失败";
    }),
  ]);
}
async function loadPoster(item: MediaItem) {
  try {
    const result = await props.request<{ data_url?: string }>(
      `/plugins/subtitle-manager/api/poster?media_path=${encodeURIComponent(item.path)}`,
    );
    if (selected.value?.path === item.path && result?.data_url) {
      item.poster_url = result.data_url;
      posterFailed.value = false;
    }
  } catch {
    // Posters are optional; subtitle management remains available without one.
  }
}
function updateSourceOverflow() {
  const element = sourceScroller.value;
  if (!element) return;
  sourceCanScrollLeft.value = element.scrollLeft > 2;
  sourceCanScrollRight.value =
    element.scrollLeft + element.clientWidth < element.scrollWidth - 2;
}
function observeSourceScroller() {
  const element = sourceScroller.value;
  if (!element || typeof ResizeObserver === "undefined") return;
  sourceResizeObserver?.disconnect();
  sourceResizeObserver = new ResizeObserver(updateSourceOverflow);
  sourceResizeObserver.observe(element);
}
function scheduleSourceOverflow() {
  requestAnimationFrame(() => {
    observeSourceScroller();
    updateSourceOverflow();
  });
}
function scrollSources(direction: -1 | 1) {
  const element = sourceScroller.value;
  if (!element) return;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  element.scrollBy({
    left: direction * Math.max(180, element.clientWidth * 0.66),
    behavior: reducedMotion ? "auto" : "smooth",
  });
}
function selectSource(provider: string, event?: MouseEvent) {
  activeSource.value = activeSource.value === provider ? "" : provider;
  const button = event?.currentTarget as HTMLElement | null;
  if (button && typeof button.scrollIntoView === "function") {
    button.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }
}
function providerClass(provider: string) {
  return providerClasses[provider] || "is-other";
}
function providerMark(provider: string) {
  return providerMarks[provider] || provider.slice(0, 1).toUpperCase();
}
function togglePreview(index: number, checked: boolean) {
  previewSelected.value = checked
    ? [...new Set([...previewSelected.value, index])]
    : previewSelected.value.filter((value) => value !== index);
}
function toggleAllPreviews(checked: boolean) {
  previewSelected.value = checked
    ? previewItems.value.map((item) => item.index)
    : [];
}
function closePreviewDialog() {
  if (savingPreview.value) return;
  previewToken.value = "";
  previewItems.value = [];
  previewSelected.value = [];
  activePreviewIndex.value = null;
}
function sourceState(value: SourceStatus) {
  if (value.state === "ready") {
    const rawCount = value.raw_candidate_count ?? value.candidate_count;
    return rawCount > value.candidate_count
      ? `${value.candidate_count}/${rawCount}`
      : `${value.candidate_count}`;
  }
  if (value.state === "restricted") return "";
  return value.state === "disabled" ? "未启用" : "失败";
}
function sourceTitle(value: SourceStatus) {
  const rawCount = value.raw_candidate_count ?? value.candidate_count;
  const count =
    rawCount > value.candidate_count
      ? `${value.candidate_count} 条匹配，源站返回 ${rawCount} 条`
      : `${value.candidate_count} 条结果`;
  const issue = value.errors?.[0]?.message;
  if (value.state === "ready") return `${value.provider}：${count}`;
  const state = sourceState(value);
  return `${value.provider}${state ? `：${state}` : ""}${issue ? `${state ? "；" : "："}${issue}` : ""}`;
}
function formatSize(size = 0) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
function subtitleFormat(name: string) {
  return name.split(".").pop()?.toUpperCase() || "字幕";
}
function subtitleLanguage(name: string) {
  const value = name.toLowerCase();
  if (/zh[-_.]?(tw|hant)|cht/.test(value)) return "繁体中文";
  if (/zh[-_.]?(cn|hans)|chs/.test(value)) return "简体中文";
  if (/(^|[._-])en(g)?([._-]|$)/.test(value)) return "英语";
  return "自动识别";
}
function chooseFile(event: Event) {
  file.value = (event.currentTarget as HTMLInputElement).files?.[0] || null;
}
function searchOnEnter(event: KeyboardEvent) {
  if (event.key === "Enter") load();
}
onMounted(() => {
  if (workspaceRoot.value) releaseWorkspaceBounds = trackWorkspaceBounds(workspaceRoot.value);
  load();
});
</script>

<template>
  <section ref="workspaceRoot" class="subtitle-workspace"
    @vue:before-unmount="disposeWorkspace" @pointerdown="handleWorkspacePointerDown">
    <div class="subtitle-browser app-surface-boundary">
      <component
        :is="alertComponent || 'div'"
        v-if="showNotice"
        :type="error ? 'error' : 'info'"
        variant="tonal"
        class="subtitle-host-notice"
        :class="{ 'subtitle-host-notice--notification-only': notificationOnly }"
        role="alert"
      >
        <strong>{{ noticeTitle }}</strong>
        <span>{{ noticeText }}</span>
      </component>

      <div class="subtitle-layout">
        <aside class="subtitle-sidebar">
          <div class="subtitle-section-heading">
            <h2>媒体文件</h2>
            <span>{{ items.length }} 个</span>
          </div>
          <div class="subtitle-sidebar-tools">
            <label class="subtitle-sidebar-search">
              <span class="subtitle-search-icon" aria-hidden="true"></span>
              <input
                class="subtitle-search"
                :value="query"
                aria-label="搜索本地媒体名称或路径"
                placeholder="搜索媒体"
                @input="query = ($event.currentTarget as HTMLInputElement).value"
                @keyup="searchOnEnter"
                @focus="searchViewport.focus"
                @blur="searchViewport.blur"
              />
              <button
                v-if="query"
                type="button"
                aria-label="清除媒体搜索"
                title="清除媒体搜索"
                @click="query = ''; load()"
              >
                ×
              </button>
            </label>
            <button
              class="subtitle-icon-button subtitle-sidebar-refresh"
              type="button"
              :disabled="loading"
              aria-label="刷新媒体目录"
              title="刷新媒体目录"
              @click="load()"
            >
              ↻
            </button>
          </div>
          <div class="subtitle-list">
            <button
              v-for="item in items"
              :key="item.path"
              :class="[
                'subtitle-media',
                selected?.path === item.path && 'is-active',
              ]"
              :aria-pressed="selected?.path === item.path"
              @click="selectMedia(item)"
            >
              <span class="subtitle-rail" aria-hidden="true"></span>
              <span class="subtitle-media-icon" aria-hidden="true">▶</span>
              <span class="subtitle-media-copy"
                ><strong>{{ mediaName(item) }}</strong
                ><small>{{ item.path }}</small></span
              >
              <span class="subtitle-count"
                >{{ item.subtitles === undefined ? "—" : `${item.subtitles.length} 条` }}</span
              >
            </button>
            <div
              v-if="!items.length"
              class="subtitle-empty subtitle-empty-list"
            >
              {{ loading ? "正在读取媒体记录…" : "暂无可管理媒体" }}
            </div>
          </div>
          <nav class="subtitle-pagination" aria-label="媒体分页">
            <button type="button" :disabled="loading || offset === 0" @click="load(Math.max(0, offset - 100))">上一页</button>
            <span>第 {{ Math.floor(offset / 100) + 1 }} 页</span>
            <button type="button" :disabled="loading || !hasMore" @click="load(offset + 100)">下一页</button>
          </nav>
        </aside>

        <main v-if="selected" class="subtitle-detail">
          <SubtitleMediaSummary :selected="selected" :poster-failed="posterFailed" :media-name="mediaName" @poster-error="posterFailed = true" />

          <div
            :class="[
              'subtitle-content-tabs',
              { 'has-online-tools': activePanel === 'online' },
            ]"
          >
            <div class="subtitle-content-tab-list" role="tablist" aria-label="字幕类型">
              <button
                type="button"
                role="tab"
                :aria-selected="activePanel === 'local'"
                :class="{ 'is-active': activePanel === 'local' }"
                @click="activePanel = 'local'"
              >
                本地字幕
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="activePanel === 'online'"
                :class="{ 'is-active': activePanel === 'online' }"
                @click="activePanel = 'online'"
              >
                在线字幕
              </button>
            </div>
            <button
              v-if="activePanel === 'local'"
              type="button"
              class="subtitle-action is-secondary is-compact subtitle-tab-action"
              aria-haspopup="dialog"
              @click="openUploadDialog"
            >
              上传字幕
            </button>
            <button
              v-else
              type="button"
              class="subtitle-mobile-search-trigger"
              :aria-expanded="mobileSearchOpen"
              aria-label="打开在线字幕搜索"
              @click="toggleMobileSearch"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
            </button>
            <form
              v-if="activePanel === 'online'"
              :class="['subtitle-tab-search-controls', { 'is-mobile-open': mobileSearchOpen }]"
              role="search"
              @submit="mobileSearchOpen = false; searchOnline($event)"
            >
              <label class="subtitle-sidebar-search subtitle-tab-search">
                <span class="subtitle-search-icon" aria-hidden="true"></span>
                <input

                  :value="onlineQuery"
                  ref="onlineSearchInput"
                  @focus="searchViewport.focus"
                  @blur="searchViewport.blur"
                  class="subtitle-search subtitle-online-query"
                  aria-label="在线字幕查询词"
                  placeholder="搜索在线字幕"
                  :disabled="searching"
                  @input="
                    onlineQuery = ($event.currentTarget as HTMLInputElement)
                      .value
                  "
                />
              </label>
              <label
                v-if="selected.identity?.media_type === 'tv'"
                class="subtitle-season-toggle"
              >
                <input
                  :checked="seasonPack"
                  type="checkbox"
                  aria-label="搜索整季字幕包"
                  @change="
                    seasonPack = ($event.currentTarget as HTMLInputElement)
                      .checked
                  "
                />
                整季
              </label>
              <button
                type="submit"
                class="subtitle-online-search-submit"
                :disabled="searching || !onlineQuery.trim()"
              >{{ searching ? "搜索中" : "搜索" }}</button>
            </form>
          </div>

          <section class="subtitle-files-section">
            <SubtitleLocalList v-if="activePanel === 'local'" :selected="selected" :inventory-loading="inventoryLoading"
              :active-action-menu="activeActionMenu" :active-action-menu-above="activeActionMenuAbove"
              :subtitle-format="subtitleFormat" :subtitle-language="subtitleLanguage" :format-size="formatSize"
              :close-action-menu="closeActionMenu" :toggle-action-menu="toggleActionMenu" :load-selection="loadSelection"
              @adjust="activeActionMenu = ''; openAdjustment($event)" @delete="activeActionMenu = ''; openDeleteDialog($event)"
              @search-online="activePanel = 'online'" />

            <div v-else class="subtitle-online-panel">
              <div v-if="searching" class="subtitle-source-progress">
                已启用字幕源正在独立搜索，单个来源失败不会影响其他来源。
              </div>
              <div v-if="sourceStatuses.length" class="subtitle-source-filter">
                <button
                  type="button"
                  :class="['subtitle-source', 'subtitle-source-all', { 'is-active': !activeSource }]"
                  :aria-pressed="!activeSource"
                  title="显示全部字幕源"
                  @click="activeSource = ''"
                >
                  <strong>全部</strong><span>{{ online.length }}</span>
                </button>
                <div
                  :class="[
                    'subtitle-source-scroller',
                    { 'can-scroll-left': sourceCanScrollLeft, 'can-scroll-right': sourceCanScrollRight },
                  ]"
                >
                  <div ref="sourceScroller" class="subtitle-source-list" @scroll="updateSourceOverflow">
                <button
                  v-for="source in sourceStatuses"
                  :key="source.provider"
                  type="button"
                  :class="[
                    'subtitle-source',
                    `is-${source.state}`,
                    { 'is-active': activeSource === source.provider },
                  ]"
                  :aria-pressed="activeSource === source.provider"
                  :title="sourceTitle(source)"
                  @click="selectSource(source.provider, $event)"
                >
                  <i class="subtitle-source-dot" aria-hidden="true"></i>
                  <strong>{{ source.provider }}</strong>
                  <span v-if="sourceState(source)">{{ sourceState(source) }}</span>
                </button>
                  </div>
                </div>
                <div
                  v-if="sourceCanScrollLeft || sourceCanScrollRight"
                  class="subtitle-source-navigation"
                  aria-label="字幕源导航"
                >
                  <button
                    type="button"
                    class="subtitle-source-arrow is-left"
                    aria-label="查看左侧字幕源"
                    :disabled="!sourceCanScrollLeft"
                    @click="scrollSources(-1)"
                  ><span aria-hidden="true"></span></button>
                  <button
                    type="button"
                    class="subtitle-source-arrow is-right"
                    aria-label="查看右侧字幕源"
                    :disabled="!sourceCanScrollRight"
                    @click="scrollSources(1)"
                  ><span aria-hidden="true"></span></button>
                </div>
              </div>

              <div
                v-if="captchaChallenges.length"
                class="subtitle-captcha-list"
              >
                <div
                  v-for="challenge in captchaChallenges"
                  :key="challenge.handle"
                  class="subtitle-captcha-card"
                >
                  <img
                    v-if="challenge.image"
                    :src="challenge.image"
                    class="subtitle-captcha-image"
                    alt="验证码"
                  />
                  <span class="subtitle-captcha-copy">
                    {{ challenge.provider }}：{{ challenge.instruction }}
                  </span>
                  <div class="subtitle-captcha-controls">
                    <input
                      :value="captchaInput"
                      class="subtitle-captcha-input"
                      maxlength="64"
                      autocomplete="off"
                      aria-label="验证码"
                      placeholder="输入验证码"
                      @input="
                        captchaInput = (
                          $event.currentTarget as HTMLInputElement
                        ).value
                      "
                    />
                    <button
                      class="subtitle-action is-primary"
                      :disabled="solvingCaptcha || !captchaInput.trim()"
                      @click="submitCaptcha(challenge)"
                    >
                      {{ solvingCaptcha ? "提交中…" : "提交并继续搜索" }}
                    </button>
                  </div>
                </div>
              </div>

              <div class="subtitle-table subtitle-online-results">
                <div class="subtitle-table-columns subtitle-online-columns" aria-hidden="true">
                  <span>字幕名称</span><span>来源</span><span>语言</span><span>格式</span><span>匹配</span>
                </div>
                <div
                  v-if="online.length && !visibleOnline.length"
                  class="subtitle-table-empty"
                >
                  {{ activeSource }} 暂无匹配字幕，再次点击来源卡可显示全部结果
                </div>
                <div v-else-if="visibleOnline.length" class="subtitle-file-list">
                  <div
                    v-for="item in visibleOnline.slice(0, 20)"
                    :key="item.candidate_handle"
                    class="subtitle-file subtitle-table-row subtitle-online-file"
                  >
                  <span
                    :class="[
                      'subtitle-file-mark',
                      'subtitle-provider-mark',
                      providerClass(item.provider),
                    ]"
                    aria-hidden="true"
                    >{{ providerMark(item.provider) }}</span
                  >
                  <span class="subtitle-file-copy">
                    <strong
                      :title="item.title"
                      :aria-label="item.title"
                      tabindex="0"
                    >{{ item.title }}</strong>
                  </span>
                  <span class="subtitle-mobile-meta">
                    {{ item.provider }} · {{ item.language || "未知" }} ·
                    {{ item.format?.toUpperCase() || "—" }} ·
                    {{ item.score || 0 }} 分
                  </span>
                  <span class="subtitle-file-meta">{{ item.provider }}</span>
                  <span class="subtitle-file-meta">{{ item.language || "未知" }}</span>
                  <span class="subtitle-file-meta">{{ item.format?.toUpperCase() || "—" }}</span>
                  <span class="subtitle-file-meta">{{ item.score || 0 }} 分</span>
                  <span class="subtitle-row-actions" @focusout="closeActionMenu">
                    <button
                      type="button"
                      class="subtitle-action-trigger"
                      :aria-expanded="activeActionMenu === `online:${item.candidate_handle}`"
                      aria-haspopup="menu"
                      :aria-label="`操作 ${item.title}`"
                      title="更多操作"
                      @click="toggleActionMenu(`online:${item.candidate_handle}`, $event)"
                    >⋮</button>
                    <span
                      v-if="activeActionMenu === `online:${item.candidate_handle}`"
                      :class="['subtitle-row-action-menu', { 'is-above': activeActionMenuAbove }]"
                      role="menu"
                    >
                      <button
                        type="button"
                        role="menuitem"
                        class="subtitle-download-action"
                        :disabled="!item.downloadable || previewing"
                        @click="activeActionMenu = ''; previewOnline(item.candidate_handle)"
                      >{{ previewing && selectedCandidate === item.candidate_handle ? "下载中…" : "下载并预览" }}</button>
                      <a
                        v-if="item.url"
                        :href="item.url"
                        target="_blank"
                        rel="noopener noreferrer"
                        role="menuitem"
                        @click="activeActionMenu = ''"
                      >查看来源</a>
                    </span>
                  </span>
                  </div>
                </div>
                <div v-else class="subtitle-table-empty">
                  <strong>{{ searching ? "正在搜索在线字幕" : "暂无在线字幕" }}</strong>
                  <span>{{ searching ? "正在等待各字幕源返回结果" : "输入关键词后搜索，结果会显示在这里" }}</span>
                </div>
              </div>

              <div v-if="previewCaptcha" class="subtitle-captcha-list">
                <div class="subtitle-captcha-card">
                  <img
                    v-if="previewCaptcha.image"
                    :src="previewCaptcha.image"
                    class="subtitle-captcha-image"
                    alt="下载验证码"
                  />
                  <span class="subtitle-captcha-copy">
                    {{ previewCaptcha.provider }}：{{ previewCaptcha.instruction }}
                  </span>
                  <div class="subtitle-captcha-controls">
                    <input
                      :value="captchaInput"
                      class="subtitle-captcha-input"
                      maxlength="64"
                      autocomplete="off"
                      aria-label="下载验证码"
                      placeholder="输入验证码"
                      @input="
                        captchaInput = (
                          $event.currentTarget as HTMLInputElement
                        ).value
                      "
                    />
                    <button
                      class="subtitle-action is-primary"
                      :disabled="solvingCaptcha || !captchaInput.trim()"
                      @click="submitCaptcha(previewCaptcha)"
                    >
                      {{ solvingCaptcha ? "提交中…" : "提交并继续预览" }}
                    </button>
                  </div>
                </div>
              </div>

              <div v-if="manualActions.length" class="subtitle-manual-actions">
                <span>该来源需手动处理：</span>
                <a
                  v-for="action in manualActions"
                  :key="`${action.provider}:${action.url}`"
                  :href="action.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  >{{ action.provider }} · {{ action.reason }}</a
                >
              </div>
            </div>
          </section>
        </main>
        <main v-else class="subtitle-detail">
          <div class="subtitle-empty subtitle-empty-files">
            <strong>请选择媒体文件</strong
            ><small>从左侧列表选择需要管理字幕的媒体</small>
          </div>
        </main>
      </div>
    </div>
    <SubtitleUploadDialog ref="uploadDialog" :dialog-component="props.dialogComponent" :upload-panel-open="uploadPanelOpen"
      :uploading="uploading" :selected="selected" :file="file" :error="error" :languages="languages"
      :media-name="mediaName" :close-upload-dialog="closeUploadDialog" :upload="upload" :choose-file="chooseFile"
      v-model:language="language" />
    <SubtitlePreviewDialog  :dialog-component="props.dialogComponent" :preview-items="previewItems" :saving-preview="savingPreview"
      :preview-selected="previewSelected" :preview-provider="previewProvider" :close-preview-dialog="closePreviewDialog"
      :toggle-all-previews="toggleAllPreviews" :toggle-preview="togglePreview" :confirm-preview="confirmPreview"
      v-model:active-preview-index="activePreviewIndex" />
    <SubtitleAdjustmentDialog  :dialog-component="props.dialogComponent" :adjusting-subtitle="adjustingSubtitle" :adjusting="adjusting"
      :adjustment-error="adjustmentError" :close-adjustment="closeAdjustment" :submit-adjustment="submitAdjustment"
      v-model:adjustment-seconds="adjustmentSeconds" />
    <SubtitleDeleteDialog  :dialog-component="props.dialogComponent" :deleting-subtitle="deletingSubtitle" :deleting="deleting"
      :delete-error="deleteError" :close-delete-dialog="closeDeleteDialog" :remove-subtitle="removeSubtitle" />
  </section>
</template>

<style src="./subtitle-workspace.css"></style>
