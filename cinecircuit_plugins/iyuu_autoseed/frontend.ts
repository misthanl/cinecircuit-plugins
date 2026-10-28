import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";
import ConfigEditor from "./ConfigEditor.vue";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  const schemaFields = sdk.ui.components.SchemaFields;
  if (schemaFields) sdk.registerEditor({
    domain: "plugin", key: "iyuu-autoseed", component: defineComponent({
      inheritAttrs: false,
      props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
      emits: ["update:modelValue"],
      setup(props, { attrs, emit }) { return () => h(ConfigEditor, {
        ...attrs, modelValue: props.modelValue, disabled: props.disabled,
        request: sdk.request, schemaFieldsComponent: schemaFields,
        "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
      }); },
    }),
  });
  sdk.registerContribution?.({ pluginId: "iyuu-autoseed", slot: "plugin.statistics", key: "seeding-statistics", component: defineComponent({
    inheritAttrs: false,
    props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
    setup(props) { return () => h(StatisticsView, { context: props.context, pluginId: "iyuu-autoseed", request: sdk.request,
      cardComponent: sdk.ui.components.Card, buttonComponent: sdk.ui.components.Button, alertComponent: sdk.ui.components.Alert, dialogComponent: sdk.ui.components.Dialog }); },
  }) });
}
