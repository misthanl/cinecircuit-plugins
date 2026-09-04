<script setup lang="ts">
import { onMounted, ref } from "vue";

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
const message = ref("");
const styles = [["single", "单图"], ["multi", "多图"], ["poster", "海报墙"], ["animated", "动态"]] as const;
const sortOptions = [["DateCreated", "入库时间"], ["PremiereDate", "首映时间"], ["Random", "随机"]] as const;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
function set(key: string, value: ConfigValue): void {
  config.value = { ...config.value, [key]: value };
}
function setInput(key: string, event: Event, numeric = false): void {
  const value = (event.target as HTMLInputElement).value;
  set(key, numeric ? Number(value) : value);
}
function toggle(key: string, value: string): void {
  const current = config.value[key];
  const selected = new Set(Array.isArray(current) ? current : []);
  if (selected.has(value)) selected.delete(value);
  else selected.add(value);
  set(key, [...selected]);
}
async function load(): Promise<void> {
  busy.value = true;
  try {
    const data = await props.request<InventoryResponse>(`/plugins/${ID}/api/inventory`);
    servers.value = data.servers || [];
    libraries.value = data.libraries || [];
    config.value = data.config || {};
  } catch (error) {
    message.value = errorMessage(error, "读取失败");
  } finally {
    busy.value = false;
  }
}
async function chooseServer(id: string): Promise<void> {
  set("selected_servers", id ? [id] : []);
  busy.value = true;
  try {
    const data = await props.request<LibrariesResponse>(`/plugins/${ID}/api/libraries?server_id=${encodeURIComponent(id)}`);
    libraries.value = data.items || [];
    set("include_libraries", []);
  } finally {
    busy.value = false;
  }
}
async function save(): Promise<void> {
  busy.value = true;
  try {
    config.value = { ...config.value, dry_run: false };
    await props.request(`/plugins/${ID}`, { method: "PATCH", body: JSON.stringify({ config: config.value }) });
    message.value = "封面设置已保存";
  } catch (error) {
    message.value = errorMessage(error, "保存失败");
  } finally {
    busy.value = false;
  }
}
async function generate(): Promise<void> {
  await save();
  busy.value = true;
  try {
    await props.request(`/plugins/${ID}/run`, { method: "POST", body: "{}" });
    message.value = "封面生成任务已加入后台队列";
  } catch (error) {
    message.value = errorMessage(error, "生成失败");
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="cover">
    <header class="cover-head">
      <div>
        <h1>媒体库视觉封面</h1>
        <p>选择媒体服务器和媒体库，再设置样式；不再要求手工填写服务器 ID。</p>
      </div>
      <div>
        <button class="alt" :disabled="busy" @click="load">刷新</button>
        <button :disabled="busy" @click="generate">{{ busy ? "处理中…" : "保存并生成" }}</button>
      </div>
    </header>
    <div class="cover-layout">
      <aside class="cover-card">
        <h2>生成范围</h2>
        <div class="cover-list">
          <label class="cover-field">
            <span>媒体服务器</span>
            <select :value="config.selected_servers?.[0] || ''" @change="chooseServer(($event.target as HTMLSelectElement).value)">
              <option value="">请选择</option>
              <option v-for="server in servers" :key="server.id" :value="server.id">{{ server.name }}</option>
            </select>
          </label>
          <label v-for="library in libraries" :key="library.id" class="cover-row">
            <input type="checkbox" :checked="(config.include_libraries || []).includes(library.id)" @change="toggle('include_libraries', library.id)">
            <span><strong>{{ library.name }}</strong><small>{{ library.collection_type || "媒体库" }}</small></span>
          </label>
        </div>
      </aside>
      <main class="cover-card">
        <div class="cover-grid">
          <div class="cover-styles">
            <button v-for="[value, label] in styles" :key="value" class="cover-style" :class="{ on: config.cover_style_base === value }" @click="set('cover_style_base', value)">{{ label }}</button>
          </div>
          <label class="cover-field"><span>输出分辨率</span><select :value="config.resolution || '480p'" @change="set('resolution', ($event.target as HTMLSelectElement).value)"><option v-for="value in ['480p', '720p', '1080p', 'custom']" :key="value" :value="value">{{ value }}</option></select></label>
          <label class="cover-field"><span>媒体排序</span><select :value="config.sort_by || 'DateCreated'" @change="set('sort_by', ($event.target as HTMLSelectElement).value)"><option v-for="[value, label] in sortOptions" :key="value" :value="value">{{ label }}</option></select></label>
          <label class="cover-field"><span>中文字号</span><input type="number" :value="config.zh_font_size ?? ''" @input="setInput('zh_font_size', $event, true)"></label>
          <label class="cover-field"><span>英文字号</span><input type="number" :value="config.en_font_size ?? ''" @input="setInput('en_font_size', $event, true)"></label>
          <label class="cover-field full"><span>媒体库标题配置</span><textarea :value="config.title_config || ''" placeholder="电影=电影|MOVIES" @input="set('title_config', ($event.target as HTMLTextAreaElement).value)" /></label>
          <label class="cover-field full"><input type="checkbox" :checked="Boolean(config.show_item_count)" @change="set('show_item_count', ($event.target as HTMLInputElement).checked)"> 显示媒体数量角标</label>
          <p class="cover-field full">{{ message }}</p>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.cover{display:grid;gap:18px;color:var(--app-text,#17243a)}.cover *{box-sizing:border-box}.cover-head,.cover-card{border:1px solid var(--app-border,#dfe5ef);border-radius:22px;background:#fff;box-shadow:0 14px 36px rgba(37,61,99,.06)}.cover-head{display:flex;justify-content:space-between;align-items:center;padding:24px}.cover h1,.cover h2{margin:0}.cover p{margin:5px 0 0;color:#71809a}.cover button{min-height:41px;padding:0 16px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.cover button.alt{background:#edf3ff;color:#245fc4}.cover-layout{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.25fr);gap:16px}.cover-card{padding:20px}.cover-list{display:grid;gap:9px;margin-top:14px}.cover-row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;padding:12px;border:1px solid #e0e6ef;border-radius:13px;background:#f8fafc}.cover-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cover-field{display:grid;gap:6px}.cover-field.full{grid-column:1/-1}.cover-field span{font-size:13px;font-weight:700;color:#60708a}.cover-field input,.cover-field select,.cover-field textarea{width:100%;min-height:42px;padding:0 12px;border:1px solid #d7dfeb;border-radius:11px;background:#fff}.cover-field textarea{min-height:90px;padding-top:10px}.cover-styles{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.cover-style{padding:14px 8px!important;background:#f0f4fa!important;color:#43536b!important}.cover-style.on{background:#2f74f6!important;color:#fff!important}@media(max-width:820px){.cover-layout{grid-template-columns:1fr}.cover-grid{grid-template-columns:1fr}.cover-field.full{grid-column:auto}.cover-styles{grid-column:auto;grid-template-columns:repeat(2,1fr)}.cover-head{align-items:stretch;flex-direction:column;gap:14px}}
</style>
