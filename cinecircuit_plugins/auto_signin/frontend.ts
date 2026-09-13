import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";
import "../_shared/ui-consistency.css";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Alert, Button, Card, Dialog } = sdk.ui.components;

  const Statistics = defineComponent({
    name: "SiteCheckinStatistics",
    inheritAttrs: false,
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup(props, { attrs }) {
      return () => h(StatisticsView, {
        ...attrs,
        context: props.context,
        request: sdk.request,
        alertComponent: Alert,
        buttonComponent: Button,
        cardComponent: Card,
        dialogComponent: Dialog,
      });
    },
  });

  sdk.registerContribution({ pluginId: "auto-signin", slot: "plugin.statistics", key: "site-results", component: Statistics });
}
