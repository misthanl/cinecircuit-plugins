import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";
import "../_shared/ui-consistency.css";

const ID = "douban-wish";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Button, Card, Dialog, Alert } = sdk.ui.components;
  const Statistics = defineComponent({
    name: "DoubanWishStatistics",
    inheritAttrs: false,
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup(props, { attrs }) {
      return () => h(StatisticsView, {
        ...attrs,
        context: props.context,
        request: sdk.request,
        imageComponent: sdk.ui.components.Image,
        buttonComponent: Button,
        cardComponent: Card,
        dialogComponent: Dialog,
        alertComponent: Alert,
      });
    },
  });
  sdk.registerContribution({ pluginId: ID, slot: "plugin.statistics", key: "subscriptions", component: Statistics });
}
