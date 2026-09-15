import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
const require=createRequire(resolve('package.json'));
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<!doctype html><html><body></body></html>');
for(const key of ['window','document','Element','HTMLElement','SVGElement','Node']) globalThis[key]=dom.window[key];
globalThis.ResizeObserver=class {observe(){} disconnect(){}};
globalThis.getComputedStyle=dom.window.getComputedStyle.bind(dom.window);
const vue=require('vue');
const hostSource=readFileSync('../cinecircuit/frontend/src/extensions/runtime.ts','utf8');
const runtimeBody=hostSource.match(/value: Object\.freeze\(\{([\s\S]*?)\}\)/)[1];
const runtimeNames=runtimeBody.split(',').map(name=>name.trim()).filter(Boolean);
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=Object.freeze(Object.fromEntries(runtimeNames.map(name=>[name,vue[name]])));
const {mount,flushPromises,config}=require('@vue/test-utils');
const {install}=await import('../../.build/cinecircuit_plugins/cloud_copy/frontend.js');
const Pass=vue.defineComponent({setup:(_, {slots})=>()=>vue.h('div',slots.default?.())});
const Button=vue.defineComponent({props:['disabled'],emits:['click'],setup:(p,{slots,emit,attrs})=>()=>vue.h('button',{...attrs,disabled:p.disabled,onClick:()=>emit('click')},slots.default?.())});
config.global.stubs={VIcon:true,VTooltip:true,VTextField:true,VSelect:vue.defineComponent({name:'VSelect',props:['items','modelValue'],emits:['update:modelValue'],template:'<div />'})};
config.global.stubs.VMenu=vue.defineComponent({setup:(_, {slots})=>()=>vue.h('div',[slots.activator?.({props:{onClick(){}}}),slots.default?.()])});
config.global.stubs.VList=Pass;
config.global.stubs.VListItem=vue.defineComponent({props:['title','disabled'],emits:['click'],setup:(p,{emit})=>()=>vue.h('button',{disabled:p.disabled,onClick:()=>emit('click')},p.title)});
function setup(request){
 let workspace,editor,page;
 const Schema=vue.defineComponent({name:'SchemaFieldsFixture',props:['fields','modelValue'],emits:['update:modelValue'],setup:p=>()=>vue.h('div',p.fields[0].key)});
 install({vue,request,ui:{components:{Dialog:Pass,Card:Pass,Button,SchemaFields:Schema}},registerContribution:r=>workspace=r.component,registerPage:r=>page=r.component,registerEditor:r=>editor=r.component});
 return {workspace,editor,Schema,page};
}

test('manual statistics menu sends record origin and identity while rule controls stay disabled',async()=>{
 const calls=[];
 const row={identity:'abc',row_key:'manual:batch:abc',batch_id:'batch',origin:'manual',name:'movie',path:'movie',source_name:'源',target_storage_name:'目标',status:'skipped',can_retry:true,can_delete:true};
 const {workspace}=setup(async(path,init)=>{calls.push({path,init});return {configured:true,rule_configured:false,counts:{},records:[row],total:1,page:1,pages:1,directories:0};});
 const wrapper=mount(workspace);await flushPromises();
 assert.ok(wrapper.find('[aria-label="记录操作"]').exists());
 assert.equal(wrapper.text().includes('查看详情'),false);
 assert.equal(wrapper.findAll('.file').length,1);
 assert.deepEqual(wrapper.findAll('small').map(x=>x.text()),['手动复制']);
 assert.ok(wrapper.findAll('button').find(b=>b.text()==='重新扫描').element.disabled);
 await wrapper.findAll('button').find(b=>b.text()==='重试').trigger('click');await flushPromises();
 assert.deepEqual(JSON.parse(calls.find(c=>c.path.endsWith('/record-retry')).init.body),{identity:'abc',origin:'manual',batch_id:'batch'});
 await wrapper.findAll('button').find(b=>b.text()==='删除').trigger('click');await flushPromises();
 assert.ok(calls.some(c=>c.path.endsWith('/record-delete')));
 wrapper.findAllComponents({name:'VSelect'})[0].vm.$emit('update:modelValue','manual');await flushPromises();
 assert.ok(calls.at(-1).path.includes('origin=manual'));
 wrapper.unmount();
});

test('batch menu disables running records and sends completed record deletion',async()=>{
 const calls=[];
 const rows=[{id:'active',names:['active'],config:{source:'s',target:'t'},status:'running',selected:1,can_retry:false,can_delete:false},{id:'done',names:['done'],config:{source:'s',target:'t'},status:'completed',selected:1,can_retry:false,can_delete:true}];
 const {page}=setup(async(path,init)=>{calls.push({path,init});return {items:path.endsWith('/batches')?rows:[]};});
 const wrapper=mount(page);await flushPromises();
 await wrapper.findAll('button').find(b=>b.text()==='复制记录').trigger('click');await flushPromises();
 const trs=wrapper.findAll('tbody tr');
 assert.ok(trs[0].findAll('button').find(b=>b.text()==='删除').element.disabled);
 assert.ok(trs[0].findAll('button').find(b=>b.text()==='重试').element.disabled);
 await trs[1].findAll('button').find(b=>b.text()==='删除').trigger('click');await flushPromises();
 assert.deepEqual(JSON.parse(calls.find(c=>c.path.endsWith('/batch-delete')).init.body),{id:'done'});
 wrapper.unmount();
});
test('statistics has separate source/target columns and sends server-side filters',async()=>{
 const calls=[];
 const {workspace}=setup(async path=>{calls.push(path);return {configured:true,counts:{completed:3},records:[],total:0,page:1,pages:1,directories:0,paused:false};});
 const wrapper=mount(workspace,{props:{context:{close(){}}}});
 await flushPromises();
 assert.deepEqual(wrapper.findAll('th').map(x=>x.text()),['文件名称','源网盘','目标网盘','传输方式','进度','处理结果','']);
 wrapper.findAllComponents({name:'VSelect'})[1]?.vm.$emit('update:modelValue','conflict');
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
 const fields=['show_sidebar_nav','source','source_root','target','target_root','policy','temporary_directory','max_gib','followup'].map(key=>({key}));
 const wrapper=mount(editor,{props:{fields,modelValue:{source:'supported',target:'plain',life_events_enabled:true}}});
 await flushPromises();
 const select=wrapper.findComponent('.copy-config-trigger [label="触发方式"]');
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

test('temporary directory gates content policies and clearing it resets selection',async()=>{
 const {editor,Schema}=setup(async()=>({items:[]}));
 const fields=['show_sidebar_nav','source','source_root','target','target_root','policy','temporary_directory','max_gib','followup'].map(key=>({key,...(key==='policy'?{options:['metadata','verify','relay'].map(value=>({value}))}:{})}));
 const wrapper=mount(editor,{props:{fields,modelValue:{policy:'metadata'}}});await flushPromises();
 const policyField=()=>wrapper.findAllComponents(Schema).find(x=>x.props('fields')[0].key==='policy');
 assert.deepEqual(policyField().props('fields')[0].options.map(x=>x.value),['metadata']);
 await wrapper.setProps({modelValue:{policy:'relay',temporary_directory:'/media/copy-temp'}});
 assert.deepEqual(policyField().props('fields')[0].options.map(x=>x.value),['metadata','verify','relay']);
 const directory=wrapper.findAllComponents(Schema).find(x=>x.props('fields')[0].key==='temporary_directory');
 directory.vm.$emit('update:modelValue',{temporary_directory:''});await flushPromises();
 assert.equal(wrapper.emitted('update:modelValue').at(-1)[0].policy,'metadata');
 assert.ok(!wrapper.text().includes('未设置临时目录时'));
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


test('HTTP browser without randomUUID submits and exposes live batch feedback',async()=>{
 const descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto');
 const original=globalThis.crypto;
 Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues:original.getRandomValues.bind(original)}});
 let submitted;
 const batch={id:'batch',names:['a very long file.mkv'],selected:1,status:'running',current_file:'episode.mkv',phase:'正在校验并尝试秒传',pending:1,config:{source:'source',target:'target'}};
 const {page}=setup(async(path,init)=>{
  if(path.endsWith('/options'))return {items:[]};
  if(path.includes('/browse?'))return {items:[{file_id:'file',name:'episode.mkv',directory:false}],cursor:null};
  if(path.endsWith('/submit')){submitted=JSON.parse(init.body);return batch;}
  return {items:[batch]};
 });
 let wrapper;
 try{
  wrapper=mount(page);await flushPromises();
  const selects=wrapper.findAllComponents({name:'VSelect'});
  selects[0].vm.$emit('update:modelValue','source');selects[1].vm.$emit('update:modelValue','target');await flushPromises();
  await wrapper.find('input[aria-label="选择 episode.mkv"]').setValue(true);
  await wrapper.findAll('button').find(row=>row.text().includes('复制所选')).trigger('click');await flushPromises();
  assert.match(submitted.id,/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  assert.ok(wrapper.text().includes('正在校验并尝试秒传'));
  assert.ok(wrapper.text().includes('当前：episode.mkv'));
  assert.equal(wrapper.find('.file').text(),'a very long file.mkv');
 }finally{wrapper?.unmount();Object.defineProperty(globalThis,'crypto',descriptor);}
});


test('batch table separates outcomes and methods and suppresses duplicate phase text',async()=>{
 const rows=[
  {id:'running',names:['copying.mkv'],selected:1,status:'running',phase:'正在复制',config:{source:'source',target:'target'},methods:[]},
  {id:'skipped',names:['skipped.mkv'],selected:1,status:'completed',outcome:'skipped',skipped:1,config:{source:'source',target:'target'},methods:[],notes:['当前策略无法直接秒传']},
  {id:'done',names:['done.mkv'],selected:1,status:'completed',outcome:'completed',completed:1,config:{source:'source',target:'target'},methods:['rapid']},
 ];
 const {page}=setup(async path=>({items:path.endsWith('/batches')?rows:[]}));
 const wrapper=mount(page);await flushPromises();
 await wrapper.findAll('button').find(row=>row.text()==='复制记录').trigger('click');await flushPromises();
 const trs=wrapper.findAll('tbody tr');
 assert.equal((trs[0].text().match(/正在复制/g)||[]).length,1);
 assert.ok(trs[1].text().includes('已跳过 1'));assert.ok(trs[1].text().includes('—'));
 assert.equal(trs[1].text().includes('处理完成'),false);assert.equal(trs[1].text().includes('待核对'),false);
 assert.ok(trs[2].text().includes('秒传'));
 assert.ok(wrapper.findAll('th').some(cell=>cell.text()==='传输方式'));
 assert.equal(wrapper.find('.workspace-message').exists(),false);
 wrapper.unmount();
});
