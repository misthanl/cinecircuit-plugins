import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import LibraryArtworkView from "./LibraryArtworkView.vue";

const ID = "emby-cover-generator";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  const Page = defineComponent({
    name: "LibraryArtworkPage",
    setup() {
      return () => h(LibraryArtworkView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });

  sdk.registerPage({ pluginId: ID, route: `plugin-${ID}`, title: "视觉封面", icon: "mdi-image-multiple-outline", section: "tools", order: 80, component: Page });
}
