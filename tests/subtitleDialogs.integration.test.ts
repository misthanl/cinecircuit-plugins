import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createVuetify } from "vuetify";
import { VBtn, VSelect } from "vuetify/components";
import { beforeAll, expect, it, vi } from "vitest";
import UploadDialog from "../cinecircuit_plugins/subtitle_manager/SubtitleUploadDialog.vue";
import AdjustmentDialog from "../cinecircuit_plugins/subtitle_manager/SubtitleAdjustmentDialog.vue";
import DeleteDialog from "../cinecircuit_plugins/subtitle_manager/SubtitleDeleteDialog.vue";
import PreviewDialog from "../cinecircuit_plugins/subtitle_manager/SubtitlePreviewDialog.vue";

beforeAll(() => {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});
const Dialog = defineComponent({
  props: { modelValue: Boolean, persistent: Boolean },
  emits: ["update:modelValue"],
  setup: (props, { slots }) => () => props.modelValue ? h("div", slots.default?.()) : null,
});
const global = { plugins: [createVuetify({ components: { VBtn, VSelect } })] };

it("upload keeps the host close button, file reset, language updates and persistence", async () => {
  const closeUploadDialog = vi.fn(), chooseFile = vi.fn(), upload = vi.fn(async () => {});
  const wrapper = mount(UploadDialog, { global, props: {
    dialogComponent: Dialog, uploadPanelOpen: true, uploading: false, selected: { path: "movie.mkv" },
    file: null, error: "", languages: [["auto", "自动识别"], ["en", "英语"]], language: "auto",
    mediaName: item => item.path, closeUploadDialog, chooseFile, upload,
  } });
  expect(wrapper.findAll(".app-dialog-close")).toHaveLength(1);
  await wrapper.get(".app-dialog-close").trigger("click");
  expect(closeUploadDialog).toHaveBeenCalledOnce();
  const input = wrapper.get<HTMLInputElement>('input[type="file"]');
  Object.defineProperty(input.element, "value", { configurable: true, writable: true, value: "subtitle.srt" });
  await input.trigger("change");
  expect(chooseFile).toHaveBeenCalledOnce();
  wrapper.vm.resetInput();
  expect(input.element.value).toBe("");
  wrapper.getComponent(VSelect).vm.$emit("update:modelValue", "en");
  expect(wrapper.emitted("update:language")).toEqual([["en"]]);
  await wrapper.setProps({ uploading: true });
  expect(wrapper.getComponent(Dialog).props("persistent")).toBe(true);
  expect(wrapper.get(".app-dialog-close").attributes("disabled")).toBeDefined();
  wrapper.unmount();
});

it("adjustment emits typed numeric input and keeps the close action disabled during save", async () => {
  const wrapper = mount(AdjustmentDialog, { global, props: {
    dialogComponent: Dialog, adjustingSubtitle: { name: "one.srt" }, adjusting: false,
    adjustmentError: "", adjustmentSeconds: "0", closeAdjustment: vi.fn(), submitAdjustment: vi.fn(async () => {}),
  } });
  await wrapper.get('input[type="number"]').setValue("-1.5");
  expect(wrapper.emitted("update:adjustmentSeconds")).toEqual([["-1.5"]]);
  await wrapper.setProps({ adjusting: true });
  expect(wrapper.getComponent(Dialog).props("persistent")).toBe(true);
  expect(wrapper.get(".app-dialog-close").attributes("disabled")).toBeDefined();
  wrapper.unmount();
});

it("delete retains explicit submit and reports errors without adding cancellation controls", async () => {
  const removeSubtitle = vi.fn(async (event?: Event) => { event?.preventDefault(); });
  const wrapper = mount(DeleteDialog, { global, props: {
    dialogComponent: Dialog, deletingSubtitle: { name: "one.srt" }, deleting: false,
    deleteError: "重试", closeDeleteDialog: vi.fn(), removeSubtitle,
  } });
  expect(wrapper.get('[role="alert"]').text()).toBe("重试");
  expect(wrapper.findAll(".app-dialog-close")).toHaveLength(1);
  expect(wrapper.text()).not.toContain("取消");
  await wrapper.get("form").trigger("submit");
  expect(removeSubtitle).toHaveBeenCalledOnce();
  wrapper.unmount();
});

it("preview selection remains independent from its dialog close role", async () => {
  const togglePreview = vi.fn();
  const wrapper = mount(PreviewDialog, { global, props: {
    dialogComponent: Dialog, previewItems: [0, 1].map(index => ({ index, name: `${index}.srt`, language: "en", format: "SRT", bytes: 12, excerpt: `line ${index}` })),
    activePreviewIndex: 0, previewSelected: [0], savingPreview: false, previewProvider: "Synthetic",
    closePreviewDialog: vi.fn(), toggleAllPreviews: vi.fn(), togglePreview, confirmPreview: vi.fn(async () => {}),
  } });
  expect(wrapper.findAll(".app-dialog-close")).toHaveLength(1);
  expect(wrapper.findAll('input[type="checkbox"].app-dialog-close')).toHaveLength(0);
  await wrapper.findAll(".subtitle-preview-file-open")[1].trigger("click");
  expect(wrapper.emitted("update:activePreviewIndex")).toEqual([[1]]);
  await wrapper.findAll('.subtitle-preview-file input[type="checkbox"]')[1].setValue(true);
  expect(togglePreview).toHaveBeenCalledWith(1, true);
  wrapper.unmount();
});
