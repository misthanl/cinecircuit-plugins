import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  sdk.registerContribution?.({ pluginId: "torrent-transfer", slot: "plugin.statistics", key: "seeding-statistics", component: defineComponent({
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup() { return () => h(StatisticsView, { pluginId: "torrent-transfer", request: sdk.request,
      cardComponent: sdk.ui.components.Card, buttonComponent: sdk.ui.components.Button, alertComponent: sdk.ui.components.Alert }); },
  }) });
}
