<script setup lang="ts">
import { onMounted, ref } from "vue";
import StyleEditorView from "./StyleEditor.vue";
import TargetSelector from "./TargetSelector.vue";

const ID = "emby-cover-generator";
type ConfigValue = string | number | boolean | string[];
interface CoverConfig {
  [key: string]: ConfigValue | undefined;
  selected_servers?: string[];
  include_libraries?: string[];
  dry_run?: boolean;
  cover_style_base?: string;
  resolution?: string;
  sort_by?: string;
  title_config?: string;
  show_item_count?: boolean;
  zh_font_preset?: string;
  en_font_preset?: string;
}
interface MediaServer { id: string; name: string }
interface MediaLibrary { id: string; name: string; collection_type?: string }
interface InventoryResponse { servers?: MediaServer[]; libraries?: MediaLibrary[]; config?: CoverConfig }
interface LibrariesResponse { items?: MediaLibrary[] }
type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

const props = defineProps<{ request: Requester }>();
const servers = ref<MediaServer[]>([]);
const libraries = ref<MediaLibrary[]>([]);
const config = ref<CoverConfig>({});
const busy = ref(false);
const loaded = ref(false);
const message = ref("");
const zhFonts = [
  { value: "wendao", label: "文道潮黑" },
  { value: "cuyasong", label: "粗雅宋" },
  { value: "modern", label: "现代黑体", stack: "'Microsoft YaHei', 'Noto Sans SC', sans-serif" },
  { value: "bold", label: "电影粗黑", stack: "Impact, 'Microsoft YaHei', sans-serif" },
  { value: "serif", label: "典雅宋体", stack: "SimSun, 'Noto Serif SC', serif" },
] as const;
const enFonts = [
  ...['emblemaone','melete','phosphate','josefinsans','lilitaone','monoton','plaster'].map(value => ({value})),
  { value: "inter", label: "Inter 简洁", stack: "Inter, Arial, sans-serif" },
  { value: "cinema", label: "Cinema 宽体", stack: "Impact, 'Arial Narrow', sans-serif" },
  { value: "editorial", label: "Editorial 衬线", stack: "Georgia, 'Times New Roman', serif" },
] as const;


function errorMessage(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback; }
function set(key: string, value: ConfigValue): void { config.value = { ...config.value, [key]: value }; }
function toggle(key: string, value: string): void {
  const current = config.value[key];
  const selected = new Set(Array.isArray(current) ? current : []);
  if (selected.has(value)) selected.delete(value); else selected.add(value);
  set(key, [...selected]);
}
async function load(): Promise<void> {
  busy.value = true;
  try {
    const data = await props.request<InventoryResponse>(`/plugins/${ID}/api/inventory`);
    servers.value = data.servers || [];
    libraries.value = data.libraries || [];
    const loaded = data.config || {};
    const zhPreset = zhFonts.some(item => item.value === loaded.zh_font_preset) ? loaded.zh_font_preset : "wendao";
    const enPreset = enFonts.some(item => item.value === loaded.en_font_preset) ? loaded.en_font_preset : "emblemaone";
    config.value = { cover_style_base: "multi", ...loaded, zh_font_preset: zhPreset, en_font_preset: enPreset };
  } catch (error) { message.value = errorMessage(error, "读取失败"); }
  finally { busy.value = false; loaded.value=true; }
}
async function chooseServer(id: string): Promise<void> {
  set("selected_servers", id ? [id] : []);
  busy.value = true;
  try {
    const data = await props.request<LibrariesResponse>(`/plugins/${ID}/api/libraries?server_id=${encodeURIComponent(id)}`);
    libraries.value = data.items || [];
    set("include_libraries", []);
  } finally { busy.value = false; }
}
async function save(): Promise<boolean> {
  busy.value = true;
  try {
    config.value = { ...config.value, dry_run: false };
    await props.request(`/plugins/${ID}`, { method: "PATCH", body: JSON.stringify({ config: config.value }) });
    message.value = "封面设置已保存";
    return true;
  } catch (error) { message.value = errorMessage(error, "保存失败"); return false; }
  finally { busy.value = false; }
}
async function generate(): Promise<void> {
  if (!await save()) return;
  busy.value = true;
  try {
    await props.request(`/plugins/${ID}/run`, { method: "POST", body: "{}" });
    message.value = "封面生成任务已加入后台队列";
  } catch (error) { message.value = errorMessage(error, "生成失败"); }
  finally { busy.value = false; }
}
onMounted(load);
</script>

<template>
  <section class="cover">
    <header class="cover-head">
      <div><span class="eyebrow">LIBRARY ARTWORK STUDIO</span><h1>媒体库视觉封面</h1><p>选择媒体库与构图，确认设置后生成。样例展示构图，实际封面使用媒体库图片。</p></div>
      <div class="head-actions"><button class="alt" :disabled="busy" @click="load">刷新</button><button :disabled="busy" @click="generate">{{ busy ? "处理中…" : "保存并生成" }}</button></div>
    </header>
    <div class="cover-layout">
      <aside class="cover-card scope-card">
        <div class="section-title"><span>生成范围</span></div>
        <TargetSelector v-if="loaded" :model-value="config" :disabled="busy" :request="request" @update:model-value="config=$event as CoverConfig" />
      </aside>
      <main class="studio">
        <section class="cover-card settings-card">
          <StyleEditorView :model-value="config" :disabled="busy" :request="request" @update:model-value="config = $event as CoverConfig" />
          <p v-if="message" class="status">{{ message }}</p>
        </section>
      </main>
    </div>
  </section>
</template>

<style scoped>
.cover{--ink:#182036;--muted:#748098;--line:#dfe4ee;--paper:#fff;--blue:#4969dc;--amber:#ffb64d;display:grid;gap:18px;color:var(--app-text,var(--ink));font-family:Inter,"Microsoft YaHei",sans-serif}.cover *{box-sizing:border-box}.cover-head,.cover-card,.preview-card{border:1px solid var(--app-border,var(--line));border-radius:20px;background:var(--app-surface,var(--paper));box-shadow:0 12px 34px rgba(30,43,78,.065)}.cover-head{display:flex;justify-content:space-between;align-items:center;padding:24px 26px}.eyebrow{display:block;margin-bottom:6px;color:var(--blue);font-size:10px;font-weight:850;letter-spacing:.18em}.cover h1{margin:0;font-size:26px;letter-spacing:-.04em}.cover p{margin:6px 0 0;color:var(--muted);font-size:13px}.head-actions{display:flex;gap:9px}.cover button{min-height:42px;padding:0 17px;border:0;border-radius:11px;background:var(--blue);color:#fff;font:inherit;font-weight:760;cursor:pointer;transition:transform .18s ease,box-shadow .18s ease}.cover button:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 7px 16px rgba(73,105,220,.22)}.cover button:focus-visible,.cover input:focus-visible,.cover select:focus-visible,.cover textarea:focus-visible{outline:3px solid rgba(73,105,220,.24);outline-offset:2px}.cover button:disabled{cursor:wait;opacity:.58}.cover button.alt{background:#edf1ff;color:#3656c4}.cover-layout{display:grid;grid-template-columns:minmax(250px,.62fr) minmax(0,1.55fr);gap:16px;align-items:start}.cover-card{padding:20px}.scope-card{position:sticky;top:12px}.section-title{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:15px}.section-title>span{font-size:15px;font-weight:820}.section-title small{color:#9099aa;font-size:11px}.cover-list{display:grid;gap:8px;margin-top:14px}.server-field{padding-bottom:15px;border-bottom:1px solid var(--line)}.cover-row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;padding:11px;border:1px solid var(--line);border-radius:12px;background:#f8f9fc;cursor:pointer;transition:border-color .18s,background .18s}.cover-row.selected{border-color:#aab9f2;background:#f0f3ff}.cover-row input{accent-color:var(--blue)}.cover-row span{display:grid}.cover-row strong{font-size:13px}.cover-row small{margin-top:2px;color:#8b95a8;font-size:10px;text-transform:uppercase}.empty{padding:14px;border:1px dashed #cfd6e4;border-radius:12px;text-align:center}.studio{display:grid;gap:16px}.preview-card{padding:12px;background:#f1f3f8}.preview-topline{display:flex;justify-content:space-between;padding:1px 4px 9px;color:#68738a;font-size:11px;font-weight:750}.artwork{position:relative;overflow:hidden;aspect-ratio:16/9;border-radius:14px;background:#182035;isolation:isolate}.artwork-images,.artwork-shade{position:absolute;inset:0}.artwork-images i{position:absolute;overflow:hidden;background:#52617d;box-shadow:inset 0 0 0 1px rgba(255,255,255,.14)}.artwork-images i::after{content:"";position:absolute;inset:0;background:linear-gradient(145deg,rgba(255,255,255,.32),transparent 40%),linear-gradient(160deg,#7587ac,#293247 62%,#e19b66)}.artwork-images i:nth-child(2)::after{background:linear-gradient(140deg,#df9b73,#702f47 42%,#1e2744)}.artwork-images i:nth-child(3)::after{background:linear-gradient(150deg,#9eb4c9,#486476 45%,#19253d)}.artwork-images i:nth-child(4)::after{background:linear-gradient(150deg,#bf7e5c,#3e4f68 54%,#172134)}.artwork-images i:nth-child(5)::after{background:linear-gradient(155deg,#dcc18c,#64554b 48%,#242a39)}.style-single .artwork-images i:first-child{inset:0}.style-single .artwork-images i:not(:first-child){display:none}.style-multi .artwork-images i:nth-child(1){inset:0 50% 50% 0}.style-multi .artwork-images i:nth-child(2){inset:0 25% 50% 50%}.style-multi .artwork-images i:nth-child(3){inset:0 0 50% 75%}.style-multi .artwork-images i:nth-child(4){inset:50% 32% 0 0}.style-multi .artwork-images i:nth-child(5){inset:50% 0 0 68%}.style-poster .artwork-images{display:flex;gap:2.1%;padding:5% 0 5% 31%;transform:rotate(-1deg)}.style-poster .artwork-images i{position:relative;flex:0 0 28%;height:100%;border-radius:5px}.style-animated .artwork-images i:first-child{inset:0}.style-animated .artwork-images i:nth-child(2){inset:0;opacity:.3;transform:translateX(7%);filter:blur(2px)}.style-animated .artwork-images i:nth-child(n+3){display:none}.artwork-shade{z-index:2;background:linear-gradient(90deg,rgba(8,12,23,.94) 0%,rgba(8,12,23,.55) 45%,transparent 76%),linear-gradient(0deg,rgba(5,9,17,.68),transparent 45%)}.artwork-copy{position:absolute;z-index:3;left:6.5%;bottom:12%;display:grid;gap:7px;color:#fff}.artwork-copy::before{content:"";width:48px;height:5px;margin-bottom:2px;border-radius:9px;background:var(--amber)}.artwork-copy b{max-width:46vw;line-height:1;letter-spacing:-.06em}.artwork-copy span{color:#e1e7f2;letter-spacing:.18em}.count-badge{position:absolute;z-index:3;top:7%;left:6.5%;padding:6px 10px;border:1px solid rgba(255,182,77,.7);border-radius:99px;background:rgba(7,12,22,.68);color:#fff;font-size:9px;font-weight:800;letter-spacing:.1em}.motion-mark{position:absolute;z-index:3;top:7%;right:4%;display:flex;gap:6px;align-items:center;padding:6px 9px;border-radius:99px;background:rgba(7,12,22,.68);color:#fff;font-size:9px}.motion-mark i{width:6px;height:6px;border-radius:50%;background:#ff6d67;box-shadow:0 0 0 4px rgba(255,109,103,.2);animation:pulse 1.4s infinite}.preview-note{padding:0 4px}.settings-card{padding:22px}.cover-styles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.cover-style{position:relative;display:grid!important;grid-template-columns:92px 1fr!important;gap:12px;align-items:center;min-height:82px!important;padding:9px!important;border:1px solid var(--line)!important;background:#fafbfc!important;color:var(--ink)!important;text-align:left}.cover-style.on{border-color:var(--blue)!important;background:#f2f4ff!important;box-shadow:0 0 0 1px var(--blue)!important}.cover-style:hover:not(:disabled){box-shadow:none!important}.style-copy{display:grid;gap:4px}.style-copy strong{font-size:13px}.style-copy small{color:#7d879a;font-size:10px;line-height:1.35}.style-check{position:absolute;top:7px;right:8px;display:grid;width:18px;height:18px;place-items:center;border-radius:50%;background:var(--blue);color:#fff;font-size:10px;opacity:0;transform:scale(.7);transition:.18s}.cover-style.on .style-check{opacity:1;transform:scale(1)}.style-thumb{position:relative;display:block;overflow:hidden;width:92px;aspect-ratio:16/9;border-radius:7px;background:#232c40}.style-thumb i{position:absolute;background:linear-gradient(145deg,#97a9ca,#3e4c69 55%,#c88063)}.mini-single .style-thumb i:first-child{inset:0}.mini-single .style-thumb i:nth-child(n+2){display:none}.mini-multi .style-thumb i:nth-child(1){inset:0 50% 50% 0}.mini-multi .style-thumb i:nth-child(2){inset:0 0 50% 50%;background:linear-gradient(145deg,#dc9e73,#69344e)}.mini-multi .style-thumb i:nth-child(3){inset:50% 35% 0 0;background:#537082}.mini-multi .style-thumb i:nth-child(4){inset:50% 0 0 65%;background:#a47258}.mini-multi .style-thumb i:nth-child(5){display:none}.mini-poster .style-thumb{display:flex;gap:3px;padding:5px 3px 5px 28px}.mini-poster .style-thumb i{position:relative;flex:0 0 19px;height:42px;border-radius:2px}.mini-animated .style-thumb i:first-child{inset:0}.mini-animated .style-thumb i:nth-child(2){inset:0;background:linear-gradient(145deg,#dc9e73,#69344e);opacity:.45;transform:translateX(12px)}.mini-animated .style-thumb i:nth-child(n+3){display:none}.divider{height:1px;margin:20px 0;background:var(--line)}.cover-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.cover-field{display:grid;gap:6px}.cover-field.full,.toggle-field.full,.status.full{grid-column:1/-1}.cover-field>span{font-size:12px;font-weight:730;color:#56627a}.cover-field>span small{font-weight:500;color:#9aa2b2}.cover-field input,.cover-field select,.cover-field textarea{width:100%;min-height:42px;padding:0 11px;border:1px solid #d6dce7;border-radius:10px;background:var(--paper);color:var(--ink);font:inherit;font-size:13px}.cover-field textarea{min-height:76px;padding-top:10px;resize:vertical}.toggle-field{display:flex;gap:9px;align-items:center;font-size:13px}.toggle-field input{accent-color:var(--blue)}.status{margin:0!important;padding:10px 12px;border-radius:9px;background:#edf6f2!important;color:#33715a!important}.cover select{cursor:pointer}@keyframes pulse{50%{box-shadow:0 0 0 7px rgba(255,109,103,0)}}@media(prefers-reduced-motion:reduce){.cover *{animation:none!important;transition:none!important}}@media(max-width:900px){.cover-layout{grid-template-columns:1fr}.scope-card{position:static}.cover-styles{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.cover-head{align-items:stretch;flex-direction:column;gap:15px}.head-actions{display:grid;grid-template-columns:1fr 1fr}.cover-styles,.cover-grid{grid-template-columns:1fr}.cover-field.full,.toggle-field.full,.status.full{grid-column:auto}.artwork-copy b{font-size:30px!important}.artwork-copy span{font-size:10px!important}.cover-style{grid-template-columns:84px 1fr!important}.style-thumb{width:84px}}
</style>
