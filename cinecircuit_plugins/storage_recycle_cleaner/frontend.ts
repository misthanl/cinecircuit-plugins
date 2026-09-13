import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import ConfigEditor from "./ConfigEditor.vue";
import StatisticsView from "./StatisticsView.vue";
import "../_shared/ui-consistency.css";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const { Button, Card, Dialog, Chip, Alert } = sdk.ui.components;
  sdk.registerContribution({
    pluginId: "storage-recycle-cleaner", slot: "plugin.statistics", key: "overview",
    component: defineComponent({
      props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
      setup(props) {
        return () => h(StatisticsView, {
          context: props.context, request: sdk.request, buttonComponent: Button,
          cardComponent: Card, dialogComponent: Dialog, chipComponent: Chip, alertComponent: Alert,
        });
      },
    }),
  });
  const schemaFields = sdk.ui.components.SchemaFields;
  if (!schemaFields) throw new Error("请更新主程序以使用公共配置表单");
  sdk.registerEditor({
    domain: "plugin", key: "storage-recycle-cleaner",
    component: defineComponent({
      inheritAttrs: false,
      props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
      emits: ["update:modelValue"],
      setup(props, { attrs, emit }) {
        return () => h(ConfigEditor, {
          ...attrs, modelValue: props.modelValue, disabled: props.disabled,
          request: sdk.request, schemaFieldsComponent: schemaFields,
          "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
        });
      },
    }),
  });
}
