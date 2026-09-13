import { mount } from "@vue/test-utils";
import { defineComponent, nextTick } from "vue";
import { createVuetify } from "vuetify";
import { VApp, VCard, VDialog, VListItem, VSelect, VSwitch, VTextField } from "vuetify/components";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import RunEditor from "../cinecircuit_plugins/media_cover_generator/RunEditor.vue";
import { appDialogScrollStrategy } from "../../cinecircuit/frontend/src/appDialogScrollStrategy";

const CronFixture = defineComponent({
  props: { modelValue: { type: [String, Number], default: "" } },
  template: '<input class="cron-fixture" :value="modelValue">',
});

describe("media cover mobile editor integration", () => {
  beforeAll(() => {
    globalThis.ResizeObserver = class ResizeObserver {
      observe(): void { /* test shim */ }
      unobserve(): void { /* test shim */ }
      disconnect(): void { /* test shim */ }
    };
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: () => ({ matches: true }),
    });
    const viewport = Object.assign(new EventTarget(), {
      width: 390,
      height: 500,
      offsetLeft: 0,
      offsetTop: 0,
      pageLeft: 0,
      pageTop: 0,
      scale: 1,
      onresize: null,
      onscroll: null,
    });
    Object.defineProperty(globalThis, "visualViewport", { configurable: true, value: viewport });
  });

  beforeEach(() => {
    document.body.innerHTML = '<main class="app-main"></main>';
  });

  it("selects the first real media server after focusing delay and preserves dialog scrolling", async () => {
    const request = async () => ({
      servers: [
        { title: "家庭 Emby", value: "server-1" },
        { title: "备用 Jellyfin", value: "server-2" },
      ],
      libraries: [],
      errors: [],
    });
    const Harness = defineComponent({
      components: { RunEditor, VApp, VCard, VDialog },
      data: () => ({ open: true, config: { delay: 60, selected_servers: [] as string[] } }),
      setup: () => ({ request, CronFixture }),
      template: '<VApp><VDialog v-model="open" scrollable><VCard><RunEditor v-model="config" :request="request" :cron-field-component="CronFixture" /></VCard></VDialog></VApp>',
    });
    const vuetify = createVuetify({
      components: { VApp, VCard, VDialog, VListItem, VSelect, VSwitch, VTextField },
      defaults: {
        VDialog: { scrollStrategy: appDialogScrollStrategy },
        VSelect: { menuProps: { maxHeight: 320 } },
      },
    });
    const wrapper = mount(Harness, { attachTo: document.body, global: { plugins: [vuetify] } });
    await nextTick();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();

    const delay = document.querySelector<HTMLInputElement>('.cover-run-settings input[type="number"]');
    const select = document.querySelector<HTMLElement>('.target-servers .v-field');
    if (!delay || !select) throw new Error("real media cover controls did not mount");
    delay.focus();
    select.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerType: "touch" }));
    select.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    select.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await nextTick();

    const menu = document.querySelector('.v-overlay-container .v-select__content');
    expect(menu).not.toBeNull();
    expect(document.querySelector('.target-servers .v-select__content')).toBeNull();
    const first = [...document.querySelectorAll<HTMLElement>('.v-overlay-container .v-list-item')]
      .find((item) => item.textContent?.includes("家庭 Emby"));
    if (!first) throw new Error("real media server option did not open in the overlay layer");
    first.click();
    await nextTick();
    expect(wrapper.vm.config.selected_servers).toEqual(["server-1"]);

    const content = document.querySelector<HTMLElement>('.v-dialog .v-card');
    if (!content) throw new Error("dialog content did not mount");
    const touchmove = new Event("touchmove", { bubbles: true, cancelable: true });
    content.dispatchEvent(touchmove);
    expect(touchmove.defaultPrevented).toBe(false);
    expect(document.querySelector(".app-main")?.hasAttribute("inert")).toBe(true);
    wrapper.unmount();
  });

});
