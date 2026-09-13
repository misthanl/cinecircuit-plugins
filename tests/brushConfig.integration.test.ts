import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent } from "vue";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { beforeAll, expect, it } from "vitest";
import ConfigEditor from "../cinecircuit_plugins/brush_flow/ConfigEditor.vue";
import SchemaFields from "../../cinecircuit/frontend/src/components/SchemaDrivenFields.vue";

beforeAll(() => {
  Object.defineProperty(globalThis, "visualViewport", { configurable: true, value: { addEventListener() {}, removeEventListener() {}, width: 1024, height: 768, offsetLeft: 0, offsetTop: 0 } });
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });
});

it("edits real schema fields and uses Vuetify site availability", async () => {
  const request = async () => ({ sites: [
    { id: "yes", name: "可用", capabilities: ["latest"] },
    { id: "no", name: "未配置站点", capabilities: [] },
  ], downloaders: [] });
  const Harness = defineComponent({
    components: { ConfigEditor, VApp: components.VApp },
    data: () => ({ config: { tasks: [{ id: "one", name: "任务一", site_id: "yes", include: "", custom: true, cleanup_enabled: false, allow_delete_files: false, delete_task: false }] } }),
    setup: () => ({ request, SchemaFields }),
    template: '<VApp><ConfigEditor v-model="config" :request="request" :schema-fields-component="SchemaFields" /></VApp>',
  });
  const wrapper = mount(Harness, { attachTo: document.body, global: { plugins: [createVuetify({ components })] } });
  await flushPromises();
  await wrapper.findAllComponents(components.VBtn).find(button => button.text() === "编辑任务")!.trigger("click");
  await flushPromises();
  const site = wrapper.findAllComponents(components.VSelect).find(field => field.props("label") === "任务 PT 站点")!;
  expect(site.props("items")).toMatchObject([{ props: { disabled: false } }, { props: { disabled: true } }]);
  await wrapper.findAllComponents(components.VTab).find(tab => tab.text() === "选种规则")!.trigger("click");
  const include = wrapper.findAllComponents(components.VTextField).find(field => field.props("label") === "包含规则（正则）")!;
  await include.get("input").setValue("WEB-DL");
  expect(wrapper.vm.config.tasks[0].include).toBe("");
  await wrapper.findAllComponents(components.VBtn).find(button => button.text() === "确认修改")!.trigger("click");
  expect(wrapper.vm.config.tasks[0]).toMatchObject({ include: "WEB-DL", custom: true, cleanup_enabled: false, allow_delete_files: false, delete_task: false });
  wrapper.unmount();
});


it("clicks add, switches, real site menu, numeric rules, and remove without randomUUID", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis.crypto, "randomUUID");
  Object.defineProperty(globalThis.crypto, "randomUUID", { configurable: true, value: undefined });
  const Harness = defineComponent({
    components: { ConfigEditor, VApp: components.VApp },
    data: () => ({ config: { tasks: [] as Record<string, unknown>[] } }),
    setup: () => ({ SchemaFields, request: async () => ({ sites: [{ id: "site", name: "无需 RSS", capabilities: ["latest"] }], downloaders: [] }) }),
    template: '<VApp><ConfigEditor v-model="config" :request="request" :schema-fields-component="SchemaFields" /></VApp>',
  });
  const wrapper = mount(Harness, { attachTo: document.body, global: { plugins: [createVuetify({ components })] } });
  try {
    await flushPromises();
    await wrapper.findAllComponents(components.VBtn).find(button => button.text() === '添加任务')!.trigger('click');
    await flushPromises();
    expect(wrapper.vm.config.tasks).toHaveLength(0);
    const toggle = wrapper.findAllComponents(components.VSwitch).find(field => field.props('label') === '启用此任务')!;
    await toggle.get('input').setValue(false);
    const site = wrapper.findAllComponents(components.VSelect).find(field => field.props('label') === '任务 PT 站点')!;
    await site.get('.v-field').trigger('mousedown');
    await flushPromises();
    const option = [...document.querySelectorAll('.v-list-item')].find(node => node.textContent?.includes('无需 RSS')) as HTMLElement;
    expect(option).toBeTruthy();
    option.click();
    await flushPromises();
    const name = wrapper.findAllComponents(components.VTextField).find(field => field.props('label') === '任务名称')!;
    await name.get('input').setValue('新任务');
    await wrapper.findAllComponents(components.VTab).find(tab => tab.text() === '删种规则')!.trigger('click');
    const numeric = wrapper.findAllComponents(components.VTextField).find(field => field.props('label') === '上传量达到后处理（GiB）')!;
    await numeric.get('input').setValue('12');
    expect(wrapper.vm.config.tasks).toHaveLength(0);
    await wrapper.findAllComponents(components.VBtn).find(button => button.text() === '添加任务' && button.classes().includes('app-action-button') && button.element.closest('.traffic-dialog-actions'))!.trigger('click');
    await flushPromises();
    expect(wrapper.vm.config.tasks[0]).toMatchObject({ name: '新任务', enabled: false, site_id: 'site' });
    expect(Number(wrapper.vm.config.tasks[0].delete_upload_gib)).toBe(12);
    await wrapper.get('[aria-label="更多任务操作"]').trigger('click');
    await flushPromises();
    const remove = [...document.querySelectorAll('.v-list-item')].find(node => node.textContent?.includes('移除任务')) as HTMLElement;
    remove.click();
    await flushPromises();
    expect(wrapper.vm.config.tasks).toHaveLength(0);
  } finally {
    wrapper.unmount();
    if (original) Object.defineProperty(globalThis.crypto, 'randomUUID', original);
    else delete (globalThis.crypto as Partial<Crypto>).randomUUID;
  }
});
