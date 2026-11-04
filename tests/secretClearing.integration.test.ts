import { shallowMount } from "@vue/test-utils";
import { defineComponent } from "vue";
import { expect, it, vi } from "vitest";
import CookieCloud from "../cinecircuit_plugins/cookiecloud/ConnectionEditor.vue";
import OnlineSources from "../cinecircuit_plugins/subtitle_manager/OnlineSourcesEditor.vue";
import RecycleCleaner from "../cinecircuit_plugins/storage_recycle_cleaner/ConfigEditor.vue";
import SavedSecretField from "../cinecircuit_plugins/_shared/SavedSecretField.vue";

const TextField = defineComponent({ name: "VTextField", emits: ["update:modelValue"], template: "<div />" });
const Schema = defineComponent({ template: "<div />" });
const requester = vi.fn(async () => ({ value: "fixture-secret" })) as never;

it("CookieCloud marks user key and password deletion while preserving untouched credentials", () => {
  const wrapper = shallowMount(CookieCloud, { global: { stubs: { VSwitch: true, VTextField: TextField, VSelect: true } }, props: { modelValue: { user_key: "old-user", password: "", enabled: true }, request: requester } });
  expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  wrapper.findComponent(SavedSecretField).vm.$emit("update:modelValue", "");
  expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ password: "", password_clear: true, user_key: "old-user" });
  wrapper.findComponent({ name: "VTextField" }).vm.$emit("update:modelValue", "");
  expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ user_key: "", user_key_clear: true });
  wrapper.unmount();
});

it("subtitle credentials clear on deletion and reset the clear marker on replacement", () => {
  const wrapper = shallowMount(OnlineSources, { props: { modelValue: { online_providers: ["assrt"], assrt_api_key: "" }, fields: [{ key: "assrt_api_key", secret: true }], schemaFieldsComponent: Schema, request: requester } });
  const field = wrapper.findComponent(SavedSecretField);
  field.vm.$emit("update:modelValue", "");
  expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ assrt_api_key: "", assrt_api_key_clear: true });
  field.vm.$emit("update:modelValue", "new-key");
  expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ assrt_api_key: "new-key", assrt_api_key_clear: false });
  wrapper.unmount();
});

it("recycle cleaner marks an emptied saved password for deletion", () => {
  const wrapper = shallowMount(RecycleCleaner, { props: { modelValue: { password: "" }, fields: [{ key: "password", secret: true }], schemaFieldsComponent: Schema, request: requester } });
  wrapper.findComponent(SavedSecretField).vm.$emit("update:modelValue", "");
  expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ password: "", password_clear: true });
  wrapper.unmount();
});
