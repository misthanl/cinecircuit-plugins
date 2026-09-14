import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import StatisticsView from "./StatisticsView.vue";
import CopyWorkspace from "./CopyWorkspace.vue";
import ConfigEditor from "./ConfigEditor.vue";
import "../_shared/ui-consistency.css";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  const Workspace = defineComponent({
    props: { context: { type: Object as PropType<PluginContributionContext> }, page: Boolean },
    setup: props => () => h(StatisticsView, {context: props.context, page: props.page, request: sdk.request,
      dialogComponent: sdk.ui.components.Dialog, cardComponent: sdk.ui.components.Card, buttonComponent: sdk.ui.components.Button}),
  });
  sdk.registerContribution({pluginId: "cloud-copy", slot: "plugin.statistics", key: "copies", component: Workspace});
  sdk.registerPage({pluginId: "cloud-copy", route: "plugin-cloud-copy", title: "跨网盘复制", icon: "mdi-content-copy", section: "tools", order: 66,
    component: defineComponent({setup: () => () => h(CopyWorkspace, {request: sdk.request, buttonComponent: sdk.ui.components.Button, dialogComponent: sdk.ui.components.Dialog, cardComponent: sdk.ui.components.Card})})});
  const SchemaFields = sdk.ui.components.SchemaFields;
  if (SchemaFields) sdk.registerEditor({domain: "plugin", key: "cloud-copy", component: defineComponent({
    inheritAttrs: false,
    props: {modelValue: {type: Object as PropType<Record<string, unknown>>, required: true}, fields: {type: Array, default: () => []}, disabled: Boolean},
    emits: ["update:modelValue"],
    setup: (props, {emit}) => () => h(ConfigEditor, {modelValue: props.modelValue, fields: props.fields as Array<{key:string}>, disabled: props.disabled,
      schemaFieldsComponent: SchemaFields, request: sdk.request, "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value)}),
  })});
}
