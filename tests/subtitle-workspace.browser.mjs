import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const host = resolve(process.argv[2]);
const frontend = resolve(host, "frontend");
const require = createRequire(resolve(frontend, "package.json"));
const { createServer } = require("vite");
const { chromium } = require("playwright");
const vuePlugin = (await import(pathToFileURL(require.resolve("@vitejs/plugin-vue")).href)).default;
const pluginRoot = process.cwd().replaceAll("\\", "/");
const hostUrl = "/@fs/" + frontend.replaceAll("\\", "/");
const poster = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="170"><rect width="120" height="170" fill="#dbe7dc"/><text x="60" y="82" text-anchor="middle" fill="#284333" font-size="16">绿灯军团</text></svg>');
const entry = `
import * as Vue from '/node_modules/.vite/deps/vue.js';
import { appDialogScrollStrategy } from '${hostUrl}/src/appDialogScrollStrategy.ts';
import { createVuetify } from '${hostUrl}/node_modules/vuetify/lib/framework.js';
import { appMdiIconSet } from '${hostUrl}/src/icons/appMdiIconSet.ts';
import { aliases } from '${hostUrl}/node_modules/vuetify/lib/iconsets/mdi-svg.js';
import * as components from '${hostUrl}/node_modules/vuetify/lib/components/index.js';
import { createPageAlertBridge } from '${hostUrl}/src/pageAlertBridge.ts';
import AppTooltipHost from '${hostUrl}/src/components/AppTooltipHost.vue';
import '${hostUrl}/node_modules/vuetify/lib/styles/main.css';
import '${hostUrl}/src/styles.css';
globalThis.__CINECIRCUIT_PLUGIN_VUE_RUNTIME__=Object.freeze({...Vue});
const { install }=await import('/@fs/${pluginRoot}/.build/cinecircuit_plugins/subtitle_manager/frontend.js');
let Page;
const item={path:'D:/media/绿灯军团.2026.S01E04.2160p.strm',title:'绿灯军团.2026.S01E04.2160p',poster_url:${JSON.stringify(poster)},identity:{title:'绿灯军团',media_type:'tv',year:2026,season:1,episode:4,tmdb_id:'7179885',imdb_id:'tt26545992'},subtitles:[{name:'绿灯军团.2026.S01E04.2160p.zh-CN.ass',size:58368},{name:'绿灯军团.2026.S01E04.2160p.zh-CN.srt',size:49152}]};
const catalogItems=[item,{...item,path:'D:/media/早春晴朗.2026.S01E20.2160p.strm',title:'早春晴朗.2026.S01E20.2160p',identity:{...item.identity,title:'早春晴朗',episode:20},subtitles:[]},{...item,path:'D:/media/凡人修仙传.2020.S01E187.2160p.strm',title:'凡人修仙传.2020.S01E187.2160p',identity:{...item.identity,title:'凡人修仙传',year:2020,episode:187},subtitles:[]}];
const hostComponents={...components,Alert:components.VAlert,Dialog:components.VDialog};
install({vue:Vue,ui:{components:hostComponents},registerPage(value){Page=value.component},registerContribution(){},registerEditor(){},request:async path=>{
  if(path.includes('/api/catalog')) return {items:catalogItems};
  if(path.includes('/api/online-search')) return {sources:[{provider:'SubHD',state:'ready',candidate_count:2,raw_candidate_count:2},{provider:'字幕库',state:'restricted',candidate_count:0,errors:[{message:'需要手动访问'}]}],items:[{title:'绿灯军团.2026.S01E04.2160p.简英双语',provider:'SubHD',language:'zh-CN/en',format:'ass',candidate_handle:'candidate-1',score:92,tags:['双语'],downloadable:true,url:'https://example.test/subtitle'},{title:'Green.Lantern.2026.S01E04.WEB-DL',provider:'SubHD',language:'zh-CN',format:'srt',candidate_handle:'candidate-2',score:88,downloadable:true}],manual_actions:[{provider:'字幕库',url:'https://example.test/manual',reason:'需要手动访问'}]};
  if(path.includes('/api/online-preview')) return ((response)=>window.singlePreview ? {...response,items:[{...response.items[0],excerpt:Array.from({length:100},(_,i)=>'Subtitle line '+i).join(String.fromCharCode(10))}]}:response)({preview_handle:'preview-1',items:[{index:0,name:'绿灯军团.S01E01.zh-CN.srt',language:'zh-CN',format:'SRT',bytes:1024,excerpt:'1\\n00:00:09,246 --> 00:00:11,747\\n欢迎回来'},{index:1,name:'绿灯军团.S01E02.zh-CN.srt',language:'zh-CN',format:'SRT',bytes:1120,excerpt:'1\\n00:00:11,748 --> 00:00:14,000\\n这一季，故事将继续'},{index:2,name:'绿灯军团.S01E03.zh-CN.ass',language:'zh-CN',format:'ASS',bytes:1240,excerpt:'Dialogue: 0,0:00:14.00,0:00:15.50,新的故事'}]});
  return {items:[]};
}});
const app=Vue.createApp({render:()=>Vue.h(components.VApp,{},()=>[
  Vue.h(AppTooltipHost),
  Vue.h(components.VChip,{class:'close-chip-reference',closable:true,closeLabel:'关闭',style:{position:'fixed',opacity:0,pointerEvents:'none'},'onClick:close':()=>{window.chipRemoved=true}},()=> '电视剧热度榜单'),
  Vue.h(components.VList,{class:'card-action-menu host-menu-reference',style:{position:'fixed',opacity:0,pointerEvents:'none'}},()=>Vue.h(components.VListItem,{title:'删除',prependIcon:'mdi-trash-can-outline'})),
  Vue.h('div',{class:'app-main app-workspace',style:{height:'100vh',padding:'18px',background:'#f5f7fa'}},[Vue.h(Page)])
])});
app.use(createVuetify({components,icons:{defaultSet:'appMdi',aliases,sets:{appMdi:appMdiIconSet}},defaults:{VDialog:{scrollStrategy:appDialogScrollStrategy,transition:false}}}));app.mount('#app');await Vue.nextTick();window.pluginToasts=[];createPageAlertBridge({root:document,routeKey:()=>"plugin-subtitle-manager",publish:payload=>window.pluginToasts.push(payload)});window.fixtureReady=true;
`;
const fixture = { name: "subtitle-workspace-fixture", configureServer(server) { server.middlewares.use((req,res,next)=>{ if(req.url==="/fixture"){res.setHeader("Content-Type","text/html");res.end('<div id="app"></div><script type="module" src="/fixture.js"></script>');} else if(req.url==="/fixture.js"){res.setHeader("Content-Type","text/javascript");res.end(entry);} else next(); }); } };
const server = await createServer({root:frontend,configFile:false,plugins:[fixture,vuePlugin()],server:{host:"127.0.0.1",port:5191,fs:{allow:[frontend,pluginRoot]}},resolve:{dedupe:["vue","vuetify"]},optimizeDeps:{include:["vue","vuetify"]}});
let browser;
try {
  await server.listen();
  browser=await chromium.launch({channel:"msedge",headless:true});
  const page=await browser.newPage({viewport:{width:1800,height:960}});
  page.on("console", message => console.log(`[browser:${message.type()}] ${message.text()}`));
  page.on("pageerror", error => console.error(`[browser:error] ${error.stack || error.message}`));
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/fixture`);
  await page.waitForFunction(()=>window.fixtureReady);
  // A real Vuetify chip uses the same Chinese close label as a modal button.
  // Moving it into each dialog host must preserve its own compact remove icon.
  const chipChecks = await page.evaluate(() => {
    const chip=document.querySelector('.close-chip-reference');
    const parent=chip.parentNode, next=chip.nextSibling;
    const button=chip.querySelector('.v-chip__close');
    const measure=()=>{
      const box=button.getBoundingClientRect();
      const icon=button.querySelector('.v-icon');
      const iconBox=icon.getBoundingClientRect();
      return {width:box.width,height:box.height,iconWidth:iconBox.width,iconHeight:iconBox.height,
        display:getComputedStyle(icon).display,after:getComputedStyle(button,'::after').content};
    };
    const baseline=measure(), results=[];
    for(const kind of ['overlay','role','native','folder','config']) {
      const container=document.createElement(kind==='native'?'dialog':'div');
      if(kind==='native') container.open=true;
      if(kind==='role') container.setAttribute('role','dialog');
      container.className={overlay:'v-overlay__content',folder:'folder-picker',config:'config-dialog'}[kind] || '';
      parent.append(container);container.append(chip);
      results.push({kind,geometry:measure()});
      parent.insertBefore(chip,next);container.remove();
    }
    button.click();
    return {label:button.getAttribute('aria-label'),baseline,results,removed:window.chipRemoved};
  });
  assert.match(chipChecks.label,/^关闭/);
  assert.ok(chipChecks.baseline.width < 32 && chipChecks.baseline.iconWidth < 24);
  for(const result of chipChecks.results) assert.deepEqual(result.geometry,chipChecks.baseline,`${result.kind} must not resize chip removal`);
  assert.equal(chipChecks.removed,true);
  // Exercise inherited button widths and flex pressure in every dialog host.
  const closeGeometry = await page.evaluate(() => {
    const results=[];
    for (const kind of ['overlay','role','native','folder','config']) {
      const container=document.createElement(kind==='native'?'dialog':'div');
      if(kind==='native') container.open=true;
      if(kind==='role') container.setAttribute('role','dialog');
      container.className={overlay:'v-overlay__content',folder:'folder-picker',config:'config-dialog'}[kind] || '';
      container.style.cssText='display:flex;width:30px;position:fixed;top:0;left:0';
      const button=document.createElement('button');
      button.title='关闭';button.textContent='×';
      button.style.cssText='min-width:90px;width:90px;height:30px;padding:12px;border-radius:9px;flex-shrink:1';
      container.append(button);document.body.append(container);
      const style=getComputedStyle(button), box=button.getBoundingClientRect();
      results.push({kind,width:box.width,height:box.height,radius:style.borderRadius,icon:getComputedStyle(button,'::after').width});
      container.remove();
    }
    return results;
  });
  for(const result of closeGeometry) assert.deepEqual(result,{kind:result.kind,width:48,height:48,radius:'50%',icon:'24px'});
  await page.locator('.subtitle-local-file').first().waitFor();
  assert.equal(await page.locator('.subtitle-toolbar').count(),0);
  assert.equal(await page.locator('.subtitle-sidebar-tools [aria-label="刷新媒体目录"]').count(),1);
  assert.equal(await page.locator('[role="tab"][aria-selected="true"]').innerText(),'本地字幕');
  assert.equal(await page.locator('.subtitle-online-panel').count(),0);
  assert.equal(await page.locator('.subtitle-local-file').count(),2);
  const firstLocalRow=page.locator('.subtitle-local-file').first();
  const [localRowBox,localMarkBox]=await Promise.all([
    firstLocalRow.boundingBox(),
    firstLocalRow.locator('.subtitle-file-mark').boundingBox(),
  ]);
  assert.ok(localRowBox && localMarkBox && localMarkBox.x-localRowBox.x >= 12);
  const localHeaderCells=page.locator('.subtitle-local-columns > span');
  const firstLocalMeta=firstLocalRow.locator('.subtitle-file-meta');
  const [localLanguageHeader,localFormatHeader,localSizeHeader,localLanguageCell,localFormatCell,localSizeCell]=await Promise.all([
    localHeaderCells.nth(1).boundingBox(),
    localHeaderCells.nth(2).boundingBox(),
    localHeaderCells.nth(3).boundingBox(),
    firstLocalMeta.nth(0).boundingBox(),
    firstLocalMeta.nth(1).boundingBox(),
    firstLocalMeta.nth(2).boundingBox(),
  ]);
  for (const [header,cell] of [[localLanguageHeader,localLanguageCell],[localFormatHeader,localFormatCell],[localSizeHeader,localSizeCell]]) {
    assert.ok(header && cell && Math.abs(header.x-cell.x)<1,`local column is misaligned: ${header?.x} vs ${cell?.x}`);
  }
  const localFileName=page.locator('.subtitle-local-file .subtitle-file-copy strong').first();
  await localFileName.hover();
  const localFileTooltip=page.locator('.app-native-tooltip');
  await localFileTooltip.waitFor({state:'visible'});
  assert.match(await localFileTooltip.innerText(),/绿灯军团\.2026\.S01E04\.2160p\.zh-CN\.ass/);
  await page.mouse.move(0,0);
  assert.equal(await page.getByText('已安装字幕',{exact:true}).count(),0);
  assert.equal(await page.locator('.subtitle-content-tabs [aria-haspopup="dialog"]').count(),1);
  assert.equal(await page.locator('.subtitle-poster img').count(),1);
  await page.getByRole('button',{name:'上传字幕',exact:true}).click();
  const uploadDialog=page.getByRole('dialog',{name:'上传字幕'});
  await uploadDialog.waitFor({state:'visible'});
  assert.equal(await page.locator('.subtitle-upload-section').count(),0);
  assert.match(await uploadDialog.innerText(),/选择文件/);
  assert.equal(await uploadDialog.getByRole('button',{name:'取消',exact:true}).count(),0);
  const uploadBackdrop=page.locator('.subtitle-host-overlay');
  const uploadBackdropBox=await uploadBackdrop.boundingBox();
  assert.ok(uploadBackdropBox && uploadBackdropBox.x === 0 && uploadBackdropBox.y === 0 && uploadBackdropBox.width === 1800 && uploadBackdropBox.height === 960);
  assert.equal(await uploadBackdrop.evaluate(element=>getComputedStyle(element).zIndex),'2200');
  const languageSelect=uploadDialog.locator('.v-field').first();
  const languageSelectBox=await languageSelect.boundingBox();
  await languageSelect.click();
  const languageMenu=page.locator('.v-overlay__content .v-list').last();
  await languageMenu.waitFor({state:'visible'});
  const languageMenuBox=await languageMenu.boundingBox();
  assert.ok(languageSelectBox && languageMenuBox && languageMenuBox.y >= languageSelectBox.y + languageSelectBox.height);
  await page.getByRole('option',{name:'自动识别',exact:true}).click();
  mkdirSync('.build/browser-checks',{recursive:true});
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-upload-dialog.png',fullPage:true});
  await page.getByRole('button',{name:'关闭上传字幕窗口'}).click();
  await uploadDialog.waitFor({state:'hidden'});
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-desktop.png',fullPage:true});
  assert.equal(await page.locator('.subtitle-local-columns span').count(),4);
  assert.doesNotMatch(await page.locator('.subtitle-local-columns').innerText(),/操作/);
  const actionButton=page.locator('[aria-label^="操作 "]').first();
  const actionButtonBox=await actionButton.boundingBox();
  const firstLocalRowBox=await page.locator('.subtitle-local-file').first().boundingBox();
  assert.ok(firstLocalRowBox && actionButtonBox && firstLocalRowBox.x+firstLocalRowBox.width-actionButtonBox.x-actionButtonBox.width < 32);
  await actionButton.click();
  await page.locator('.subtitle-row-action-menu').waitFor({state:'visible'});
  assert.equal(await page.getByRole('menuitem',{name:'调轴'}).locator('svg').count(),1);
  assert.equal(await page.getByRole('menuitem',{name:'删除',exact:true}).locator('svg').count(),1);
  const hostIconSize=await page.locator('.host-menu-reference .v-icon svg').evaluate(el=>{const r=el.getBoundingClientRect();return [r.width,r.height]});
  assert.deepEqual(hostIconSize,[18,18]);
  for(const name of ['调轴','删除']) {
    const iconSize=await page.getByRole('menuitem',{name,exact:true}).locator('svg').evaluate(el=>{const r=el.getBoundingClientRect();return [r.width,r.height]});
    assert.deepEqual(iconSize,hostIconSize,`${name} must match the host menu icon size`);
  }
  assert.equal(await page.locator('.subtitle-row-action-menu').count(),1);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-local-menu.png',fullPage:true});
  await page.getByRole('menuitem',{name:'调轴'}).click();
  const adjustmentDialog=page.getByRole('dialog',{name:'调整字幕时间轴'});
  await adjustmentDialog.waitFor({state:'visible'});
  assert.equal(await adjustmentDialog.getByRole('button',{name:'取消',exact:true}).count(),0);
  const adjustmentBackdropBox=await page.locator('.subtitle-host-overlay').boundingBox();
  assert.ok(adjustmentBackdropBox && adjustmentBackdropBox.x === 0 && adjustmentBackdropBox.y === 0 && adjustmentBackdropBox.width === 1800 && adjustmentBackdropBox.height === 960);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-adjustment-dialog.png',fullPage:true});
  await page.getByRole('button',{name:'关闭调轴窗口'}).click();
  await actionButton.click();
  await page.getByRole('menuitem',{name:'删除'}).click();
  const deleteDialog=page.getByRole('dialog',{name:'删除字幕'});
  await deleteDialog.waitFor({state:'visible'});
  const closeButton=deleteDialog.getByRole('button',{name:'关闭删除字幕窗口'});
  await closeButton.hover();
  assert.equal(await closeButton.locator('svg').count(),1);
  assert.deepEqual(await closeButton.evaluate(element=>{const style=getComputedStyle(element);return [style.width,style.height,style.borderRadius]}),['48px','48px','50%']);
  assert.match(await deleteDialog.innerText(),/绿灯军团\.2026\.S01E04\.2160p\.zh-CN\.ass/);
  assert.equal(await deleteDialog.getByRole('button',{name:'取消',exact:true}).count(),0);
  const deleteBackdropBox=await page.locator('.subtitle-host-overlay').boundingBox();
  assert.ok(deleteBackdropBox && deleteBackdropBox.x === 0 && deleteBackdropBox.y === 0 && deleteBackdropBox.width === 1800 && deleteBackdropBox.height === 960);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-delete-dialog.png',fullPage:true});
  await page.getByRole('button',{name:'关闭删除字幕窗口'}).click();
  await deleteDialog.waitFor({state:'hidden'});
  await page.getByRole('tab',{name:'在线字幕'}).click();
  assert.equal(await page.locator('.subtitle-online-columns span').count(),5);
  assert.doesNotMatch(await page.locator('.subtitle-online-columns').innerText(),/操作/);
  assert.equal(await page.locator('.subtitle-online-controls').count(),0);
  assert.equal(await page.locator('.subtitle-content-tabs .subtitle-tab-search-controls').count(),1);
  assert.equal(await page.getByRole('button',{name:'搜索',exact:true}).count(),1);
  assert.equal(await page.getByText('整季',{exact:true}).count(),1);
  const seasonToggle=page.locator('.subtitle-season-toggle');
  assert.equal(await seasonToggle.evaluate(element=>getComputedStyle(element).cursor),'pointer');
  assert.equal(await seasonToggle.locator('input').evaluate(element=>getComputedStyle(element).cursor),'pointer');
  const sidebarSearch=page.getByRole('textbox',{name:'搜索本地媒体名称或路径'});
  const onlineSearch=page.getByRole('textbox',{name:'在线字幕查询词'});
  const [sidebarSearchBox,onlineSearchBox,sidebarSearchStyle,onlineSearchStyle]=await Promise.all([
    sidebarSearch.boundingBox(),
    onlineSearch.boundingBox(),
    sidebarSearch.evaluate((element)=>({fontSize:getComputedStyle(element).fontSize,borderRadius:getComputedStyle(element).borderRadius})),
    onlineSearch.evaluate((element)=>({fontSize:getComputedStyle(element).fontSize,borderRadius:getComputedStyle(element).borderRadius})),
  ]);
  assert.ok(sidebarSearchBox && onlineSearchBox && sidebarSearchBox.height === onlineSearchBox.height);
  assert.deepEqual(onlineSearchStyle,sidebarSearchStyle);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-online-toolbar.png',fullPage:true});
  await onlineSearch.press('Enter');
  await page.getByText('绿灯军团.2026.S01E04.2160p.简英双语').waitFor();
  const sourceFilterBox=await page.locator('.subtitle-source-filter').boundingBox();
  const firstSourcePillBox=await page.locator('.subtitle-source').first().boundingBox();
  assert.ok(sourceFilterBox && firstSourcePillBox && firstSourcePillBox.y-sourceFilterBox.y >= 7);
  assert.equal(await page.locator('.subtitle-source b').count(),0);
  await page.locator('.subtitle-online-results').evaluate(element=>{element.style.maxHeight='126px'});
  const onlineRow=page.locator('.subtitle-online-file').first();
  const [onlineRowBox,onlineMarkBox]=await Promise.all([
    onlineRow.boundingBox(),
    onlineRow.locator('.subtitle-file-mark').boundingBox(),
  ]);
  assert.ok(onlineRowBox && onlineMarkBox && onlineMarkBox.x-onlineRowBox.x >= 12);
  assert.ok(localRowBox && onlineRowBox && localRowBox.height === onlineRowBox.height);
  assert.ok(localMarkBox && onlineMarkBox && localMarkBox.width === onlineMarkBox.width && localMarkBox.height === onlineMarkBox.height);
  const headerCells=page.locator('.subtitle-online-columns > span');
  const firstRowMeta=onlineRow.locator('.subtitle-file-meta');
  const [languageHeader,formatHeader,scoreHeader,languageCell,formatCell,scoreCell]=await Promise.all([
    headerCells.nth(2).boundingBox(),
    headerCells.nth(3).boundingBox(),
    headerCells.nth(4).boundingBox(),
    firstRowMeta.nth(1).boundingBox(),
    firstRowMeta.nth(2).boundingBox(),
    firstRowMeta.nth(3).boundingBox(),
  ]);
  for (const [header,cell] of [[languageHeader,languageCell],[formatHeader,formatCell],[scoreHeader,scoreCell]]) {
    assert.ok(header && cell && Math.abs(header.x-cell.x)<1,`column is misaligned: ${header?.x} vs ${cell?.x}`);
  }
  const onlineSubtitleName=page.locator('.subtitle-online-file .subtitle-file-copy strong').first();
  await onlineSubtitleName.hover();
  const onlineNameTooltip=page.locator('.app-native-tooltip');
  await onlineNameTooltip.waitFor({state:'visible'});
  assert.match(await onlineNameTooltip.innerText(),/绿灯军团\.2026\.S01E04\.2160p\.简英双语/);
  await page.mouse.move(0,0);
  assert.equal(await page.locator('.subtitle-host-notice:visible').count(),0);
  const searchToast=await page.evaluate(()=>window.pluginToasts.at(-1));
  assert.equal(searchToast.title,'搜索完成');
  assert.match(searchToast.detail,/找到 2 条在线字幕/);
  assert.equal(await page.locator('.subtitle-online-heading').count(),0);
  assert.equal(await page.locator('.subtitle-online-file input[type="radio"]').count(),0);
  const onlineActions=page.locator('.subtitle-online-file [aria-label^="操作 "]');
  assert.equal(await onlineActions.count(),2);
  assert.equal(await page.locator('.subtitle-preview-action').count(),0);
  const bottomRow=page.locator('.subtitle-online-file').last();
  const [bottomRowBefore,bottomScrollBefore]=await Promise.all([
    bottomRow.boundingBox(),
    page.locator('.subtitle-online-results').evaluate(element=>({left:element.scrollLeft,width:element.clientWidth})),
  ]);
  await onlineActions.last().click();
  const bottomMenu=page.locator('.subtitle-row-action-menu');
  await bottomMenu.waitFor({state:'visible'});
  assert.equal(await bottomMenu.evaluate(element=>element.classList.contains('is-above')),true);
  const [bottomRowAfter,bottomScrollAfter]=await Promise.all([
    bottomRow.boundingBox(),
    page.locator('.subtitle-online-results').evaluate(element=>({left:element.scrollLeft,width:element.clientWidth})),
  ]);
  assert.ok(bottomRowBefore && bottomRowAfter && bottomRowBefore.x===bottomRowAfter.x && bottomRowBefore.width===bottomRowAfter.width);
  assert.deepEqual(bottomScrollAfter,bottomScrollBefore);
  const onlineMenu=page.locator('.subtitle-row-action-menu');
  await onlineMenu.waitFor({state:'visible'});
  assert.match(await onlineMenu.innerText(),/下载并预览/);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-online.png',fullPage:true});
  await onlineMenu.getByRole('menuitem',{name:'下载并预览'}).click();
  const previewDialog=page.getByRole('dialog',{name:'字幕预览'});
  await previewDialog.waitFor({state:'visible'});
  assert.equal(await previewDialog.locator('.subtitle-preview-file').count(),3);
  assert.match(await previewDialog.locator('.subtitle-preview-footer').innerText(),/已选择 3 \/ 3/);
  await previewDialog.locator('.subtitle-preview-file-open').nth(1).click();
  assert.match(await previewDialog.locator('.subtitle-preview-excerpt').innerText(),/这一季，故事将继续/);
  await previewDialog.locator('.subtitle-preview-select-all input').uncheck();
  assert.match(await previewDialog.locator('.subtitle-preview-footer').innerText(),/已选择 0 \/ 3/);
  assert.equal(await previewDialog.getByRole('button',{name:'保存所选'}).isDisabled(),true);
  await previewDialog.locator('.subtitle-preview-file > input').nth(1).check();
  assert.match(await previewDialog.locator('.subtitle-preview-footer').innerText(),/已选择 1 \/ 3/);
  assert.equal(await previewDialog.getByRole('button',{name:'保存所选'}).isEnabled(),true);
  await page.screenshot({path:'.build/browser-checks/subtitle-workspace-preview-dialog.png',fullPage:true});

  const mobilePage=await browser.newPage({viewport:{width:390,height:844}});
  mobilePage.on("console", message => console.log(`[mobile:${message.type()}] ${message.text()}`));
  mobilePage.on("pageerror", error => console.error(`[mobile:error] ${error.stack || error.message}`));
  await mobilePage.addInitScript(()=>Object.defineProperty(navigator,'userAgent',{get:()=> 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)'}));
  await mobilePage.goto(`http://127.0.0.1:${server.httpServer.address().port}/fixture`);
  await mobilePage.waitForFunction(()=>window.fixtureReady);
  await mobilePage.locator('.app-workspace').evaluate(element=>{element.style.padding='8px'});
  await mobilePage.locator('.subtitle-local-file').first().waitFor();
  assert.equal(await mobilePage.locator('.subtitle-layout').evaluate(element=>getComputedStyle(element).flexDirection),'column');
  assert.match(await mobilePage.locator('.subtitle-list').evaluate(element=>getComputedStyle(element).overflowX),/auto|scroll/);
  const mobileMediaScroll=await mobilePage.locator('.subtitle-list').evaluate(element=>({scrollWidth:element.scrollWidth,clientWidth:element.clientWidth,touchAction:getComputedStyle(element).touchAction}));
  assert.ok(mobileMediaScroll.scrollWidth>mobileMediaScroll.clientWidth);
  assert.equal(mobileMediaScroll.touchAction,'pan-x');
  const identityRows=await mobilePage.locator('.subtitle-identity > span').evaluateAll(elements=>elements.map(element=>element.getBoundingClientRect().y));
  assert.equal(new Set(identityRows).size,1,'media identity must stay on one line');
  assert.equal(await mobilePage.locator('.subtitle-identity').evaluate(element=>getComputedStyle(element).overflowX),'auto');
  const sidebarBox=await mobilePage.locator('.subtitle-sidebar').boundingBox();
  const mediaCardBox=await mobilePage.locator('.subtitle-media').first().boundingBox();
  assert.ok(sidebarBox && sidebarBox.x+sidebarBox.width<=390, 'media sidebar must fit the phone');
  assert.ok(mediaCardBox && mediaCardBox.width<=280, 'scrolling must not enlarge media cards');
  for (const width of [320,390,430]) {
    await mobilePage.setViewportSize({width,height:844});
    const sidebar=await mobilePage.locator('.subtitle-sidebar').boundingBox();
    const input=await mobilePage.locator('.subtitle-sidebar-tools input').boundingBox();
    const refresh=await mobilePage.locator('.subtitle-sidebar-refresh').boundingBox();
    assert.ok(input.x>=sidebar.x && input.x+input.width<refresh.x,`search must leave room for refresh at ${width}px`);
    assert.ok(refresh.x+refresh.width<=sidebar.x+sidebar.width,`refresh must stay in sidebar at ${width}px`);
    assert.ok(sidebar.x+sidebar.width<=width,`sidebar must fit viewport at ${width}px`);
  }
  await mobilePage.setViewportSize({width:390,height:844});
  const tabPositions=await mobilePage.getByRole('tab').evaluateAll(elements=>elements.map(element=>{const r=element.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}));
  const uploadButtonBox=await mobilePage.getByRole('button',{name:'上传字幕',exact:true}).boundingBox();
  assert.equal(await mobilePage.locator('.subtitle-local-columns').evaluate(element=>getComputedStyle(element).display),'none');
  assert.equal(await mobilePage.locator('.subtitle-local-file .subtitle-mobile-meta').first().isVisible(),true);
  assert.equal(await mobilePage.locator('.subtitle-local-list').evaluate(element=>getComputedStyle(element).overflowY),'auto');
  const mobileLocalBox=await mobilePage.locator('.subtitle-local-file').first().boundingBox();
  assert.ok(mobileLocalBox && mobileLocalBox.width > 330 && mobileLocalBox.height < 90,`unexpected mobile local row: ${JSON.stringify(mobileLocalBox)}`);
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-workspace-mobile-local.png',fullPage:true});
  const mobileMenuButton=mobilePage.locator('.subtitle-local-file [aria-label^="操作 "]').first();
  await mobileMenuButton.click();
  await mobilePage.locator('.subtitle-row-action-menu').waitFor({state:'visible'});
  await mobilePage.locator('.subtitle-detail-heading').click();
  assert.equal(await mobilePage.locator('.subtitle-row-action-menu').count(),0);
  await mobilePage.getByRole('button',{name:'上传字幕',exact:true}).click();
  const mobileUploadDialog=mobilePage.getByRole('dialog',{name:'上传字幕'});
  await mobileUploadDialog.waitFor({state:'visible'});
  const mobileUploadBox=await mobileUploadDialog.boundingBox();
  assert.ok(mobileUploadBox && mobileUploadBox.y>70 && mobileUploadBox.y+mobileUploadBox.height<800);
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-workspace-mobile-upload.png',fullPage:true});
  await mobilePage.getByRole('button',{name:'关闭上传字幕窗口'}).click();
  await mobilePage.getByRole('tab',{name:'在线字幕'}).click();
  const onlineTabPositions=await mobilePage.getByRole('tab').evaluateAll(elements=>elements.map(element=>{const r=element.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}));
  assert.deepEqual(onlineTabPositions,tabPositions,'switching subtitle modes must not move tabs');
  assert.equal(await mobilePage.locator('.subtitle-online-panel').evaluate(element=>getComputedStyle(element).borderTopWidth),'0px','no duplicate line below online tabs');
  const searchButton=mobilePage.getByRole('button',{name:'打开在线字幕搜索'});
  const searchButtonBox=await searchButton.boundingBox();
  assert.deepEqual(searchButtonBox,uploadButtonBox,'both actions must occupy the same space');
  const searchIconBox=await searchButton.locator('svg').boundingBox();
  assert.ok(Math.abs(searchIconBox.x+searchIconBox.width/2-searchButtonBox.x-searchButtonBox.width/2)<1);
  assert.ok(Math.abs(searchIconBox.y+searchIconBox.height/2-searchButtonBox.y-searchButtonBox.height/2)<1);
  assert.equal(await mobilePage.getByRole('textbox',{name:'在线字幕查询词'}).isVisible(),false);
  await mobilePage.getByRole('button',{name:'打开在线字幕搜索'}).click();
  const mobileOnlineSearch=mobilePage.getByRole('textbox',{name:'在线字幕查询词'});
  await mobileOnlineSearch.focus();
  await mobilePage.waitForFunction(()=>document.body.style.minHeight !== '');
  assert.equal(await mobilePage.getByRole('dialog').count(),0);
  const documentFloor=await mobilePage.evaluate(()=>document.body.style.minHeight);
  await mobilePage.setViewportSize({width:390,height:500});
  assert.equal(await mobilePage.evaluate(()=>document.body.style.minHeight),documentFloor);
  await mobilePage.setViewportSize({width:390,height:844});
  assert.equal(await mobileOnlineSearch.isVisible(),true);
  await mobileOnlineSearch.press('Enter');
  await mobilePage.getByText('绿灯军团.2026.S01E04.2160p.简英双语').waitFor();
  assert.equal(await mobilePage.locator('.subtitle-online-columns').evaluate(element=>getComputedStyle(element).display),'none');
  assert.equal(await mobilePage.locator('.subtitle-online-file .subtitle-mobile-meta').first().isVisible(),true);
  assert.equal(await mobilePage.locator('.subtitle-source-list').evaluate(element=>getComputedStyle(element).overflowX),'auto');
  assert.equal(await mobilePage.locator('.subtitle-online-results').evaluate(element=>getComputedStyle(element).overflowY),'auto');
  await mobilePage.locator('.subtitle-online-file [aria-label^="操作 "]').first().click();
  await mobilePage.getByRole('menuitem',{name:'下载并预览'}).click();
  const mobilePreviewDialog=mobilePage.getByRole('dialog',{name:'字幕预览'});
  await mobilePreviewDialog.waitFor({state:'visible'});
  const mobilePreviewBox=await mobilePreviewDialog.boundingBox();
  assert.ok(mobilePreviewBox && mobilePreviewBox.height<700 && mobilePreviewBox.y>40);
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-workspace-mobile-preview.png',fullPage:true});
  await mobilePage.getByRole('button',{name:'关闭字幕预览窗口'}).click();
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-workspace-mobile-online.png',fullPage:true});
  await mobilePage.evaluate(()=>{window.singlePreview=true});
  await mobilePage.locator('.subtitle-online-file [aria-label^="操作 "]').first().click();
  await mobilePage.getByRole('menuitem',{name:'下载并预览'}).click();
  await mobilePreviewDialog.waitFor({state:'visible'});
  const singleBodyBox=await mobilePage.locator('.subtitle-preview-dialog-body').boundingBox();
  const singleContentBox=await mobilePage.locator('.subtitle-preview-content').boundingBox();
  assert.ok(Math.abs(singleBodyBox.height-singleContentBox.height)<1,JSON.stringify({singleBodyBox,singleContentBox})+' single preview must fill the body instead of reserving an empty file-list row');
  assert.equal(await mobilePage.locator('.app-main').getAttribute('inert'),'');
  const rootScroll=await mobilePage.evaluate(()=>window.scrollY);
  await mobilePage.mouse.move(5,400);
  await mobilePage.mouse.wheel(0,500);
  assert.equal(await mobilePage.evaluate(()=>window.scrollY),rootScroll);
  const excerpt=mobilePage.locator('.subtitle-preview-excerpt');
  const excerptBox=await excerpt.boundingBox();
  const footerBox=await mobilePage.locator('.subtitle-preview-footer').boundingBox();
  assert.ok(footerBox.y-excerptBox.y-excerptBox.height<=12,'preview text must extend down to the footer');
  assert.ok(await excerpt.evaluate(element=>{element.scrollTop=100;return element.scrollTop>0}),'long preview text must scroll');
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-workspace-mobile-single-preview.png',fullPage:true});
  await mobilePage.getByRole('button',{name:'关闭字幕预览窗口'}).click();
  await mobilePage.getByRole('textbox',{name:'搜索本地媒体名称或路径'}).click();
  const mediaSearch=mobilePage.getByRole('textbox',{name:'搜索本地媒体名称或路径'});
  await mediaSearch.fill('绿灯军团');
  assert.equal(await mobilePage.getByRole('dialog').count(),0);
  await mobilePage.waitForFunction(()=>document.body.style.minHeight !== '');
  const mediaFloor=await mobilePage.evaluate(()=>document.body.style.minHeight);
  await mobilePage.setViewportSize({width:390,height:500});
  assert.equal(await mobilePage.evaluate(()=>document.body.style.minHeight),mediaFloor);
  await mobilePage.setViewportSize({width:390,height:844});
  await mediaSearch.blur();
  await mobilePage.waitForFunction(()=>document.body.style.minHeight === '');
  assert.equal(await mobilePage.locator('.app-main').getAttribute('inert'),null);
  const card=mobilePage.locator('.subtitle-browser');
  const cardBefore=await card.boundingBox();
  const outerBefore=await mobilePage.evaluate(()=>window.scrollY);
  await mobilePage.locator('.subtitle-online-file').first().evaluate(element=>{
    const parent=element.parentElement;
    for(let i=0;i<25;i++) parent.append(element.cloneNode(true));
  });
  const fixedSelectors=['.subtitle-detail-heading','.subtitle-content-tabs','.subtitle-source-filter','.subtitle-manual-actions'];
  const fixedBefore=await Promise.all(fixedSelectors.map(selector=>mobilePage.locator(selector).boundingBox()));
  const resultList=mobilePage.locator('.subtitle-online-results');
  await resultList.evaluate(element=>{element.scrollTop=element.scrollHeight});
  const fixedAfter=await Promise.all(fixedSelectors.map(selector=>mobilePage.locator(selector).boundingBox()));
  assert.deepEqual(fixedAfter,fixedBefore,'media, tabs, sources and manual footer must not move with result scrolling');
  assert.ok(fixedAfter[3].y+fixedAfter[3].height<=cardBefore.y+cardBefore.height,'manual footer must remain inside the card');
  assert.ok(await resultList.evaluate(element=>element.scrollTop>0),'only result list scrolls');
  assert.deepEqual(await card.boundingBox(),cardBefore,'card bottom must stay fixed when results grow and scroll');
  assert.equal(await mobilePage.evaluate(()=>window.scrollY),outerBefore);
  assert.equal(await card.evaluate(element=>element.scrollTop),0,'card must not scroll');
  assert.ok(cardBefore.y+cardBefore.height<=844-76,'card must clear bottom navigation');
  await mobilePage.screenshot({path:'.build/browser-checks/subtitle-fixed-online-list.png',fullPage:true});
  await mobilePage.getByRole('tab',{name:'本地字幕'}).click();
  const localTabsBefore=await mobilePage.locator('.subtitle-content-tabs').boundingBox();
  await mobilePage.locator('.subtitle-local-file').first().evaluate(element=>{
    for(let i=0;i<25;i++) element.parentElement.append(element.cloneNode(true));
  });
  const localList=mobilePage.locator('.subtitle-local-list');
  await localList.evaluate(element=>{element.scrollTop=element.scrollHeight});
  assert.ok(await localList.evaluate(element=>element.scrollTop>0));
  assert.deepEqual(await mobilePage.locator('.subtitle-content-tabs').boundingBox(),localTabsBefore);
  assert.deepEqual(await card.boundingBox(),cardBefore);
  assert.equal(await card.evaluate(element=>element.scrollTop),0);
  await mobilePage.evaluate(()=>{
    for(const [className,style] of [['mobile-shell-bar','position:fixed;top:0;height:104px;width:100%'],['mobile-shell-dock','position:fixed;bottom:12px;height:58px;width:100%']]) {
      const node=document.createElement('div');node.className=className;node.style.cssText=style;document.body.append(node);
    }
  });
  await mobilePage.waitForFunction(()=>document.querySelector('.subtitle-workspace').style.getPropertyValue('--subtitle-workspace-top')==='116px');
  const boundedCard=await card.boundingBox();
  const dock=await mobilePage.locator('.mobile-shell-dock').boundingBox();
  assert.equal(boundedCard.y,116,'card must clear the actual header including safe area');
  assert.equal(dock.y-boundedCard.y-boundedCard.height,6,'card sits six pixels above the dock');
  await mobilePage.close();
  console.log('subtitle_workspace_visual=passed');
} finally {
  await browser?.close();
  await server.close();
}
