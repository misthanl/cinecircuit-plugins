import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { test } from 'node:test';
const require=createRequire(resolve('package.json'));
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<!doctype html><html><body></body></html>');
for(const key of ['window','document','Element','HTMLElement','SVGElement','Node']) globalThis[key]=dom.window[key];
globalThis.ResizeObserver=class {observe(){} disconnect(){}};
globalThis.getComputedStyle=dom.window.getComputedStyle.bind(dom.window);
const vue=require('vue');
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=vue;
const {mount,flushPromises,config}=require('@vue/test-utils');
const {install}=await import('../../.build/cinecircuit_plugins/cloud_copy/frontend.js');
const Pass=vue.defineComponent({setup:(_, {slots})=>()=>vue.h('div',slots.default?.())});
const Button=vue.defineComponent({props:['disabled'],emits:['click'],setup:(p,{slots,emit,attrs})=>()=>vue.h('button',{...attrs,disabled:p.disabled,onClick:()=>emit('click')},slots.default?.())});
config.global.stubs={VIcon:true,VTooltip:true,VTextField:true,VSelect:vue.defineComponent({name:'VSelect',props:['items','modelValue'],emits:['update:modelValue'],template:'<div />'})};
function setup(request){
 let workspace,editor,page;
 const Schema=vue.defineComponent({props:['fields','modelValue'],emits:['update:modelValue'],setup:p=>()=>vue.h('div',p.fields[0].key)});
 install({vue,request,ui:{components:{Dialog:Pass,Card:Pass,Button,SchemaFields:Schema}},registerContribution:r=>workspace=r.component,registerPage:r=>page=r.component,registerEditor:r=>editor=r.component});
 return {workspace,editor,Schema,page};
}
test('statistics has separate source/target columns and sends server-side filters',async()=>{
 const calls=[];
 const {workspace}=setup(async path=>{calls.push(path);return {configured:true,counts:{completed:3},records:[],total:0,page:1,pages:1,directories:0,paused:false};});
 const wrapper=mount(workspace,{props:{context:{close(){}}}});
 await flushPromises();
 assert.deepEqual(wrapper.findAll('th').map(x=>x.text()),['文件名称','源网盘','目的网盘','复制方式','处理结果','操作']);
 wrapper.findAllComponents({name:'VSelect'})[0]?.vm.$emit('update:modelValue','conflict');
 await flushPromises();
 assert.ok(calls[0].includes('page=1'));
 assert.ok(calls.at(-1).includes('status=conflict'));
 assert.ok(wrapper.text().includes('没有符合条件的复制记录'));
 wrapper.unmount();
});
test('unconfigured state shows no error and disables mutation buttons',async()=>{
 const {workspace}=setup(async()=>({configured:false,counts:{},records:[],page:1,pages:1,total:0,configuration_message:'请选择源网盘与目标网盘'}));
 const wrapper=mount(workspace);await flushPromises();
 assert.ok(wrapper.text().includes('请选择源网盘与目标网盘'));
 assert.equal(wrapper.find('[role=alert]').exists(),false);
 const scan=wrapper.findAll('button').find(x=>x.text()==='重新扫描');
 assert.ok(scan.element.disabled);
 wrapper.unmount();
});
test('configuration follows source capability and clears events when source changes',async()=>{
 const {editor,Schema}=setup(async()=>({items:[{id:'supported',capabilities:['change_feed']},{id:'plain',capabilities:[]}]}));
 const fields=['show_sidebar_nav','source','source_root','target','target_root','policy','max_gib','followup'].map(key=>({key}));
 const wrapper=mount(editor,{props:{fields,modelValue:{source:'supported',target:'plain',life_events_enabled:true}}});
 await flushPromises();
 const select=wrapper.findComponent({name:'VSelect'});
 assert.deepEqual(select.props('items').map(x=>x.value),['manual','full','events']);
 assert.equal(wrapper.find('.copy-config-sidebar').text(),'show_sidebar_nav');
 select.vm.$emit('update:modelValue','full');await flushPromises();
 assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].full_scan_enabled,true);
 assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].life_events_enabled,false);
 const source=wrapper.findAllComponents(Schema).find(x=>x.props('fields')[0].key==='source');
 source.vm.$emit('update:modelValue',{source:'plain',life_events_enabled:true});await flushPromises();
 const updated=wrapper.emitted('update:modelValue').at(-1)[0];
 assert.equal(updated.life_events_enabled,false);assert.equal(updated.source_root,'0');
 await wrapper.setProps({modelValue:updated});
 assert.deepEqual(select.props('items').map(x=>x.value),['manual','full']);
 assert.equal(select.props('modelValue'),'manual');
 select.vm.$emit('update:modelValue','full');await flushPromises();
 const scheduled=wrapper.emitted('update:modelValue').at(-1)[0];
 assert.equal(scheduled.full_scan_enabled,true);assert.equal(scheduled.life_events_enabled,false);
 assert.equal(wrapper.text().includes('life_events_since'),false);
 wrapper.unmount();
});

test('manual workspace submits only selected identities without changing plugin configuration',async()=>{
 const calls=[];
 const {page}=setup(async(path,init)=>{
  calls.push({path,init});
  if(path.endsWith('/options'))return {items:[{id:'source',name:'源',enabled:true,capabilities:['file_copy_source']},{id:'target',name:'目的',enabled:true,capabilities:['file_copy_target']}]};
  if(path.includes('/browse?'))return {items:[{file_id:'file',name:'selected.mkv',directory:false},{file_id:'other',name:'other.mkv',directory:false}],cursor:null};
  return {items:[]};
 });
 const wrapper=mount(page);await flushPromises();
 const selects=wrapper.findAllComponents({name:'VSelect'});
 selects[0].vm.$emit('update:modelValue','source');selects[1].vm.$emit('update:modelValue','target');await flushPromises();
 await wrapper.find('input[aria-label="选择 selected.mkv"]').setValue(true);
 const submit=wrapper.findAll('button').find(row=>row.text().includes('复制所选'));
 await submit.trigger('click');await flushPromises();
 const call=calls.find(row=>row.path.endsWith('/submit'));
 assert.deepEqual(JSON.parse(call.init.body).selected,['file']);
 assert.equal(JSON.parse(call.init.body).target,'target');
 assert.equal(calls.some(row=>row.init?.method==='PATCH'),false);
 await submit.trigger('click');await flushPromises();
 const submissions=calls.filter(row=>row.path.endsWith('/submit'));
 assert.equal(JSON.parse(submissions[0].init.body).id,JSON.parse(submissions[1].init.body).id);
 wrapper.unmount();
});

test('navigating source folders clears the previous directory selection',async()=>{
 const {page}=setup(async(path)=>path.endsWith('/options')?{items:[]} : path.includes('/browse?')?{items:[{file_id:'folder',name:'Movies',directory:true},{file_id:'file',name:'film.mkv',directory:false}],cursor:null}:{items:[]});
 const wrapper=mount(page);await flushPromises();
 wrapper.findAllComponents({name:'VSelect'})[0].vm.$emit('update:modelValue','source');await flushPromises();
 await wrapper.find('input[aria-label="选择 film.mkv"]').setValue(true);
 assert.ok(wrapper.text().includes('已选择 1 项'));
 await wrapper.findAll('button').find(row=>row.text()==='Movies').trigger('click');await flushPromises();
 assert.ok(wrapper.text().includes('已选择 0 项'));
 wrapper.unmount();
});
