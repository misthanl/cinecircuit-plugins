import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import AutoSigninPageView from "./AutoSigninPage.vue";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const Page = defineComponent({
    name: "SiteCheckinPage",
    inheritAttrs: false,
    setup() {
      return () => h(AutoSigninPageView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });

  sdk.registerPage({ pluginId: "auto-signin", route: "plugin-auto-signin", title: "自动签到", icon: "mdi-calendar-check-outline", section: "tools", order: 72, component: Page });
}
