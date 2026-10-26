import { mount, flushPromises } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { beforeAll, expect, it, vi } from "vitest";
import SeedStatistics from "../cinecircuit_plugins/_shared/SeedStatistics.vue";

beforeAll(() => {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });
});

it("uses existing CC/Vuetify components for totals, pagination and error-safe text", async () => {
  const request = vi.fn().mockResolvedValue({ counts: { seeding: 3, checking: 1 }, items: [
    { id: "one", name: "Sample", status: "checking", hash: "abc", error: "<script>bad</script>", timestamp: 100 },
  ] });
  const wrapper = mount(SeedStatistics, { props: { pluginId: "torrent-transfer", request,
    cardComponent: components.VCard, buttonComponent: components.VBtn, alertComponent: components.VAlert },
    global: { plugins: [createVuetify({ components })] } });
  await flushPromises();
  expect(wrapper.findComponent(components.VDataTable).exists()).toBe(true);
  expect(wrapper.text()).toContain("Sample");
  expect(wrapper.find("script").exists()).toBe(false);
  expect(wrapper.findComponent(components.VDataTable).props("itemsPerPage")).toBe(10);
  const refresh = wrapper.findAll("button").find(button => button.text() === "刷新");
  await refresh?.trigger("click"); await flushPromises();
  expect(request).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});
