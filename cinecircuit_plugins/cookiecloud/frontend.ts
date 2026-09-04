import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import ConnectionEditorView from "./ConnectionEditor.vue";
import StatisticsView from "./StatisticsView.vue";

const ID = "cookiecloud";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Button, Card, Dialog, Chip, Alert } = sdk.ui.components;
  const Statistics = defineComponent({
    name: "CookieCloudStatistics",
    inheritAttrs: false,
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup(props, { attrs }) {
      return () => h(StatisticsView, {
        ...attrs,
        context: props.context,
        request: sdk.request,
        buttonComponent: Button,
        cardComponent: Card,
        dialogComponent: Dialog,
        chipComponent: Chip,
        alertComponent: Alert,
      });
    },
  });
  const ConnectionEditor = defineComponent({
    name: "CookieCloudConnectionEditor",
    inheritAttrs: false,
    props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
    emits: ["update:modelValue"],
    setup(props, { attrs, emit }) {
      return () => h(ConnectionEditorView, {
        ...attrs,
        disabled: props.disabled,
        modelValue: props.modelValue,
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
        "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
      });
    },
  });
  sdk.registerEditor({ domain: "plugin", key: ID, component: ConnectionEditor });
  sdk.registerEditor({ domain: "plugin", key: `${ID}:connection`, component: ConnectionEditor });
  sdk.registerContribution({ pluginId: ID, slot: "plugin.statistics", key: "overview", component: Statistics });
}
