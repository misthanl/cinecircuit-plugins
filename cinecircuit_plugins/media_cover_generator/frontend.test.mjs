import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";
import { installSelectStub } from '../../tests/select-stub.mjs';

const require = createRequire(resolve("package.json"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>");
for (const key of ["window", "document", "Element", "HTMLElement", "SVGElement", "Node"]) globalThis[key] = dom.window[key];
const vue = require("vue");
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__ = vue;
const { install } = await import("../../.build/cinecircuit_plugins/media_cover_generator/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
installSelectStub(vue,require('@vue/test-utils').config);
require('@vue/test-utils').config.global.stubs.VBtn=true;
for (const name of ['VSwitch', 'VTextField']) {
  require('@vue/test-utils').config.global.components[name] = vue.defineComponent({
    props: ['modelValue', 'label', 'disabled', 'type', 'hideDetails', 'density', 'variant'],
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => vue.h('label', [props.label, vue.h('input', {
      type: name === 'VSwitch' ? 'checkbox' : props.type,
      checked: name === 'VSwitch' ? props.modelValue : undefined,
      value: name === 'VSwitch' ? undefined : props.modelValue,
      disabled: props.disabled,
      onChange: event => emit('update:modelValue', name === 'VSwitch' ? event.target.checked : event.target.value),
    })]),
  });
}

test('cover settings stay compact and desktop history keeps four columns', () => {
  const shared = readFileSync(resolve('cinecircuit_plugins/_shared/ui-consistency.css'), 'utf8');
  const history = readFileSync(resolve('cinecircuit_plugins/media_cover_generator/HistoryView.vue'), 'utf8');
  assert.match(shared, /:is\(\.v-switch, \.v-checkbox, \.v-radio\) \.v-label/);
  assert.match(shared, /font-size: 12px !important/);
  assert.match(shared, /font-weight: 500 !important/);
  assert.match(shared, /font-family: var\(--app-font-family, inherit\) !important/);
  assert.match(shared, /font-size: var\(--app-font-size-control, 14px\)/);
  assert.match(history, /:max-width="920" width="calc\(100vw - 32px\)"/);
  assert.match(history, /\.cover-history \.gallery\{grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(history, /@media\(max-width:600px\)\{\.cover-history \.gallery\{grid-template-columns:1fr\}\}/);
});

test('poster preference defaults on but preserves explicit off', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{}}});
  const preference=()=>wrapper.findAll('label').find(x=>x.text().includes('优先使用海报图')).get('input');
  assert.equal(preference().element.checked,true);
  await preference().setValue(false);
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].use_primary,false);
  await wrapper.setProps({modelValue:{use_primary:false}});
  assert.equal(preference().element.checked,false);
  wrapper.unmount();
});

test('animated wedge restores as a dynamic style without wall direction controls', () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{cover_style_base:'animated_wedge'}}});
  assert.equal(wrapper.get('.base-style-select').element.value,'animated_wedge');
  assert.ok(wrapper.text().includes('动态斜切轮播'));
  assert.equal(wrapper.find('.direction-select').exists(),false);
  assert.equal(wrapper.findAll('.base-style-select option').length,3);
  wrapper.unmount();
});

test('random sorting is first and default without overriding saved sorting', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{}}});
  const field=()=>wrapper.findAll('label').find(x=>x.text().startsWith('媒体排序')).get('select');
  assert.equal(field().element.value,'Random');
  assert.equal(field().findAll('option')[0].attributes('value'),'Random');
  await wrapper.setProps({modelValue:{sort_by:'PremiereDate'}});
  assert.equal(field().element.value,'PremiereDate');
  wrapper.unmount();
});

test('requested background helper text is removed without removing controls', () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{cover_style_base:'diagonal'}}});
  for (const title of ['留白背景','底色占比','横向提亮','磨砂颗粒','背景底色']) {
    const field=wrapper.findAll('.form-grid label').find(item=>item.text().startsWith(title));
    assert.ok(field);
    assert.ok(field.find('input,select').exists());
    assert.equal(field.find('small').exists(),false);
  }
  wrapper.unmount();
});

test('optional style examples appear only while their fields are focused', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{cover_style_base:'diagonal'}}});
  const field=title=>wrapper.findAll('.form-grid label').find(item=>item.text().startsWith(title));
  const background=field('背景底色').get('input');
  const titles=field('媒体库标题配置').get('textarea');
  assert.equal(field('背景底色').classes().includes('label-active'),false);
  assert.equal(field('媒体库标题配置').classes().includes('label-active'),false);
  assert.equal(background.attributes('placeholder') || '','');
  assert.equal(titles.attributes('placeholder') || '','');
  await background.trigger('focus');
  assert.equal(field('背景底色').classes().includes('label-active'),true);
  assert.equal(background.attributes('placeholder'),'留空自动取色，如 #101828');
  await background.trigger('blur');
  assert.equal(field('背景底色').classes().includes('label-active'),false);
  assert.equal(background.attributes('placeholder') || '','');
  await titles.trigger('focus');
  assert.equal(field('媒体库标题配置').classes().includes('label-active'),true);
  assert.equal(titles.attributes('placeholder'),'电影=电影|MOVIES\n剧集=剧集|TV SERIES');
  await titles.trigger('blur');
  assert.equal(field('媒体库标题配置').classes().includes('label-active'),false);
  assert.equal(titles.attributes('placeholder') || '','');
  await wrapper.setProps({modelValue:{cover_style_base:'diagonal',background_color:'#101828',title_config:'电影=电影|MOVIES'}});
  assert.equal(field('背景底色').classes().includes('label-active'),true);
  assert.equal(field('媒体库标题配置').classes().includes('label-active'),true);
  assert.equal(wrapper.emitted('update:modelValue'),undefined);
  wrapper.unmount();
});

test('1080p defaults and packed preview polling preserve chosen dimensions', async () => {
  globalThis.Image = class { naturalWidth=1920; naturalHeight=1080; async decode() {} };
  const calls=[];
  const wrapper=mount(styleEditor(async(path)=>{
    if(path.includes('/sample?')) return {image_words:[0],byte_length:1,mime:'image/webp',width:1920,height:1080};
    calls.push(path);
    return calls.length===1 ? {status:'rendering',preview_id:'a'.repeat(32)} : {status:'complete',image_words:[0],byte_length:1,mime:'image/webp',width:1920,height:1080};
  }),{props:{modelValue:{}}});
  const field=text=>wrapper.findAll('label').find(x=>x.text().startsWith(text));
  assert.equal(field('输出分辨率').get('select').element.value,'1080p');
  await wrapper.setProps({modelValue:{cover_style_base:'animated_diagonal'}});
  assert.equal(field('动态输出分辨率'),undefined);
  assert.equal(wrapper.get('.direction-select').element.value,'up');
  await wrapper.get('.preview-actions button').trigger('click');
  await new Promise(resolve=>setTimeout(resolve,1100));
  await flushPromises();
  assert.ok(calls[1].includes('/preview_status?id='));
  assert.ok(wrapper.get('.sample img').attributes('src').startsWith('blob:'));
  assert.equal(wrapper.get('.sample img').attributes('width'),'1920');
  await wrapper.setProps({modelValue:{cover_style_base:'animated_diagonal',animation_resolution:'640x360'}});
  assert.equal(field('动态输出分辨率'),undefined);
  assert.equal(wrapper.props('modelValue').animation_resolution,'640x360');
  wrapper.unmount();
});

test('cover registers editors and statistics but no main menu page', () => {
  const pages = [], editors = [], contributions = [];
  install({ vue, registerPage: value => pages.push(value), registerEditor: value => editors.push(value), registerContribution: value => contributions.push(value) });
  assert.deepEqual(pages, []);
  assert.deepEqual(editors.map(value => value.key), ['emby-cover-generator:style', 'emby-cover-generator:run']);
  assert.equal(contributions[0].slot, 'plugin.statistics');
});

function styleEditor(request = async () => ({})) {
  let editor;
  install({
    vue,
    request,
    registerPage() {},
    registerEditor: value => { if(value.key.endsWith(':style')) editor = value; },
  });
  assert.equal(editor.key, "emby-cover-generator:style");
  return editor.component;
}

function runEditor() {
  let editor;
  const CronField = vue.defineComponent({
    name: 'CronFieldFixture',
    props: ['modelValue', 'field', 'disabled'],
    emits: ['update:modelValue'],
    template: '<button class="cron-field-fixture" @click="$emit(\'update:modelValue\', \'0 6 * * *\')">cron</button>',
  });
  install({
    vue,
    request: async () => ({}),
    ui: { components: { CronField } },
    registerPage() {},
    registerEditor: value => { if(value.key.endsWith(':run')) editor = value; },
  });
  assert.equal(editor.key, 'emby-cover-generator:run');
  return { component: editor.component, CronField };
}

test('run settings use the host visual Cron selector and preserve the complete config', async () => {
  const { component, CronField } = runEditor();
  const modelValue = { cron: '0 5 * * *', enabled: true, delay: 60 };
  const wrapper = mount(component, { props: { modelValue } });
  const cron = wrapper.getComponent(CronField);
  assert.equal(cron.props('modelValue'), '0 5 * * *');
  assert.equal(cron.props('field').input_type, 'cron');
  assert.equal(cron.props('field').label, '执行周期');

  await cron.trigger('click');

  assert.deepEqual(wrapper.emitted('update:modelValue').at(-1)[0], {
    ...modelValue,
    cron: '0 6 * * *',
  });
  wrapper.unmount();
});

test('run settings replace the scrape switch with an optional ordered event selector', async () => {
  const { component } = runEditor();
  const wrapper = mount(component, { props: { modelValue: { trigger_event: '', delay: 60 } } });
  const selector = wrapper.findAll('label').find(field => field.text().startsWith('触发事件')).get('select');
  assert.deepEqual(selector.findAll('option').map(option => option.text()), [
    '整理完成',
    '同步完成',
    '刮削完成',
  ]);
  assert.equal(wrapper.text().includes('刮削完成后更新封面'), false);
  const source = readFileSync(resolve('cinecircuit_plugins/media_cover_generator/RunEditor.vue'), 'utf8');
  assert.match(source, /:disabled="disabled \|\| !selectedEvent"/);
  await selector.setValue('sync.completed');
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].trigger_event, 'sync.completed');
  wrapper.unmount();
});

test('requested defaults and all nine font names are exposed without replacing saved choices', async () => {
  const wrapper = mount(styleEditor(), {props:{modelValue:{}}});
  const fields = wrapper.findAll('.settings-section label');
  const main = fields.find(field=>field.text().startsWith('主标题字体')).get('select');
  const secondary = fields.find(field=>field.text().startsWith('副标题字体')).get('select');
  assert.equal(main.element.value, 'wendao');
  assert.equal(secondary.element.value, 'emblemaone');
  for (const label of ['文道潮黑','粗雅宋','EmblemaOne','Melete','Phosphate','JosefinSans','LilitaOne','Monoton','Plaster']) {
    assert.ok(wrapper.text().includes(label));
  }
  await wrapper.setProps({modelValue:{zh_font_preset:'cuyasong',en_font_preset:'phosphate'}});
  assert.equal(main.element.value,'cuyasong');
  assert.equal(secondary.element.value,'phosphate');
  wrapper.unmount();
});


test("configuration shows only the selected style and layout preview", async () => {
  globalThis.Image = class { naturalWidth=1280; naturalHeight=720; async decode() {} };
  const sampleRequests=[];
  const wrapper = mount(styleEditor(async path => {
    sampleRequests.push(path);
    return {image_bytes:[0],mime:'image/webp',width:1280,height:720};
  }), {
    props: {
      modelValue: { cover_style_base: "single", cover_style_variant: "1", zh_font_preset: "serif" },
    },
  });
  assert.equal(wrapper.findAll(".sample img").length, 1);
  assert.equal(wrapper.get(".sample img").attributes("alt"), "焦点单图成品封面样例");
  assert.equal(wrapper.findAll(".base-style-select option").length, 11);
  assert.equal(wrapper.find(".variant-section").exists(), false);

  await wrapper.get(".base-style-select").setValue("multi");
  const styleUpdate = wrapper.emitted("update:modelValue").at(-1)[0];
  assert.equal(styleUpdate.cover_style_base, "multi");
  await wrapper.setProps({ modelValue: styleUpdate });
  assert.equal(wrapper.findAll(".variant-select option").length, 4);
  const images = new Set();
  for (const [value, label] of [["1", "八宫格"], ["2", "主次拼贴"], ["3", "左右分镜"], ["4", "三联画"]]) {
    await wrapper.get(".variant-select").setValue(value);
    const updated = wrapper.emitted("update:modelValue").at(-1)[0];
    assert.equal(updated.cover_style_variant, value);
    assert.equal(updated.zh_font_preset, "serif");
    await wrapper.setProps({ modelValue: updated });
    assert.equal(wrapper.findAll(".sample img").length, 1);
    assert.equal(wrapper.get(".sample img").attributes("alt"), `${label}成品封面样例`);
    images.add(wrapper.get(".sample img").attributes("src"));
  }
  for (const [value, label] of [["single", "焦点单图"], ["poster", "海报长廊"], ["animated", "动态轮播"],['diagonal','斜向画廊'],['duo','留白双海报'],['stack','扇形叠卡'],['editorial','杂志拼版'],['panorama','胶片横窗'],['cinema','极简巨幕']]) {
    await wrapper.get('.cover-mode-select').setValue(value.startsWith('animated') ? 'dynamic' : 'static');
    if (wrapper.emitted('update:modelValue')?.length) await wrapper.setProps({modelValue:wrapper.emitted('update:modelValue').at(-1)[0]});
    await wrapper.get(".base-style-select").setValue(value);
    await wrapper.setProps({ modelValue: wrapper.emitted("update:modelValue").at(-1)[0] });
    assert.equal(wrapper.find(".variant-select").exists(), false);
    assert.equal(wrapper.findAll(".sample img").length, 1);
    assert.equal(wrapper.get(".sample img").attributes("alt"), `${label}成品封面样例`);
    await flushPromises();
    images.add(wrapper.get(".sample img").attributes("src"));
  }
  await wrapper.setProps({modelValue:{cover_style_base:'animated_diagonal'}});
  await flushPromises();
  assert.equal(wrapper.get('.sample img').attributes('alt'),'动态斜向海报墙成品封面样例');
  images.add(wrapper.get('.sample img').attributes('src'));
  assert.equal(images.size, 14);
  assert.deepEqual(sampleRequests, ['/plugins/emby-cover-generator/api/sample?style=animated&variant=1','/plugins/emby-cover-generator/api/sample?style=animated_diagonal&variant=1']);
  await wrapper.setProps({modelValue:{cover_style_base:'animated_diagonal',cover_style_variant:'4'}});
  await wrapper.get('.cover-mode-select').setValue('static');
  await wrapper.setProps({modelValue:wrapper.emitted('update:modelValue').at(-1)[0]});
  await wrapper.get(".base-style-select").setValue("multi");
  await wrapper.setProps({ modelValue: wrapper.emitted("update:modelValue").at(-1)[0] });
  assert.equal(wrapper.get(".variant-select").element.value, "4");
  assert.equal(wrapper.get(".sample img").attributes("alt"), "三联画成品封面样例");
  await wrapper.setProps({ disabled: true });
  assert.equal(wrapper.get(".base-style-select").element.disabled, true);
  assert.equal(wrapper.get(".variant-select").element.disabled, true);
  wrapper.unmount();
});

test('current preview sends chosen fonts, material and blur without saving config', async () => {
  globalThis.Image = class { naturalWidth=960; naturalHeight=540; async decode() {} };
  const calls=[];
  const wrapper=mount(styleEditor(async(path,init)=> {
    calls.push({path,init});
    return {image_bytes:[0],mime:'image/jpeg',width:960,height:540};
  }),{props:{modelValue:{cover_style_base:'diagonal',zh_font_preset:'serif',en_font_preset:'editorial',text_finish:'silver',background_mode:'blurred',blur_radius:0}}});
  await wrapper.get('.preview-actions button').trigger('click');
  await flushPromises();
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'/plugins/emby-cover-generator/api/preview');
  assert.equal(JSON.parse(calls[0].init.body).config.zh_font_preset,'serif');
  assert.equal(JSON.parse(calls[0].init.body).config.blur_radius,0);
  assert.ok(wrapper.get('.sample img').attributes('src').startsWith('blob:'));
  await wrapper.setProps({modelValue:{cover_style_base:'diagonal',blur_radius:80}});
  assert.ok(!wrapper.get('.sample img').attributes('src').startsWith('blob:'));
  wrapper.unmount();
});

test('undecodable current preview preserves the displayed image', async () => {
  globalThis.Image = class { async decode() { throw new Error('Broken image'); } };
  const wrapper=mount(styleEditor(async()=>({image_bytes:[1,2,3],mime:'image/jpeg',width:960,height:540})),{props:{modelValue:{}}});
  const original=wrapper.get('.sample img').attributes('src');
  await wrapper.get('.preview-actions button').trigger('click');
  await flushPromises();
  assert.equal(wrapper.get('.sample img').attributes('src'),original);
  assert.ok(wrapper.text().includes('Broken image'));
  wrapper.unmount();
});


test('type selector filters styles, restores each selection and reads saved animated configs', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{cover_style_base:'multi',cover_style_variant:'3',zh_font_preset:'cuyasong'}}});
  const choose=async(selector,value)=>{
    await wrapper.get(selector).setValue(value);
    await wrapper.setProps({modelValue:wrapper.emitted('update:modelValue').at(-1)[0]});
  };
  assert.equal(wrapper.get('.cover-mode-select').element.value,'static');
  assert.equal(wrapper.findAll('.base-style-select option').length,11);
  await choose('.cover-mode-select','dynamic');
  assert.deepEqual(wrapper.findAll('.base-style-select option').map(x=>x.attributes('value')),['animated','animated_diagonal','animated_wedge']);
  await choose('.base-style-select','animated_diagonal');
  await choose('.cover-mode-select','static');
  assert.equal(wrapper.get('.base-style-select').element.value,'multi');
  assert.equal(wrapper.get('.variant-select').element.value,'3');
  await choose('.cover-mode-select','dynamic');
  assert.equal(wrapper.get('.base-style-select').element.value,'animated_diagonal');
  const saved=wrapper.emitted('update:modelValue').at(-1)[0];
  assert.equal(saved.zh_font_preset,'cuyasong');
  wrapper.unmount();
  const reopened=mount(styleEditor(),{props:{modelValue:saved,disabled:true}});
  assert.equal(reopened.get('.cover-mode-select').element.value,'dynamic');
  assert.equal(reopened.get('.base-style-select').element.value,'animated_diagonal');
  assert.ok(reopened.get('.cover-mode-select').element.disabled);
  assert.ok(reopened.get('.base-style-select').element.disabled);
  assert.equal(reopened.findAll('.sample img').length,1);
  reopened.unmount();
});

test('new templates and contextual matte controls preserve zero values and direction', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{cover_style_base:'echo',background_grain:0,background_light:0,background_mix:0}}});
  const field=(text)=>wrapper.findAll('label').find(x=>x.text().startsWith(text));
  assert.equal(wrapper.get('.sample img').attributes('alt'),'扇形叠影成品封面样例');
  assert.equal(field('磨砂颗粒').get('input').element.value,'0');
  assert.equal(field('底色占比').get('input').element.value,'0');
  await wrapper.setProps({modelValue:{cover_style_base:'wedge',background_mode:'solid'}});
  assert.equal(wrapper.get('.sample img').attributes('alt'),'斜切大图成品封面样例');
  assert.equal(field('背景模糊强度'),undefined);
  await wrapper.setProps({modelValue:{cover_style_base:'multi'}});
  assert.equal(field('留白背景'),undefined);
  await wrapper.setProps({modelValue:{cover_style_base:'animated_diagonal',animation_direction:'down'}});
  assert.equal(wrapper.get('.direction-select').element.value,'down');
  await field('中文字号').get('input').setValue('150');
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].animation_direction,'down');
  await wrapper.get('.direction-select').setValue('alternate');
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].animation_direction,'alternate');
  assert.equal(wrapper.findAll('.sample img').length,1);
  wrapper.unmount();
});


test('cover switches follow background color, precede title config and preserve explicit hidden titles', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{}}});
  const group=wrapper.get('.switches');
  assert.deepEqual(group.findAll('label').map(x=>x.text()),['显示媒体库标题','显示媒体数量角标']);
  assert.match(group.element.previousElementSibling.textContent,/优先使用海报图/);
  assert.match(group.element.previousElementSibling.previousElementSibling.textContent,/背景底色/);
  assert.match(group.element.nextElementSibling.textContent,/媒体库标题配置/);
  const toggle=()=>wrapper.get('.switches').findAll('input')[0];
  assert.equal(toggle().element.checked,true);
  await toggle().setValue(false);
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].show_library_title,false);
  await wrapper.setProps({modelValue:{show_library_title:false,title_config:'Saved=Title|SUBTITLE'}});
  assert.equal(toggle().element.checked,false);
  assert.equal(wrapper.get('textarea').element.value,'Saved=Title|SUBTITLE');
  wrapper.unmount();
});


function historyFixture(request,notify) {
  const Shell=vue.defineComponent({props:['modelValue'],setup:(p,{slots})=>()=>p.modelValue===false?null:vue.h('section',slots.default?.())});
  const Card=vue.defineComponent({setup:(_,{slots})=>()=>vue.h('div',slots.default?.())});
  const Button=vue.defineComponent({props:['loading','disabled'],setup:(p,{slots,attrs})=>()=>vue.h('button',{...attrs,disabled:p.disabled||p.loading},slots.default?.())});
  const Confirm=vue.defineComponent({name:'FixtureConfirm',props:['open','loading','title'],emits:['confirm','cancel'],setup:(p,{slots,emit})=>()=>p.open?vue.h('section',{class:'fixture-confirm'},[p.title,slots.default?.(),vue.h('button',{class:'confirm',disabled:p.loading,onClick:()=>emit('confirm')},'Confirm')]):null});
  const Detail=vue.defineComponent({name:'FixtureDetail',props:['modelValue','title','kind'],emits:['update:modelValue'],setup:(p,{slots,emit})=>()=>p.modelValue?vue.h('section',{class:'fixture-detail'},[p.title,slots.default?.(),vue.h('button',{class:'close',onClick:()=>emit('update:modelValue',false)},'Close')]):null});
  let contribution;
  install({vue,request,ui:{notify,components:{Dialog:Shell,Card,Button,BaseDialog:Detail,ConfirmDialog:Confirm}},registerEditor(){},registerContribution:v=>contribution=v});
  globalThis.IntersectionObserver=class{observe(){}disconnect(){}};
  globalThis.URL.createObjectURL=()=> 'blob:cover-fixture';
  globalThis.URL.revokeObjectURL=()=>{};
  return mount(contribution.component,{props:{context:{close(){}}},global:{components:{
    VMenu:{template:'<div><slot name="activator" :props="{}"/><slot/></div>'},
    VList:{template:'<div><slot/></div>'},
    VListItem:vue.defineComponent({props:['title'],setup:p=>()=>vue.h('button',p.title)}),
    VDivider:{template:'<hr>'},VCheckboxBtn:{template:'<input type="checkbox">'},VProgressLinear:{template:'<progress/>'},
  }}});
}
const historyRow={id:'one',name:'Movies',server_id:'server',server_name:'Emby',library_id:'library',created_at:'2026-11-24T01:00:00Z',status:'updated',style:'diagonal',format:'jpeg',resolution:'1920×1080',bytes:100,animated:false};
function historyResponse(path){return path.includes('history_image')?{image_words:[],byte_length:0,mime:'image/jpeg'}:{items:[historyRow],limit:50,counts:{uploaded:1}};}

test('history uses shared preview and confirmation, guards duplicate apply and notifies after success',async()=>{
  let finish;let applied=0;const notices=[];
  const wrapper=historyFixture(async path=>{if(path.endsWith('history_apply')){applied++;return new Promise(resolve=>finish=resolve);}return historyResponse(path);},v=>notices.push(v));
  await flushPromises();
  await wrapper.findAll('button').find(x=>x.text()==='查看大图').trigger('click');await flushPromises();
  assert.equal(wrapper.getComponent({name:'FixtureDetail'}).props('kind'),'detail');
  assert.match(wrapper.get('.fixture-detail').text(),/Movies/);
  await wrapper.get('.fixture-detail .close').trigger('click');
  await wrapper.findAll('button').find(x=>x.text()==='重新应用封面').trigger('click');
  const confirm=wrapper.getComponent({name:'FixtureConfirm'});
  confirm.vm.$emit('confirm');await flushPromises();
  assert.equal(confirm.props('loading'),true);assert.equal(notices.length,0);
  confirm.vm.$emit('confirm');await flushPromises();assert.equal(applied,1);
  finish({});await flushPromises();
  assert.deepEqual(notices,[{title:'封面已重新应用',tone:'success'}]);
  assert.equal(wrapper.find('.fixture-confirm').exists(),false);
  assert.equal(wrapper.text().includes('正在处理'),false);
  assert.equal(wrapper.find('[role="status"]').exists(),false);
  wrapper.unmount();
});

test('a failed apply keeps confirmation available for retry without duplicating a handled error',async()=>{
 const notices=[];
 const wrapper=historyFixture(async path=>{if(path.endsWith('history_apply'))throw Object.assign(new Error('Reported by host'),{notificationHandled:true});return historyResponse(path);},v=>notices.push(v));
 await flushPromises();await wrapper.findAll('button').find(x=>x.text()==='重新应用封面').trigger('click');
 wrapper.getComponent({name:'FixtureConfirm'}).vm.$emit('confirm');await flushPromises();
 assert.equal(wrapper.getComponent({name:'FixtureConfirm'}).props('loading'),false);
 assert.equal(wrapper.find('.fixture-confirm').exists(),true);assert.deepEqual(notices,[]);
 wrapper.unmount();
});
