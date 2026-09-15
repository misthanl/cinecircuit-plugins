import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
const root=process.cwd(), host=resolve('../cinecircuit/frontend');
const require=createRequire(resolve(host,'package.json'));
const {createServer}=require('vite'),{chromium}=require('playwright');
const hostUrl='/@fs/'+host.replaceAll('\\','/');
const source=readFileSync(resolve(host,'src/extensions/runtime.ts'),'utf8');
const names=source.match(/value: Object\.freeze\(\{([\s\S]*?)\}\)/)[1].split(',').map(s=>s.trim()).filter(Boolean);
const entry=`
import * as Vue from '/node_modules/.vite/deps/vue.js';
import {createVuetify} from '${hostUrl}/node_modules/vuetify/lib/framework.js';
import * as components from '${hostUrl}/node_modules/vuetify/lib/components/index.js';
import '${hostUrl}/node_modules/vuetify/lib/styles/main.css';
import '/src/styles.css';
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=Object.fromEntries(${JSON.stringify(names)}.map(name=>[name,Vue[name]]));
const plugin=await import('/@fs/${root.replaceAll('\\','/')}/.build/cinecircuit_plugins/cloud_copy/frontend.js');
let page;
plugin.install({vue:Vue,ui:{components:{Dialog:components.VDialog,Card:components.VCard,Button:components.VBtn}},registerContribution(){},registerPage(row){page=row.component},
request:async path=>path.endsWith('/options')?{items:[{id:'source',name:'115网盘',enabled:true,capabilities:['file_copy_source']},{id:'target',name:'夸克网盘',enabled:true,capabilities:['file_copy_target']}]}:{items:[{id:'fixture',names:['测试电视剧.mkv'],selected:1,status:'running',current_file:'测试电视剧.mkv',phase:'正在校验并尝试秒传',config:{source:'source',target:'target'}}]}});
const app=Vue.createApp({render:()=>Vue.h(components.VApp,{},()=>Vue.h(page))});
app.use(createVuetify({components}));app.mount('#app');
`;
const fixture={name:'copy-render-fixture',configureServer(server){server.middlewares.use((req,res,next)=>{
 if(req.url==='/fixture'){res.setHeader('Content-Type','text/html');res.end('<html lang="zh"><div id="app"></div><script type="module" src="/fixture.js"></script></html>');}
 else if(req.url==='/fixture.js'){res.setHeader('Content-Type','text/javascript');res.end(entry);}else next();
});}};
const server=await createServer({root:host,configFile:false,plugins:[fixture],server:{host:'127.0.0.1',port:0,fs:{allow:[host,root]}},resolve:{dedupe:['vue','vuetify']},optimizeDeps:{include:['vue','vuetify']}});
let browser;
try{
 await server.listen();browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(server.resolvedUrls.local[0]+'fixture');
 await page.getByRole('heading',{name:'跨网盘复制',exact:true}).waitFor();
 assert.equal(await page.getByPlaceholder('筛选当前目录').count(),2);
 const typography=await page.getByPlaceholder('筛选当前目录').first().evaluate(el=>{
  const style=getComputedStyle(el),placeholder=getComputedStyle(el,'::placeholder');
  return {font:style.fontFamily,size:style.fontSize,weight:style.fontWeight,placeholderFont:placeholder.fontFamily,placeholderSize:placeholder.fontSize,placeholderWeight:placeholder.fontWeight,token:style.getPropertyValue('--app-font-family')};
 });
 console.log(JSON.stringify(typography));
 assert.equal(typography.font,typography.token.trim());
 assert.equal(typography.size,'14px');assert.equal(typography.weight,'400');
 assert.equal(typography.placeholderFont,typography.font);
 assert.equal(typography.placeholderSize,'14px');assert.equal(typography.placeholderWeight,'400');
 await page.getByRole('button',{name:'复制记录',exact:true}).click();
 await page.getByText('正在校验并尝试秒传',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 mkdirSync('.build/verification',{recursive:true});
 await page.screenshot({path:'.build/verification/cloud-copy-render.png'});
 console.log('Real browser: page, both filters, records dialog, current file and stage rendered; no page errors.');
}finally{await browser?.close();await server.close();}
