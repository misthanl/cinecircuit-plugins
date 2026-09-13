<script setup lang="ts">
import type { MediaItem } from "./workspaceTypes";
defineProps<{ selected: MediaItem; posterFailed: boolean; mediaName: (item: MediaItem) => string | undefined }>();
const emit = defineEmits<{ posterError: [] }>();
function identityParts(item: MediaItem) {
  const value = item.identity || {};
  return [
    value.media_type === "tv"
      ? "剧集"
      : value.media_type === "movie"
        ? "电影"
        : "类型未知",
    value.year,
    value.season != null && value.episode != null
      ? `S${String(value.season).padStart(2, "0")}E${String(value.episode).padStart(2, "0")}`
      : "",
    value.tmdb_id ? `TMDB ${value.tmdb_id}` : "",
    value.imdb_id ? `IMDb ${value.imdb_id}` : "",
  ].filter(Boolean);
}
</script>
<template>
          <header class="subtitle-detail-heading">
            <div class="subtitle-poster" aria-hidden="true">
              <img
                v-if="selected.poster_url && !posterFailed"
                :src="selected.poster_url"
                alt=""
                @error="emit('posterError')"
              />
              <span v-else>影视</span>
            </div>
            <div class="subtitle-detail-copy">
              <h2>{{ selected.title || mediaName(selected) || "字幕详情" }}</h2>
              <p>{{ selected.path }}</p>
              <div class="subtitle-identity" aria-label="结构化媒体身份">
                <span
                  v-for="part in identityParts(selected)"
                  :key="String(part)"
                  >{{ part }}</span
                >
                <small v-if="selected.identity?.aliases?.length"
                  >别名：{{ selected.identity.aliases.join(" / ") }}</small
                >
              </div>
              <p
                v-for="warning in selected.identity?.warnings || []"
                :key="warning"
                class="subtitle-identity-warning"
              >
                {{ warning }}
              </p>
            </div>
            <div class="subtitle-summary-actions">
              <div class="subtitle-local-stat">
                <span>本地字幕</span>
                <strong>{{ selected.subtitles === undefined ? "—" : `${selected.subtitles.length} 条` }}</strong>
              </div>
            </div>
          </header>
</template>
