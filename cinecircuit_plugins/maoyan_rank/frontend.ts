import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";
import RankEditor from "./RankEditor.vue";
import "../_shared/ui-consistency.css";

const ID = "maoyan-rank";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Button, Card, Dialog, Alert } = sdk.ui.components;
  const fields = sdk.ui.components.SchemaFields;
  if (fields) sdk.registerEditor({
    domain: "plugin", key: ID,
    component: defineComponent({
      inheritAttrs: false,
      props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
      emits: ["update:modelValue"],
      setup(props, { attrs, emit }) {
        return () => h(RankEditor, {
          ...attrs, modelValue: props.modelValue, disabled: props.disabled, schemaFieldsComponent: fields,
          loadConfig: sdk.request ? async (signal: AbortSignal) => {
            // Read installation metadata: unlike plugin APIs, this also works while disabled.
            const result = await sdk.request<{ items: { id: string; config: Record<string, unknown> }[] }>("/plugins/", { signal });
            const item = result.items.find(item => item.id === ID);
            if (!item) throw new Error("插件配置不存在");
            return item.config;
          } : undefined,
          "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
        });
      },
    }),
  });
  const Statistics = defineComponent({
    name: "MaoyanStatistics",
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
