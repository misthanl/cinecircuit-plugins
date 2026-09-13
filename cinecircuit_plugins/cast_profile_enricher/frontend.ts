import type { CineCircuitPluginSdk, PluginContributionContext } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import CastProfileEditorView from "./CastProfileEditor.vue";
import StatisticsView from "./StatisticsView.vue";
import { orderedFields, type ConfigField } from "../_shared/config-fields";
import "../_shared/ui-consistency.css";

const ID = "cast-profile-enricher";

function createEditor(sdk: CineCircuitPluginSdk) {
  return sdk.vue.defineComponent({
    name: "CastProfileEditor",
    inheritAttrs: false,
    props: {
      modelValue: { type: Object as PropType<Record<string, unknown>>, required: true },
      disabled: Boolean,
      fields: { type: Array as PropType<ConfigField[]>, default: () => [] },
    },
    emits: ["update:modelValue"],
    setup(props, { emit }) {
      return () => sdk.ui.components.SchemaFields && props.fields.length
        ? sdk.vue.h(sdk.ui.components.SchemaFields, {
          modelValue: props.modelValue,
          disabled: props.disabled,
          pluginId: ID,
          compact: true,
          class: "standard-config-fields plugin-config-grid app-form-layout",
          fields: orderedFields(props.fields, ["enabled", "cron", "trigger_event", "scrape_delay", "update_biography", "condition", "remove_unresolved", "selected_servers"])
            .map(field => ({ ...field, icon: undefined, disabled: field.disabled || (field.key === "scrape_delay" && !props.modelValue.trigger_event) })),
          "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
        })
        : sdk.vue.h(CastProfileEditorView, {
        modelValue: props.modelValue,
        disabled: props.disabled,
        request: sdk.request,
        cronFieldComponent: sdk.ui.components.CronField,
        "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
      });
    },
  });

}

export function install(sdk: CineCircuitPluginSdk): void {
  const { Alert, Button, Card, Chip, Dialog } = sdk.ui.components;
  sdk.registerEditor({ domain: "plugin", key: ID, component: createEditor(sdk) });
  sdk.registerContribution?.({
    pluginId: ID,
    slot: "plugin.statistics",
    key: "overview",
    component: sdk.vue.defineComponent({
      name: "CastProfileStatistics",
      inheritAttrs: false,
      props: { context: { type: Object as PropType<PluginContributionContext>, required: true } },
      setup(props, { attrs }) {
        return () => sdk.vue.h(StatisticsView, {
          ...attrs,
          context: props.context,
          request: sdk.request,
          alertComponent: Alert,
          buttonComponent: Button,
          cardComponent: Card,
          chipComponent: Chip,
          dialogComponent: Dialog,
        });
      },
    }),
  });
}
