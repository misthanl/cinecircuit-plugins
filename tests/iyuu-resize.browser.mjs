import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const host = resolve('../cinecircuit/frontend'), root = process.cwd();
const require = createRequire(resolve(host, 'package.json'));
const { createServer } = require('vite'), { chromium } = require('playwright');
const vue = (await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)).default;
const url = path => '/@fs/' + path.replaceAll('\\', '/');
const entry = `
import * as Vue from '/node_modules/.vite/deps/vue.js';
const {createApp,h,ref}=Vue;
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=Vue;
import {createVuetify} from '${url(host)}/node_modules/vuetify/lib/framework.js';
import * as components from '${url(host)}/node_modules/vuetify/lib/components/index.js';
import '${url(host)}/node_modules/vuetify/lib/styles/main.css';
import '/src/styles.css';
const plugin=await import('${url(root)}/.build/cinecircuit_plugins/iyuu_autoseed/frontend.js');
let Editor;plugin.install({vue:Vue,ui:{components:{SchemaFields:components.VTextField}},request:async()=>({value:''}),registerEditor:e=>{Editor=e.component},registerContribution(){}});
const value=ref({nopaths:''});
const app=createApp({render:()=>h(components.VApp,{},()=>h('div',{class:'standard-config-fields',style:'padding:30px;display:block'},[
h(Editor,{modelValue:value.value,'onUpdate:modelValue':v=>value.value=v,fields:[{key:'nopaths',label:'不辅种数据目录'}],schemaFieldsComponent:components.VTextField,request:async()=>({value:''})})]))});
app.use(createVuetify({components,defaults:{VTextarea:{variant:'outlined',density:'comfortable',hideDetails:'auto'}}}));app.mount('#app');
`;
const server = await createServer({root:host,configFile:false,plugins:[vue(),{name:'resize-fixture',configureServer(s){s.middlewares.use((req,res,next)=>{
if(req.url==='/resize'){res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/resize.js"></script>');}
else if(req.url==='/resize.js'){res.setHeader('Content-Type','text/javascript');res.end(entry);}else next();
});}}],server:{host:'127.0.0.1',port:5196,fs:{allow:[host,root]}},resolve:{dedupe:['vue','vuetify']},optimizeDeps:{include:['vue','vuetify']}});
let browser;
try {
await server.listen();browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900}});
page.on('pageerror',e=>console.error(e.message));page.on('console',m=>{if(m.type()==='error')console.error(m.text())});
await page.goto('http://127.0.0.1:'+server.httpServer.address().port+'/resize');
const field=page.locator('textarea:not([aria-hidden])');await field.waitFor();
await field.fill('/media/keep\n/media/download');
const start=await field.boundingBox();
const initial=await field.evaluate(el=>({resize:getComputedStyle(el).resize,rows:el.rows}));
await page.mouse.move(start.x+start.width-4,start.y+start.height-4);
await page.mouse.down();await page.mouse.move(start.x+start.width-4,start.y+start.height+130,{steps:15});await page.mouse.up();
const expanded=await field.boundingBox();
assert.ok(expanded.height>start.height+90,JSON.stringify({initial,start,expanded}));
assert.equal(await field.inputValue(),'/media/keep\n/media/download');
await page.mouse.move(expanded.x+expanded.width-4,expanded.y+expanded.height-4);
await page.mouse.down();await page.mouse.move(expanded.x+expanded.width-4,start.y+start.height-4,{steps:15});await page.mouse.up();
const shrunk=await field.boundingBox();assert.ok(shrunk.height<expanded.height-90);
assert.equal(initial.rows,1);console.log(JSON.stringify({initial,height:start.height,expanded:expanded.height,shrunk:shrunk.height}));
} finally {await browser?.close();await server.close();}
