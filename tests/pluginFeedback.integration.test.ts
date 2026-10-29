import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { expect, it } from "vitest";
import StatisticsView from "../cinecircuit_plugins/brush_flow/StatisticsView.vue";
import { pluginErrorText } from "../cinecircuit_plugins/_shared/request-feedback";

const Container = defineComponent({ setup(_, { slots }) { return () => h("section", slots.default?.()); } });

it("does not duplicate host warnings or leave statistics permanently loading", async () => {
  const failure = Object.assign(new Error("插件尚未启用"), { notificationHandled: true });
  const wrapper = mount(StatisticsView, {
    props: {
      context: { close() {}, configure() {} },
      request: async () => { throw failure; },
      buttonComponent: Container, cardComponent: Container, dialogComponent: Container,
    },
    global: { stubs: { VSelect: true } },
  });
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(wrapper.text()).not.toContain("正在读取统计");
  expect(wrapper.text()).toContain("暂无统计数据");
  wrapper.unmount();
});

it("keeps standalone plugin failures visible when no host notification was delivered", () => {
  expect(pluginErrorText(new Error("读取失败"), "fallback")).toBe("读取失败");
  expect(pluginErrorText(null, "fallback")).toBe("fallback");
});
