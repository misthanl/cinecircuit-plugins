import {test} from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {resolve} from "node:path";
const require=createRequire(resolve("package.json"));
const {JSDOM}=require("jsdom");const dom=new JSDOM("<!doctype html><html><body></body></html>");
for(const key of ["window","document","Element","HTMLElement","SVGElement","Node"])globalThis[key]=dom.window[key];
const vue=require("vue");globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=vue;
const {install}=await import("../../.build/cinecircuit_plugins/douban_wish/frontend.js");
const {mount,flushPromises}=require("@vue/test-utils");
const Box={setup:(_, {slots})=>()=>vue.h("div",slots.default?.())};
const Button={props:["disabled","loading"],emits:["click"],setup:(props,{slots,emit})=>()=>vue.h("button",{disabled:props.disabled||props.loading,onClick:()=>emit("click")},slots.default?.())};
function component(request){let contribution;install({vue,ui:{components:{Button,Card:Box,Dialog:Box,Alert:Box,Image:"img"}},request,registerContribution:value=>{contribution=value;}});assert.equal(contribution.pluginId,"douban-wish");assert.equal(contribution.slot,"plugin.statistics");return contribution.component;}
const row={id:1,title:"测试影片",media_label:"电影",board:"example",rating:8.2,subscribed_at:"2026-10-30T00:00:00Z"};
const empty={items:[],total:0,movie_count:0,tv_count:0,board_count:0,page:1,pages:1};
test("wish history uses existing poster cards and its own paginated endpoint",async()=>{
const urls=[];const wrapper=mount(component(async url=>{urls.push(url);return {...empty,items:[row],total:9,pages:2,page:url.endsWith("page=2")?2:1};}),{props:{context:{close(){}}}});await flushPromises();
assert.match(wrapper.text(),/豆瓣想看/);assert.match(wrapper.text(),/测试影片/);assert.match(wrapper.text(),/example/);assert.equal(wrapper.findAll(".douban-subscription").length,1);assert.equal(wrapper.find("table").exists(),false);
await wrapper.findAll("button").find(b=>b.text()==="下一页").trigger("click");await flushPromises();assert.equal(urls.at(-1),"/plugins/douban-wish/api/statistics?page=2");wrapper.unmount();});
test("statistics supports request retry and empty history",async()=>{let calls=0;const wrapper=mount(component(async()=>{if(++calls===1)throw new Error("读取失败");return empty;}),{props:{context:{close(){}}}});await flushPromises();assert.match(wrapper.text(),/读取失败/);await wrapper.findAll("button").find(b=>b.text()==="刷新").trigger("click");await flushPromises();assert.match(wrapper.text(),/暂无订阅记录/);wrapper.unmount();});
