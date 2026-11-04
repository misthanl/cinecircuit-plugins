import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const host = resolve('../cinecircuit/frontend');
const req = createRequire(resolve(host,'package.json'));
const { createServer } = await import(pathToFileURL(req.resolve('vite')).href);
const { default: vue } = await import(pathToFileURL(req.resolve('@vitejs/plugin-vue')).href);
const { chromium } = req('playwright');
const taskPath = resolve('cinecircuit_plugins/brush_flow/TaskCard.vue').replaceAll('\\','/');
const server = await createServer({root:host,configFile:false,plugins:[vue(),{name:'mobile-layout-fixture',transform(code,id){
 if(!id.endsWith('/src/main.ts'))return;
 code=code.replace('import App from "./App.vue";', `import { h } from 'vue'; import Task from '/@fs/${taskPath}'; import Sites from './views/PtSitesView.vue'; const App={setup(){return()=>h(VApp,{},()=>h('main',{style:'padding:12px'},[h(Task,{task:{id:'qa',name:'天空站点夜间刷流任务',enabled:true,max_add:3,seeding_limit_gib:200},siteName:'天空',downloaderName:'qb',cadence:'每10分钟',globalLimit:30}),h(Sites,{sites:[{id:'qa',name:'测试站点',resource_id:'',engine:'',base_url:'https://example.test',uploaded:169750000000000,downloaded:5600000000000,enabled:true}]})]))}};`);
 return code.slice(0,code.indexOf('async function bootstrap()'))+'createApp(App).use(vuetify).mount("#app");';
}}],server:{host:'127.0.0.1',port:5201,strictPort:true,fs:{allow:[resolve('..')]}},optimizeDeps:{entries:['index.html']}});
let browser;
try{await server.listen();browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage();
 await page.route('**/*',r=>['xhr','fetch'].includes(r.request().resourceType())?r.fulfill({json:{items:[]}}):r.continue());
 await mkdir('test-results/mobile-cards',{recursive:true});const evidence=[];
 for(const width of [390,430,1280]){await page.setViewportSize({width,height:900});await page.goto('http://127.0.0.1:5201');await page.locator('.task-header').waitFor();await page.waitForTimeout(300);
 const layout=await page.evaluate(()=>{const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right}};return {header:box('.task-header'),menu:box('.task-menu'),status:box('.task-status'),arrow:box('.task-actions>.v-btn'),strip:box('.site-data-strip'),bars:box('.site-data-bars')}});
 console.log(JSON.stringify({width,...layout})); if(width<480){assert.ok(layout.menu.x>layout.header.right-56);assert.ok(layout.menu.y<layout.status.y);assert.ok(layout.arrow.y>layout.menu.y);assert.ok(layout.bars.width>layout.strip.width*.55);}
 assert.ok(layout.bars.right<=width);await page.getByRole('button',{name:'更多任务操作'}).click();await page.getByText('编辑任务',{exact:true}).waitFor();await page.keyboard.press('Escape');await page.locator('.task-disclosure').click();await page.locator('.task-details').waitFor();
 await page.screenshot({path:`test-results/mobile-cards/layout-${width}.png`,fullPage:true});evidence.push({width,...layout});}
 await writeFile('test-results/mobile-cards/results.json',JSON.stringify(evidence,null,2));console.log('Mobile menus, expanded cards and PT tracks verified at 390, 430 and 1280px');
}finally{await browser?.close();await server.close();}



