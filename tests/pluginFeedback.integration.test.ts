import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { expect, it } from "vitest";
import StatisticsView from "../cinecircuit_plugins/brush_flow/StatisticsView.vue";
import { pluginErrorText } from "../cinecircuit_plugins/_shared/request-feedback";
import { SubtitleOnlineSession } from "../cinecircuit_plugins/subtitle_manager/onlineWorkspace";
import { reportPluginRequestError, subscribePluginFeedback } from "../../cinecircuit/frontend/src/pluginFeedback";
import { createPageAlertBridge } from "../../cinecircuit/frontend/src/pageAlertBridge";

const Container = defineComponent({ setup(_, { slots }) { return () => h("section", slots.default?.()); } });

it.each(["search", "preview", "captcha"])("subtitle %s failure publishes exactly one host notice", async (operation) => {
  const error = ref("");
  const notices: unknown[] = [];
  const stop = subscribePluginFeedback(notice => notices.push(notice));
  const wrapper = mount(defineComponent({ setup() { return () => h("section", { class: "app-workspace" },
    error.value ? h("div", { class: "v-alert text-error" }, error.value) : []); } }));
  const stopBridge = createPageAlertBridge({ root: wrapper.element, routeKey: () => "subtitle", publish: notice => notices.push(notice) });
  try {
    const session = new SubtitleOnlineSession(async () => {
      const failure = new Error("SubHD 下载超时");
      reportPluginRequestError(failure, "user");
      throw failure;
    }, ref({ path: "movie.mkv" }), error, ref(""));
    if (operation === "preview") await session.preview("candidate");
    else if (operation === "search") await session.search();
    else {
      session.captchaInput.value = "1234";
      await session.submitCaptcha({ handle: "challenge" } as Parameters<typeof session.submitCaptcha>[0]);
    }
    await flushPromises();
    await new Promise(resolve => setTimeout(resolve, 10));
    expect(notices).toHaveLength(1);
    expect(error.value).toBe("");
    expect(wrapper.find(".v-alert").exists()).toBe(false);
    expect(session.previewing.value || session.searching.value || session.solvingCaptcha.value).toBe(false);
  } finally { stopBridge(); stop(); wrapper.unmount(); }
});

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
