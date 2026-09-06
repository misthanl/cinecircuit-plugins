import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import SubtitleWorkspacePageView from "./SubtitleWorkspacePage.vue";
import "../_shared/ui-consistency.css";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const Page = defineComponent({
    name: "SubtitleWorkspacePage",
    inheritAttrs: false,
    setup() {
      return () => h(SubtitleWorkspacePageView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });

  sdk.registerPage({ pluginId: "subtitle-manager", route: "plugin-subtitle-manager", title: "字幕大师", icon: "mdi-subtitles-outline", section: "tools", order: 65, component: Page });
}
