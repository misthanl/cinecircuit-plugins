import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { test } from "node:test";
import { installSelectStub } from '../../tests/select-stub.mjs';

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/brush_flow/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
installSelectStub(vue,require('@vue/test-utils').config);
require('@vue/test-utils').config.global.components.VBtn = vue.defineComponent({ inheritAttrs: false, props: ['disabled', 'loading'], setup: (props, { attrs, slots }) => () => vue.h('button', { ...attrs, disabled: props.disabled || props.loading }, slots.default?.()) });

for (const name of ['VIcon', 'VDialog', 'VCard', 'VCardText', 'VCardActions', 'VTabs', 'VTab', 'VList']) {
  require('@vue/test-utils').config.global.components[name] = vue.defineComponent({
    name, props: ['modelValue'], setup: (_props, { slots }) => () => vue.h('div', slots.default?.()),
  });
}
require('@vue/test-utils').config.global.components.VMenu = vue.defineComponent({
  name: 'VMenu', props: ['activator', 'location', 'closeOnContentClick'],
  setup: (_props, { slots }) => () => vue.h('div', slots.default?.()),
});
require('@vue/test-utils').config.global.components.VListItem = vue.defineComponent({
  name: 'VListItem', inheritAttrs: false, props: ['title', 'disabled', 'baseColor'],
  setup: (props, { attrs }) => () => vue.h('button', { ...attrs, disabled: props.disabled }, props.title),
});

const SchemaFields = vue.defineComponent({
  name: 'SchemaFieldsFixture', props: ['fields', 'modelValue', 'disabled'], emits: ['update:modelValue'],
  setup: props => () => vue.h('div', (props.fields || []).map(field => vue.h('span', field.label || field.key))),
});
const UiButton = vue.defineComponent({ inheritAttrs: false, props: ['loading'], setup: (props, { attrs, slots }) => () => vue.h('button', { ...attrs, disabled: props.loading }, slots.default?.()) });
const UiContainer = vue.defineComponent({ setup: (_props, { slots }) => () => vue.h('div', slots.default?.()) });

function editor(request, modelValue, disabled = false) {
  let registration;
  install({ vue, request, ui: { components: { SchemaFields } }, registerPage() {},
    registerEditor(value) { registration = value; } });
  assert.equal(registration.domain, 'plugin');
  assert.equal(registration.key, 'brush-flow');
  return mount(registration.component, { props: { modelValue, disabled }, attrs: {
    fields: ['enabled', 'cron', 'cleanup_enabled', 'notification_enabled', 'max_tasks', 'allow_delete_files'].map(key => ({ key })),
  } });
}

function button(wrapper, label) { return wrapper.findAll('button').find(item => item.text() === label); }
function group(wrapper, key) { return wrapper.findAllComponents(SchemaFields).find(item => item.props('fields').some(field => field.key === key)); }
const inventory = async () => ({ sites: [{ id: 's1', name: '测试站点', capabilities: ['feed'] }], downloaders: [{ id: 'd1', name: '下载器一' }] });

test('summary shows global controls once and task routing', async () => {
  const wrapper = editor(inventory, { tasks: [{ id: 'r1', name: '夜间刷流', site_id: 's1', downloader_id: 'd1', interval_minutes: 15 }] });
  await flushPromises();
  assert.match(wrapper.text(), /测试站点/);
  assert.match(wrapper.text(), /下载器一/);
  assert.match(wrapper.text(), /每 15 分钟/);
  assert.equal(wrapper.findAll('.traffic-config > .global-heading').length, 1);
  assert.match(wrapper.find('.traffic-config > .global-heading').text(), /统一控制刷流任务/);
  assert.deepEqual(group(wrapper, 'enabled').props('fields').map(field => field.key), ['enabled', 'max_tasks']);
  assert.equal(wrapper.findAllComponents(SchemaFields).length, 1);
  wrapper.unmount();
});

test('adding opens an isolated draft and cancel creates nothing', async () => {
  const wrapper = editor(inventory, { tasks: [] });
  await flushPromises();
  await button(wrapper, '添加任务').trigger('click');
  assert.ok(group(wrapper, 'name'));
  group(wrapper, 'name').vm.$emit('update:modelValue', { name: '未保存' });
  await vue.nextTick();
  await wrapper.find('[aria-label="关闭任务编辑"]').trigger('click');
  assert.equal(wrapper.emitted('update:modelValue'), undefined);
  wrapper.unmount();
});

test('editing inherits old defaults and commits only when confirmed', async () => {
  const wrapper = editor(inventory, { unknown: 7, default_site_id: 's1', default_downloader_id: 'd1', cleanup_enabled: true, allow_delete_files: true,
    tasks: [{ id: 'r1', name: '旧任务', custom: 'keep' }] });
  await flushPromises();
  await button(wrapper, '编辑任务').trigger('click');
  assert.equal(group(wrapper, 'name').props('modelValue').allow_delete_files, true);
  group(wrapper, 'name').vm.$emit('update:modelValue', { name: '修改任务' });
  await vue.nextTick();
  assert.equal(wrapper.emitted('update:modelValue'), undefined);
  await button(wrapper, '确认修改').trigger('click');
  const result = wrapper.emitted('update:modelValue').at(-1)[0];
  assert.equal(result.unknown, 7);
  assert.equal(result.tasks[0].name, '修改任务');
  assert.equal(result.tasks[0].site_id, 's1');
  assert.equal(result.tasks[0].cleanup_enabled, true);
  assert.equal(result.tasks[0].custom, 'keep');
  await wrapper.setProps({ modelValue: result });
  assert.match(wrapper.text(), /修改任务/);
  assert.equal(wrapper.findAllComponents(SchemaFields).length, 1);
  wrapper.unmount();
});

test('incomplete task is not committed and disabled editor cannot add', async () => {
  const wrapper = editor(inventory, { tasks: [] });
  await flushPromises();
  await button(wrapper, '添加任务').trigger('click');
  await wrapper.findAll('button').filter(item => item.text() === '添加任务').at(-1).trigger('click');
  assert.match(wrapper.text(), /请填写任务名称并选择 PT 站点/);
  assert.equal(wrapper.emitted('update:modelValue'), undefined);
  wrapper.unmount();
  const disabled = editor(inventory, { tasks: [] }, true);
  await flushPromises();
  assert.equal(button(disabled, '添加任务').attributes('disabled'), '');
  disabled.unmount();
});


test('new task produces summary only after confirmation and invalid cron is rejected', async () => {
  const wrapper = editor(inventory, { tasks: [] });
  await flushPromises();
  await button(wrapper, '添加任务').trigger('click');
  group(wrapper, 'name').vm.$emit('update:modelValue', { name: '新增计划', site_id: 's1', cron: 'wrong' });
  await vue.nextTick();
  await wrapper.findAll('button').filter(item => item.text() === '添加任务').at(-1).trigger('click');
  assert.equal(wrapper.emitted('update:modelValue'), undefined);
  assert.match(wrapper.text(), /有效的 5 位 Cron/);
  group(wrapper, 'cron').vm.$emit('update:modelValue', { cron: '*/15 * * * *' });
  await vue.nextTick();
  await wrapper.findAll('button').filter(item => item.text() === '添加任务').at(-1).trigger('click');
  const saved = wrapper.emitted('update:modelValue').at(-1)[0];
  assert.equal(saved.tasks[0].name, '新增计划');
  assert.equal(saved.tasks[0].allow_delete_files, true);
  await wrapper.setProps({ modelValue: saved });
  assert.equal(wrapper.findAllComponents(SchemaFields).length, 1);
  assert.match(wrapper.text(), /新增计划/);
  wrapper.unmount();
});


test('adding a task works without secure-context crypto APIs', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  try {
    for (const crypto of [undefined, {}]) {
      Object.defineProperty(globalThis, 'crypto', { configurable: true, value: crypto });
      const wrapper = editor(inventory, { tasks: [] });
      try {
        await flushPromises();
        await button(wrapper, '添加任务').trigger('click');
        assert.ok(group(wrapper, 'name'));
        const firstId = group(wrapper, 'name').props('modelValue').id;
        assert.match(firstId, /^task-/);
        await wrapper.find('[aria-label="关闭任务编辑"]').trigger('click');
        await button(wrapper, '添加任务').trigger('click');
        assert.notEqual(group(wrapper, 'name').props('modelValue').id, firstId);
      } finally { wrapper.unmount(); }
    }
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor);
    else delete globalThis.crypto;
  }
});


test('task limits tab preserves rates and volume and routes invalid values', async () => {
  const wrapper = editor(inventory, { tasks: [] });
  await flushPromises();
  await button(wrapper, '添加任务').trigger('click');
  assert.equal(group(wrapper, 'max_add'), undefined);
  group(wrapper, 'name').vm.$emit('update:modelValue', { name: '限速任务', site_id: 's1' });
  const tabs = wrapper.findComponent({ name: 'VTabs' });
  tabs.vm.$emit('update:modelValue', 'limits');
  await vue.nextTick();
  assert.match(wrapper.text(), /任务限制/);
  const limits = group(wrapper, 'max_add');
  assert.ok(limits.props('fields').some(field => field.key === 'seeding_limit_gib'));
  limits.vm.$emit('update:modelValue', { upload_limit_kib: -1, download_limit_kib: 200, seeding_limit_gib: 100.5 });
  await vue.nextTick();
  await wrapper.findAll('button').filter(item => item.text() === '添加任务').at(-1).trigger('click');
  assert.equal(wrapper.emitted('update:modelValue'), undefined);
  assert.match(wrapper.text(), /限速须为非负整数/);
  group(wrapper, 'max_add').vm.$emit('update:modelValue', { upload_limit_kib: 100 });
  await vue.nextTick();
  await wrapper.findAll('button').filter(item => item.text() === '添加任务').at(-1).trigger('click');
  const saved = wrapper.emitted('update:modelValue').at(-1)[0].tasks[0];
  assert.equal(saved.upload_limit_kib, 100);
  assert.equal(saved.download_limit_kib, 200);
  assert.equal(saved.seeding_limit_gib, 100.5);
  wrapper.unmount();
});


test('task cards expose the six limits in compact grid', async () => {
  const wrapper = editor(inventory, { max_tasks: 30, tasks: [{ id: 'r1', name: '容量任务', seeding_limit_gib: 500, upload_limit_kib: 2048, download_limit_kib: 0 }] });
  await flushPromises();
  assert.equal(wrapper.findAll('.task-card dl > div').length, 6);
  assert.match(wrapper.text(), /500 GiB/);
  assert.match(wrapper.text(), /2,048 KiB\/s/);
  assert.match(wrapper.text(), /不限速/);
  assert.equal(wrapper.findAllComponents({ name: 'VMenu' }).length, 1);
  wrapper.unmount();
});

test('task action menu uses the host menu pattern', async () => {
  const wrapper = editor(inventory, { tasks: [{ id: 'r1', name: '菜单任务' }] });
  await flushPromises();
  const menu = wrapper.getComponent({ name: 'VMenu' });
  assert.equal(menu.props('activator'), 'parent');
  assert.equal(menu.props('location'), 'bottom end');
  assert.equal(menu.props('closeOnContentClick'), true);
  assert.equal(wrapper.get('[aria-label="更多任务操作"]').exists(), true);
  assert.equal(button(wrapper, '移除任务').exists(), true);
  wrapper.unmount();
});

test('statistics use real response, filter, paginate and show unavailable values', async () => {
  let contribution;
  const task = { id:'r1',name:'统计任务',site_id:'s1',downloader_id:'d1',enabled:true,seeding_limit_gib:1,interval_minutes:5,cron:'',download_count:2,seed_count:3,upload_speed:1024,download_speed:2048,size:1024,uploaded:4096,downloaded:2048,available:true,history_complete:true };
  const report = { tasks:[task], history:Array.from({length:10},(_,i)=>({id:String(i),task_id:'r1',name:'统计任务',site_id:'s1',timestamp:1000+i,added:2,cleaned:0,skipped:4,failed:i===0?1:0,matched:6,reason:i===0?'部分失败':'成功'})),updated_at:1000,enabled:true };
  const request = async path => path.endsWith('/statistics') ? structuredClone(report) : inventory();
  install({vue,request,ui:{components:{SchemaFields,Button:UiButton,Card:UiContainer,Dialog:UiContainer}},registerEditor(){},registerContribution(value){contribution=value;}});
  assert.equal(contribution.slot, 'plugin.statistics');
  let closed = false;
  const wrapper=mount(contribution.component, { props: { context: { close() { closed = true; } } } });
  await flushPromises();
  assert.match(wrapper.text(), /4 KiB/);
  assert.match(wrapper.text(), /2.00/);
  assert.equal(wrapper.findAll('tbody tr').length, 8);
  await wrapper.find('[aria-label="最后一页"]').trigger('click');
  assert.equal(wrapper.findAll('tbody tr').length, 2);
  const page=wrapper.find('[aria-label="页码"]');
  await page.setValue(99); await page.trigger('change');
  assert.equal(page.element.value, '2');
  await button(wrapper,'有异常').trigger('click');
  assert.equal(wrapper.findAll('tbody tr').length, 1);
  await wrapper.find('td button').trigger('click');
  assert.match(wrapper.find('.execution-detail').text(), /失败 1/);
  report.tasks=[{...task,available:false,history_complete:false}];
  await button(wrapper,'刷新').trigger('click'); await flushPromises();
  assert.match(wrapper.text(), /当前占用和速度显示为 —/);
  // Partial history retains recorded totals; missing totals are not presented as zero.
  assert.match(wrapper.find('.stat-totals').text(), /4 KiB/);
  report.tasks = [{ ...task, uploaded: 0, downloaded: 0, available: false, history_complete: false }];
  await button(wrapper, '刷新').trigger('click'); await flushPromises();
  assert.deepEqual(wrapper.findAll('.stat-totals strong').map(value => value.text()), ['—', '—', '—', '—']);
  await wrapper.find('[aria-label="关闭"]').trigger('click');
  assert.equal(closed, true);
  wrapper.unmount();
});

test('reopening the editor restores persisted tasks from inventory', async () => {
  const persisted = { id: 'saved', name: '已保存任务', site_id: 's1', downloader_id: 'd1' };
  const wrapper = editor(async () => ({ sites: [], downloaders: [], tasks: [persisted] }), { tasks: [] });
  await flushPromises();
  const restored = wrapper.emitted('update:modelValue').at(-1)[0];
  assert.deepEqual(restored.tasks, [persisted]);
  await wrapper.setProps({ modelValue: restored });
  assert.match(wrapper.text(), /已保存任务/);
  wrapper.unmount();
});
