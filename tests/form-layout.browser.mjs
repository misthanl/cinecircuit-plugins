// Integration check against an explicitly supplied host checkout and catalog.
// No application server, credentials, or production writes are used.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const host = resolve(process.argv[2]);
const catalog = JSON.parse(readFileSync(process.argv[3], 'utf8')).plugins;
const require = createRequire(resolve(host, 'package.json'));
const { createServer } = require('vite');
const { chromium } = require('playwright');
const vuePlugin = (await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)).default;
const pluginRoot = process.cwd().replaceAll('\\', '/');
const hostUrl = '/@fs/' + host.replaceAll('\\', '/');
const directories = { 'auto-signin':'auto_signin', 'brush-flow':'brush_flow', 'cast-profile-enricher':'cast_profile_enricher', cookiecloud:'cookiecloud', 'douban-hot':'douban_rank', 'maoyan-rank':'maoyan_rank', 'emby-cover-generator':'media_cover_generator', 'storage-recycle-cleaner':'storage_recycle_cleaner', 'subtitle-manager':'subtitle_manager' };
const entry = `
import * as Vue from '/node_modules/.vite/deps/vue.js';
import { createVuetify } from '${hostUrl}/node_modules/vuetify/lib/framework.js';
import * as components from '${hostUrl}/node_modules/vuetify/lib/components/index.js';
import '${hostUrl}/node_modules/vuetify/lib/styles/main.css';
import '/src/styles.css';
import '/src/views/PluginLibraryView.vue';
import Fields from '/src/components/SchemaDrivenFields.vue';
import CronField from '/src/components/CronExpressionField.vue';
import { registerPluginEditor } from '/src/extensions/editorRegistry.ts';
import { formLayoutStyle } from '/src/extensions/formPresentation.ts';
const catalog = ${JSON.stringify(catalog)};
const directories = ${JSON.stringify(directories)};
for (const item of catalog) {
 const id = item.manifest.id;
 const module = await import('/@fs/${pluginRoot}/.build/cinecircuit_plugins/' + directories[id] + '/frontend.js');
 module.install({ vue: Vue, ui: { components: { ...components, SchemaFields: Fields, CronField, Dialog:components.VDialog, Card:components.VCard, Button:components.VBtn } },
  request: async () => ({ items:[], servers:[], libraries:[] }),
  registerEditor: editor => registerPluginEditor(editor, []), registerPage(){}, registerContribution(){} });
}
let app;
catalog.push({manifest:{id:'layout-probe',config_schema:{fields:[
 {key:'name',input_type:'text',label:'Required name',default:'',required:true,description:'Must stay hidden',description_display:'hidden'},
 {key:'enabled',input_type:'switch',label:'Enabled',default:true},
]}}});
window.renderForm = async (id, section, columns=2) => {
 app?.unmount();
 const schema = catalog.find(item=>item.manifest.id===id).manifest.config_schema;
 const fields = schema.fields.filter(field => !section || field.section===section).map(field=>({...field,description_display:field.description_display??schema.description_display}));
 const value = Object.fromEntries(schema.fields.map(field=>[field.key,field.default]));
 const layout = {columns,row_gap:14,column_gap:16};
 app = Vue.createApp({render:()=>Vue.h(components.VApp,{},()=>Vue.h('div',{class:'plugin-config-form',style:{...formLayoutStyle(layout),padding:'24px'}},[
   Vue.h(Fields,{class:'standard-config-fields plugin-config-fields plugin-config-grid',modelValue:value,fields,compact:true,layout,extensionDomain:'plugin',extensionKey:id,extensionSection:section}),
   Vue.h('div',{id:'legacy-grid',style:{display:'grid',gridTemplateColumns:'repeat(3,1fr)'}},['a','b','c']),
 ]))});
 const control={class:'app-field',variant:'outlined',density:'comfortable',hideDetails:'auto'};
 app.use(createVuetify({components,defaults:{VTextField:control,VSelect:control,VTextarea:control}})); app.mount('#app');
 await Vue.nextTick();
};
window.fixtureReady=true;
`;
const fixturePlugin = { name:'form-layout-fixture', configureServer(server) { server.middlewares.use((req,res,next)=>{
 if(req.url==='/fixture'){res.setHeader('Content-Type','text/html');res.end('<div id="app"></div><script type="module" src="/fixture.js"></script>');}
 else if(req.url==='/fixture.js'){res.setHeader('Content-Type','text/javascript');res.end(entry);}
 else next();
}); } };
const server = await createServer({root:host, configFile:false, plugins:[fixturePlugin,vuePlugin()], server:{host:'127.0.0.1',port:5188,fs:{allow:[host,pluginRoot]}}, resolve:{dedupe:['vue','vuetify']}, optimizeDeps:{include:['vue','vuetify']} });
let browser;
try {
 await server.listen();
 browser = await chromium.launch({channel:'msedge',headless:true});
 const page = await browser.newPage();
 const errors=[];page.on('pageerror',error=>{errors.push(error.message);console.error(error.message);});
 page.on('console',message=>{if(message.type()==='error')console.error(message.text());});
 await page.route('**/api/**',route=>new URL(route.request().url()).pathname.startsWith('/api/') ? route.fulfill({json:{items:[]}}) : route.continue());
 await page.goto('http://127.0.0.1:'+server.httpServer.address().port+'/fixture');
 await page.waitForFunction(()=>window.fixtureReady, {timeout:30000});
 let checked=0;
 for(const width of [390,680,720,760,761,1280]){
  await page.setViewportSize({width,height:1000});
  for(const item of catalog){
   const sections=item.manifest.config_schema.sections?.map(section=>section.key)||[''];
   for(const section of sections){
    await page.evaluate(([id,section])=>window.renderForm(id,section),[item.manifest.id,section]);
    await page.waitForTimeout(80);
    const grids=await page.locator('.app-form-layout').evaluateAll(nodes=>nodes.map(node=>({columns:getComputedStyle(node).gridTemplateColumns.split(' ').length,gap:getComputedStyle(node).rowGap,local:node.closest('.style-controls')!=null})));
    assert.ok(grids.length, item.manifest.id+':'+section);
    for(const grid of grids){assert.equal(grid.columns,width<=760||grid.local?1:2,JSON.stringify({width,id:item.manifest.id,section,grid}));assert.equal(grid.gap,'14px');}
    assert.equal(await page.locator('#legacy-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),3);
    if(width===1280){
      await page.locator('.plugin-config-form').evaluate(el=>el.style.setProperty('--app-font-size-label','17px'));
      const labelSizes=await page.locator('.plugin-config-grid .v-switch .v-label,.plugin-config-grid .switches b').evaluateAll(nodes=>nodes.map(el=>getComputedStyle(el).fontSize));
      assert.ok(labelSizes.every(size=>size==='17px'),JSON.stringify({id:item.manifest.id,section,labelSizes}));
    }
    if(section==='animation') {
      const hints=await page.locator('.v-messages__message').evaluateAll(nodes=>nodes.map(el=>({text:el.textContent,visible:el.checkVisibility(),parent:getComputedStyle(el.closest('.v-input__details')).cssText,display:getComputedStyle(el.closest('.v-input__details')).display,visibility:getComputedStyle(el.closest('.v-input__details')).visibility})));
      assert.ok(await page.locator('.v-messages__message:visible').count()>=4,JSON.stringify({width,id:item.manifest.id,hints,html:await page.locator('.schema-driven-fields').innerHTML()}));
    }
    checked++;
   }
  }
 }
 await page.setViewportSize({width:1280,height:1000});
 for(const id of ['auto-signin','cast-profile-enricher','cookiecloud','emby-cover-generator']){
  await page.evaluate(([id,section])=>window.renderForm(id,section,3),[id,id==='emby-cover-generator'?'run':'']);
  const counts=await page.locator('.app-form-layout').evaluateAll(nodes=>nodes.map(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length));
  assert.ok(counts.every(count=>count===3),JSON.stringify({id,counts}));
 }
 await page.evaluate(()=>window.renderForm('auto-signin','',3));
 assert.equal(await page.locator('.app-form-layout').first().evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),3);
 await page.evaluate(()=>window.renderForm('layout-probe',''));
 await page.locator('input[type=text]').focus();
 assert.equal(await page.getByText('Must stay hidden').count(),0);
 await page.locator('input[type=text]').blur();
 await page.waitForTimeout(200);
 assert.ok(await page.locator('.v-messages__message:visible').count()>0,'validation error must remain visible');
 await page.locator('.plugin-config-form').evaluate(el=>{
   el.style.setProperty('--app-font-size-label','17px');
   el.style.setProperty('--app-font-size-control','19px');
 });
 assert.equal(await page.locator('.v-switch .v-label').evaluate(el=>getComputedStyle(el).fontSize),'17px');
 assert.equal(await page.locator('input[type=text]').evaluate(el=>getComputedStyle(el).fontSize),'19px');
 assert.deepEqual(errors,[]);
 mkdirSync('.build/browser-checks',{recursive:true});
 await page.evaluate(()=>window.renderForm('emby-cover-generator','run'));
 await page.screenshot({path:'.build/browser-checks/cover-run-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:1000});
 await page.evaluate(()=>window.renderForm('cast-profile-enricher',''));
 await page.screenshot({path:'.build/browser-checks/cast-mobile.png',fullPage:true});
 console.log('rendered_form_cases='+checked+'; parameter_override=passed; existing_three_column_page=unchanged');
} finally {await browser?.close();await server.close();}
