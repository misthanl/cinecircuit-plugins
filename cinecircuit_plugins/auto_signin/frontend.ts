import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import AutoSigninPageView from "./AutoSigninPage.vue";
import StatisticsView from "./StatisticsView.vue";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Alert, Button, Card, Dialog } = sdk.ui.components;
  const Page = defineComponent({
    name: "SiteCheckinPage",
    inheritAttrs: false,
    setup() {
      return () => h(AutoSigninPageView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });

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

  sdk.registerPage({ pluginId: "auto-signin", route: "plugin-auto-signin", title: "自动签到", icon: "mdi-calendar-check-outline", section: "tools", order: 72, component: Page });
  sdk.registerContribution({ pluginId: "auto-signin", slot: "plugin.statistics", key: "site-results", component: Statistics });
}
