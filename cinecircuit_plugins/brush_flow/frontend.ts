import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import SiteTrafficView from "./SiteTrafficView.vue";
import "../_shared/ui-consistency.css";

const PLUGIN_ID = "brush-flow";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  const Page = defineComponent({
    name: "SiteTrafficPage",
    setup() {
      return () => h(SiteTrafficView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });

  sdk.registerPage({ pluginId: PLUGIN_ID, route: `plugin-${PLUGIN_ID}`, title: "站点刷流", icon: "mdi-water-sync", section: "tools", order: 74, component: Page });
}
