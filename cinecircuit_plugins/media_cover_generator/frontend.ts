import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import type { PropType } from "vue";
import LibraryArtworkView from "./LibraryArtworkView.vue";
import StyleEditorView from "./StyleEditor.vue";
import RunEditorView from "./RunEditor.vue";
import HistoryView from "./HistoryView.vue";
import "../_shared/ui-consistency.css";

const ID = "emby-cover-generator";

export function install(sdk: CineCircuitPluginSdk): void {
  const { defineComponent, h } = sdk.vue;
  sdk.registerContribution?.({pluginId:ID,slot:'plugin.statistics',key:'cover-history',component:defineComponent({
    props:{context:{type:Object,required:true}},
    setup(props){return ()=>h(HistoryView,{context:props.context as {close:()=>void},request:sdk.request,dialogComponent:sdk.ui.components.Dialog,cardComponent:sdk.ui.components.Card,buttonComponent:sdk.ui.components.Button});}
  })});
  const Page = defineComponent({
    name: "LibraryArtworkPage",
    setup() {
      return () => h(LibraryArtworkView, {
        request: <T,>(path: string, init?: RequestInit) => sdk.request<T>(path, init),
      });
    },
  });
  const StyleEditor = defineComponent({
    name: "LibraryArtworkStyleEditor",
    inheritAttrs: false,
    props: {
      modelValue: { type: Object as PropType<Record<string, unknown>>, required: true },
      disabled: Boolean,
    },
    emits: ["update:modelValue"],
    setup(props, { attrs, emit }) {
      return () => h(StyleEditorView, {
        ...attrs,
        modelValue: props.modelValue,
        request: (path: string, init?: RequestInit) => sdk.request(path, init),
        disabled: props.disabled,
        "onUpdate:modelValue": (value: Record<string, unknown>) => emit("update:modelValue", value),
      });
    },
  });

  sdk.registerPage({ pluginId: ID, route: `plugin-${ID}`, title: "视觉封面", icon: "mdi-image-multiple-outline", section: "tools", order: 80, component: Page });
  sdk.registerEditor({ domain: "plugin", key: `${ID}:style`, component: StyleEditor });
  sdk.registerEditor({ domain: "plugin", key: `${ID}:run`, component: defineComponent({
    inheritAttrs:false,
    props:{modelValue:{type:Object as PropType<Record<string,unknown>>,required:true},disabled:Boolean},
    emits:['update:modelValue'],
    setup(props,{emit}){return ()=>h(RunEditorView,{modelValue:props.modelValue,disabled:props.disabled,request:sdk.request,cronFieldComponent:sdk.ui.components.CronField,'onUpdate:modelValue':(value:Record<string,unknown>)=>emit('update:modelValue',value)});}
  }) });
}
