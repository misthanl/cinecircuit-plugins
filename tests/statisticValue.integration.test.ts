import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import StatisticValue from "../cinecircuit_plugins/_shared/StatisticValue.vue";

it("uses a quiet missing value while retaining real zero and formatted metrics", async () => {
  const wrapper = mount(StatisticValue, { props: { value: "—" } });
  expect(wrapper.find(".plugin-statistic-placeholder").attributes("aria-label")).toBe("暂无数据");
  await wrapper.setProps({ value: 0 });
  expect(wrapper.text()).toBe("0");
  expect(wrapper.find(".plugin-statistic-placeholder").exists()).toBe(false);
  await wrapper.setProps({ value: "622.6 GiB" });
  expect(wrapper.text()).toBe("622.6 GiB");
  wrapper.unmount();
});
