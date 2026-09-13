// Mechanical migration of native selects; field keys and handlers stay unchanged.
import { readFileSync, writeFileSync } from 'node:fs';
const files=['media_cover_generator/StyleEditor.vue','media_cover_generator/LibraryArtworkView.vue','brush_flow/SiteTrafficView.vue','subtitle_manager/SubtitleWorkspacePage.vue'];
for(const file of files){
  const path='cinecircuit_plugins/'+file;
  let source=readFileSync(path,'utf8');
  source=source.replace(/<select\b([^>]*?)>([\s\S]*?)<\/select>/g,(_,attrs,options)=>{
    let items;
    const loop=options.match(/v-for="([^"]+)"/);
    if(loop){
      const [,variable,list]=loop[1].match(/^(.+) in (.+)$/);
      if(variable==='[value,label]') items=`${list}.map(([value,title]) => ({value,title}))`;
      else if(variable==='option') items=`${list}.map(option => ({value:option[0],title:option[1]}))`;
      else {
        const value=options.match(/:value="([^"]+)"/)[1];
        const title=options.match(/\{\{\s*([^}]+?)\s*\}\}/)[1];
        items=`${list}.map(${variable} => ({value:${value},title:${title}}))`;
      }
      if(options.includes('<option value="">')) items=`[{value:'',title:'请选择'}, ...${items}]`;
    }else{
      const rows=[...options.matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)].map(([,value,title])=>({value,title}));
      if(!rows.length)throw Error('Unparsed options '+file);
      items=JSON.stringify(rows).replaceAll('"',"'");
    }
    attrs=attrs.replace(':value=',':model-value=').replace('@change=','@update:model-value=')
      .replaceAll('inputValue($event)','$event').replaceAll('($event.target as HTMLSelectElement).value','$event');
    return `<VSelect${attrs} :items="${items}" variant="outlined" density="comfortable" hide-details />`;
  });
  source=source.replace(/<label([^>]*)><span>([^<]*)<\/span>(<VSelect[^\n]*?\/>)(<small>[^<]*<\/small>)?<\/label>/g,(_,attrs,label,control,hint='')=>
    `<div${attrs}>${control.replace('<VSelect',`<VSelect label="${label}"`)}${hint}</div>`);
  source=source.replace('<VSelect :model-value="language"','<VSelect label="字幕语言" :model-value="language"');
  // Subtitle's old handler consumed a DOM event; the component emits the value.
  source=source.replace('@update:model-value="chooseLanguage"','@update:model-value="language = $event"');
  writeFileSync(path,source);
}
