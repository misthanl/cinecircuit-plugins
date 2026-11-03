import { mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import { VIcon } from "vuetify/components";
import { expect, it } from "vitest";
import StatisticsTaskCard from "../cinecircuit_plugins/brush_flow/StatisticsTaskCard.vue";
import type { StatisticsTask } from "../cinecircuit_plugins/brush_flow/statistics-types";

function card(overrides: Partial<StatisticsTask> = {}, globalEnabled = true) {
  const task: StatisticsTask = {
    id: "sky", name: "天空", site_id: "sky", downloader_id: "qb", enabled: true,
    seeding_limit_gib: 2, interval_minutes: 10, cron: "", download_count: 0,
    seed_count: 3, upload_speed: 1024, download_speed: 0, size: 1024 ** 3,
    uploaded: 4096, downloaded: 2048, available: true, history_complete: true,
    ...overrides,
  };
  return mount(StatisticsTaskCard, {
    props: { task, siteName: "天空", downloaderName: "qb", globalEnabled, formatBytes: value => `${value} B` },
    global: { plugins: [createVuetify({ components: { VIcon } })] },
  });
}

it("keeps the icon-free summary compact and reveals real live metrics on demand", async () => {
  const wrapper = card();
  try {
    const toggle = wrapper.get(".stat-task-toggle");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".stat-task-details").exists()).toBe(false);
    expect(toggle.findAllComponents(VIcon)).toHaveLength(1); // Only the disclosure arrow.
    expect(wrapper.get(".stat-task-metadata").text()).toContain("天空 → qb");
    await toggle.trigger("click");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get(".stat-task-details").attributes("id")).toBe(toggle.attributes("aria-controls"));
    expect(wrapper.findAll(".stat-task-metrics dd").map(node => node.text())).toEqual(["0", "3", "1024 B/s", "0 B/s"]);
    expect(wrapper.get("progress").attributes("value")).toBe("50");
    expect(wrapper.find(".stat-task-note").exists()).toBe(false);
    await toggle.trigger("click");
    expect(wrapper.find(".stat-task-details").exists()).toBe(false);
  } finally { wrapper.unmount(); }
});

it("preserves unknown values and updates an expanded card when live data recovers", async () => {
  const wrapper = card({ available: false, history_complete: false });
  try {
    expect(wrapper.get(".stat-task-metadata").text()).toContain("保种 — / 2 GiB");
    await wrapper.get(".stat-task-toggle").trigger("click");
    expect(wrapper.findAll(".stat-task-metrics dd").map(node => node.text())).toEqual(["—", "—", "—", "—"]);
    expect(wrapper.find("progress").exists()).toBe(false);
    expect(wrapper.get(".stat-task-note").text()).toContain("历史累计统计仍保留");
    await wrapper.setProps({ task: { ...wrapper.props("task"), available: true, download_count: 2 } });
    expect(wrapper.get(".stat-task-toggle").attributes("aria-expanded")).toBe("true");
    expect(wrapper.findAll(".stat-task-metrics dd")[0].text()).toBe("2");
    expect(wrapper.find(".stat-task-note").exists()).toBe(false);
  } finally { wrapper.unmount(); }
});

it("respects global pause and removed tasks while retaining their live statistics", async () => {
  const wrapper = card({}, false);
  try {
    expect(wrapper.classes()).toContain("paused");
    expect(wrapper.get(".stat-task-status").text()).toBe("已停用");
    expect(wrapper.get(".stat-task-metadata").text()).toContain("调度已停止");
    await wrapper.setProps({ globalEnabled: true });
    expect(wrapper.get(".stat-task-status").text()).toBe("已启用");
    await wrapper.setProps({ task: { ...wrapper.props("task"), removed: true } });
    expect(wrapper.get(".stat-task-status").text()).toBe("已移除");
    expect(wrapper.classes()).toContain("paused");
    await wrapper.get(".stat-task-toggle").trigger("click");
    expect(wrapper.findAll(".stat-task-metrics dd")[1].text()).toBe("3");
  } finally { wrapper.unmount(); }
});
