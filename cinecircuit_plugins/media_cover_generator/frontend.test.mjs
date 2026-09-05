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
const { install } = await import("../../.build/cinecircuit_plugins/media_cover_generator/frontend.js");
const { mount, flushPromises } = require("@vue/test-utils");
installSelectStub(vue,require('@vue/test-utils').config);
require('@vue/test-utils').config.global.stubs.VBtn=true;

test('poster preference defaults on but preserves explicit off', async () => {
  const wrapper=mount(styleEditor(),{props:{modelValue:{}}});
  const preference=()=>wrapper.findAll('.switches label').find(x=>x.text().includes('优先使用海报图')).get('input');
  assert.equal(preference().element.checked,true);
  await preference().setValue(false);
  assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].use_primary,false);
  await wrapper.setProps({modelValue:{use_primary:false}});
  assert.equal(preference().element.checked,false);
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

function setup(request) {
  let registration;
  install({ vue, request, registerPage: value => { registration = value; }, registerEditor() {} });
  assert.equal(registration.pluginId, "emby-cover-generator");
  return mount(registration.component);
}

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

test("cover generator preserves server selection, library toggles and run sequence", async () => {
  const calls = [];
  const request = async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      servers: [{ id: "server-1", name: "Emby" }], libraries: [],
      config: { cover_style_base: "single", selected_servers: [], include_libraries: [] },
    };
    if (path.includes("/api/targets?")) return {servers:[{value:'server-1',title:'Emby'}],libraries:[{value:'["server-1","library-1"]',title:'Emby：电影'}]};
    return {};
  };
  const wrapper = setup(request);
  await flushPromises();
  await wrapper.get('.target-servers').setValue(['server-1']);
  await flushPromises();
  assert.ok(calls.at(-1).path.includes('/api/targets?servers='));

  await wrapper.get('.target-libraries').setValue(['["server-1","library-1"]']);
  await wrapper.findAll("button").find(button => button.text() === "保存并生成").trigger("click");
  await flushPromises();

  const saveCall = calls.find(call => call.path === "/plugins/emby-cover-generator");
  assert.equal(saveCall.init.method, "PATCH");
  const saved = JSON.parse(saveCall.init.body).config;
  assert.deepEqual(saved.selected_servers, ["server-1"]);
  assert.deepEqual(saved.library_targets, ['["server-1","library-1"]']);
  assert.equal(saved.dry_run, false);
  assert.equal(calls.at(-1).path, "/plugins/emby-cover-generator/run");
  assert.equal(calls.at(-1).init.method, "POST");
  wrapper.unmount();
});

test("cover studio exposes visual style previews and font presets", async () => {
  const calls = [];
  const wrapper = setup(async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith("/api/inventory")) return {
      servers: [{ id: "server-1", name: "Emby" }],
      libraries: [{ id: "library-1", name: "电影", collection_type: "movies" }],
      config: { cover_style_base: "single", selected_servers: ["server-1"], include_libraries: ["library-1"] },
    };
    return {};
  });
  await flushPromises();

  assert.equal(wrapper.findAll(".sample img").length, 1);
  await wrapper.get('.base-style-select').setValue('poster');
  assert.equal(wrapper.get('.sample img').attributes('alt'),'海报长廊成品封面样例');
  const fields = wrapper.findAll('.settings-section label');
  await fields.find(field=>field.text().startsWith('主标题字体')).get('select').setValue('serif');
  await fields.find(field=>field.text().startsWith('副标题字体')).get('select').setValue('editorial');
  await wrapper.findAll("button").find(button => button.text() === "保存并生成").trigger("click");
  await flushPromises();
  const saved = JSON.parse(calls.find(call => call.path === "/plugins/emby-cover-generator").init.body).config;
  assert.equal(saved.zh_font_preset, "serif");
  assert.equal(saved.en_font_preset, "editorial");
  assert.equal(saved.cover_style_base, "poster");
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

test('failed save does not start generation with stale settings', async () => {
  const calls=[];
  const wrapper=setup(async(path,init)=>{
    calls.push({path,init});
    if(path.endsWith('/api/inventory'))return {servers:[],libraries:[],config:{}};
    if(init?.method==='PATCH')throw new Error('Save failed');
    return {};
  });
  await flushPromises();
  await wrapper.findAll('button').find(button=>button.text()==='保存并生成').trigger('click');
  await flushPromises();
  assert.equal(calls.some(call=>call.path.endsWith('/run')),false);
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
  assert.deepEqual(wrapper.findAll('.base-style-select option').map(x=>x.attributes('value')),['animated','animated_diagonal']);
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
