import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import SubtitleWorkspacePageView from "./SubtitleWorkspacePage.vue";
import OnlineSourcesEditor from "./OnlineSourcesEditor.vue";
import StatisticsView from "./StatisticsView.vue";
import type { PropType } from "vue";
import "../_shared/ui-consistency.css";

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h } = sdk.vue;
  sdk.registerContribution?.({ pluginId: "subtitle-manager", slot: "plugin.statistics", key: "overview", component: defineComponent({
    props: { context: { type: Object as PropType<{ close: () => void }>, required: true } },
    setup(props) { return () => h(StatisticsView, { context: props.context, request: sdk.request,
      dialogComponent: sdk.ui.components.Dialog, cardComponent: sdk.ui.components.Card, buttonComponent: sdk.ui.components.Button }); },
  }) });
  const SchemaFields = sdk.ui?.components?.SchemaFields;
  if (SchemaFields) {
    sdk.registerEditor({ domain: "plugin", key: "subtitle-manager:online", component: defineComponent({
      inheritAttrs: false,
      props: { modelValue: { type: Object as PropType<Record<string, unknown>>, required: true }, disabled: Boolean },
      emits: ["update:modelValue"],
      setup(props, { attrs, emit }) {
        return () => h(OnlineSourcesEditor, { ...attrs, modelValue: props.modelValue, disabled: props.disabled,
          request: sdk.request, schemaFieldsComponent: SchemaFields,
          "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value) });
      },
    }) });
  }
  const Page = defineComponent({
    name: "SubtitleWorkspacePage",
    inheritAttrs: false,
    setup() {
      return () => h(SubtitleWorkspacePageView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
        alertComponent: sdk.ui?.components?.Alert,
        dialogComponent: sdk.ui.components.Dialog,
      });
    },
  });

  sdk.registerPage({ pluginId: "subtitle-manager", route: "plugin-subtitle-manager", title: "字幕管理", icon: "mdi-subtitles-outline", section: "tools", order: 65, component: Page });
}
