<script setup lang="ts">
import SeedStatistics from "../_shared/SeedStatistics.vue";
import type { Component } from "vue";
const props = defineProps<{ pluginId: string; request: <T>(path: string, init?: RequestInit) => Promise<T>; cardComponent: Component; buttonComponent: Component; alertComponent: Component }>();
</script>
<template><SeedStatistics :plugin-id="props.pluginId" :request="props.request" :card-component="props.cardComponent" :button-component="props.buttonComponent" :alert-component="props.alertComponent" /></template>
