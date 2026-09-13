import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import ConfigEditor from "./ConfigEditor.vue";
import StatisticsView from "./StatisticsView.vue";
import "../_shared/ui-consistency.css";

const PLUGIN_ID = "brush-flow";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  const fields = sdk.ui?.components.SchemaFields;
  const { Button, Card, Dialog } = sdk.ui.components;
  sdk.registerContribution?.({ pluginId: PLUGIN_ID, slot: "plugin.statistics", key: "traffic-statistics", component: defineComponent({
    inheritAttrs: false,
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup(props) { return () => h(StatisticsView, {
      context: props.context, request: sdk.request,
      buttonComponent: Button, cardComponent: Card, dialogComponent: Dialog,
    }); },
  }) });
  if (fields) sdk.registerEditor({
    domain: "plugin", key: PLUGIN_ID,
    component: defineComponent({
      inheritAttrs: false,
      props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
      emits: ["update:modelValue"],
      setup(props, { attrs, emit }) {
        return () => h(ConfigEditor, {
          ...attrs, modelValue: props.modelValue, disabled: props.disabled,
          request: sdk.request, schemaFieldsComponent: fields,
          "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
        });
      },
    }),
  });
}
