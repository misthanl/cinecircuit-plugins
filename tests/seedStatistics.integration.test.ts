import { mount, flushPromises } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { beforeAll, expect, it, vi } from "vitest";
import { defineComponent, h, markRaw } from "vue";
import SeedStatistics from "../cinecircuit_plugins/_shared/SeedStatistics.vue";

beforeAll(() => {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });
});

it("uses existing CC/Vuetify components for totals, pagination and error-safe text", async () => {
  // The host owns overlay placement; keep the actual table/card/button components here.
  const Dialog = defineComponent({ props: { modelValue: Boolean },
    setup: (props, { slots }) => () => props.modelValue ? h("section", { role: "dialog" }, slots.default?.()) : null });
  const request = vi.fn().mockResolvedValue({ counts: { seeding: 3, checking: 1 }, items: [
    { id: "one", name: "Sample", status: "checking", hash: "abc", error: "<script>bad</script>", timestamp: 100 },
  ] });
  const wrapper = mount(SeedStatistics, { props: { pluginId: "torrent-transfer", request,
    context: { installation: { name: "转移做种" }, close: vi.fn() }, dialogComponent: markRaw(Dialog),
    cardComponent: markRaw(components.VCard), buttonComponent: markRaw(components.VBtn), alertComponent: markRaw(components.VAlert) },
    global: { plugins: [createVuetify({ components })] } });
  await flushPromises();
  await vi.waitFor(() => expect(wrapper.findComponent(components.VDataTable).exists()).toBe(true));
  expect(wrapper.text()).toContain("Sample");
  expect(wrapper.find("script").exists()).toBe(false);
  expect(wrapper.findComponent(components.VDataTable).props("itemsPerPage")).toBe(10);
  const refresh = wrapper.findAll("button").find(button => button.text() === "刷新");
  await refresh?.trigger("click"); await flushPromises();
  expect(request).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});
