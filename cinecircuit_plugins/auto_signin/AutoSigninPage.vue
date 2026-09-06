<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

interface SiteItem { id: string; name: string; enabled?: boolean }
interface SigninResult { ok?: boolean; message?: string; status?: string; mode?: "sign" | "login"; site_name?: string }
interface HistoryItem {
  item_key?: string;
  status?: string;
  updated_at?: string;
  payload?: { site_id?: string; site_name?: string; mode?: "sign" | "login" };
  result?: SigninResult;
}
interface InventoryResponse {
  items?: SiteItem[];
  config?: Record<string, unknown>;
  selected?: { sign_sites?: string[]; login_sites?: string[] };
  history?: HistoryItem[];
}
type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

const props = defineProps<{ request: Requester }>();
const sites = ref<SiteItem[]>([]);
const signSites = ref<string[]>([]);
const loginSites = ref<string[]>([]);
const loading = ref(false);
const saving = ref(false);
const running = ref("");
const results = ref<Record<string, SigninResult>>({});
const history = ref<HistoryItem[]>([]);
const config = ref<Record<string, unknown>>({});
const message = ref("");
const recentSuccess = computed(() => history.value.filter((item) => item.status === "signed").length);

async function load() {
  loading.value = true;
  try {
    const data = await props.request<InventoryResponse>("/plugins/auto-signin/api/inventory");
    sites.value = Array.isArray(data?.items) ? data.items : [];
    config.value = data?.config && typeof data.config === "object" ? data.config : {};
    signSites.value = Array.isArray(data?.selected?.sign_sites) ? data.selected.sign_sites : [];
    loginSites.value = Array.isArray(data?.selected?.login_sites) ? data.selected.login_sites : [];
    history.value = Array.isArray(data?.history) ? data.history : [];
  } catch (error) {
    message.value = error instanceof Error ? error.message : "站点读取失败";
  } finally { loading.value = false; }
}

function toggle(target: "sign" | "login", id: string, checked: boolean) {
  const list = target === "sign" ? signSites : loginSites;
  const values = new Set(list.value);
  checked ? values.add(id) : values.delete(id);
  list.value = [...values];
}

async function save() {
  saving.value = true;
  try {
    await props.request("/plugins/auto-signin", { method: "PATCH", body: JSON.stringify({ config: { ...config.value, sign_sites: signSites.value, login_sites: loginSites.value } }) });
    config.value = { ...config.value, sign_sites: signSites.value, login_sites: loginSites.value };
    message.value = "站点选择已保存";
  } catch (error) { message.value = error instanceof Error ? error.message : "保存失败"; }
  finally { saving.value = false; }
}

async function runSite(site: SiteItem, mode: "sign" | "login") {
  const key = `${site.id}:${mode}`;
  running.value = key;
  try {
    const result = await props.request<SigninResult>("/plugins/auto-signin/api/site", { method: "POST", body: JSON.stringify({ site_id: site.id, mode }) });
    results.value = { ...results.value, [key]: { ...result, mode, site_name: site.name } };
  } catch (error) {
    results.value = { ...results.value, [key]: { ok: false, mode, site_name: site.name, message: error instanceof Error ? error.message : "执行失败" } };
  } finally { running.value = ""; }
}

function resultFor(siteId: string, mode: "sign" | "login"): SigninResult | undefined {
  const live = results.value[`${siteId}:${mode}`];
  if (live) return live;
  const saved = history.value.find((item) => item.payload?.site_id === siteId && item.payload?.mode === mode);
  return saved?.result;
}

function resultText(result: SigninResult | undefined, mode: "sign" | "login"): string {
  if (!result) return "暂无执行记录";
  if (result.message) return result.message;
  if (result.ok) return mode === "login" ? "登录状态正常" : "签到完成";
  return result.status || "执行失败";
}

function eventChecked(event: Event) { return (event.currentTarget as HTMLInputElement).checked; }
onMounted(load);
</script>

<template>
  <section class="signin-page">
    <header class="signin-hero">
      <div><h1>站点签到助手</h1><p>勾选需要每日签到或仅保持登录的站点；保存后由插件定时执行。</p></div>
      <div class="signin-actions">
        <button class="signin-button secondary" :disabled="loading" @click="load">{{ loading ? "读取中…" : "刷新站点" }}</button>
        <button class="signin-button" :disabled="saving" @click="save">{{ saving ? "保存中…" : "保存选择" }}</button>
      </div>
    </header>
    <div class="signin-stats" aria-label="任务数据统计">
      <div><span>已配置站点</span><strong>{{ sites.length }}</strong></div>
      <div><span>保持登录</span><strong>{{ loginSites.length }}</strong></div>
      <div><span>每日签到</span><strong>{{ signSites.length }}</strong></div>
      <div><span>最近成功</span><strong>{{ recentSuccess }}</strong></div>
    </div>
    <main class="signin-panel">
      <div class="signin-panel-head"><div><h2>站点状态</h2><p>分别检查保持登录与每日签到，结果按站点保存。</p></div><span>{{ message }}</span></div>
      <div v-if="sites.length" class="signin-sites">
        <article v-for="site in sites" :key="site.id" class="signin-site">
          <div><strong>{{ site.name }}</strong><small>{{ site.enabled ? "站点已启用" : "站点已停用" }}</small></div>
          <div class="signin-modes">
            <label><input type="checkbox" :checked="loginSites.includes(site.id)" @change="toggle('login', site.id, eventChecked($event))">保持登录</label>
            <label><input type="checkbox" :checked="signSites.includes(site.id)" @change="toggle('sign', site.id, eventChecked($event))">每日签到</label>
          </div>
          <div class="signin-checks">
            <div>
              <span>保持登录</span>
              <p :class="['signin-result', { ok: resultFor(site.id, 'login')?.ok, bad: resultFor(site.id, 'login') && !resultFor(site.id, 'login')?.ok }]">{{ resultText(resultFor(site.id, 'login'), 'login') }}</p>
              <button class="signin-button secondary compact" :disabled="Boolean(running)" @click="runSite(site, 'login')">{{ running === `${site.id}:login` ? "检查中…" : "检查登录" }}</button>
            </div>
            <div>
              <span>每日签到</span>
              <p :class="['signin-result', { ok: resultFor(site.id, 'sign')?.ok, bad: resultFor(site.id, 'sign') && !resultFor(site.id, 'sign')?.ok }]">{{ resultText(resultFor(site.id, 'sign'), 'sign') }}</p>
              <button class="signin-button secondary compact" :disabled="Boolean(running)" @click="runSite(site, 'sign')">{{ running === `${site.id}:sign` ? "执行中…" : "测试签到" }}</button>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="signin-empty">{{ loading ? "正在读取站点…" : "尚未配置 PT 站点" }}</div>
    </main>
  </section>
</template>

<style>
.signin-page{display:grid;gap:18px;color:var(--app-text,#17243a)}.signin-hero,.signin-panel,.signin-stats{border:1px solid var(--app-border,#dde4ef);border-radius:22px;background:var(--app-surface,#fff);box-shadow:0 16px 38px rgba(37,61,99,.06)}.signin-hero{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:24px}.signin-hero h1{margin:0;font-size:30px}.signin-hero p,.signin-panel p{margin:5px 0 0;color:var(--app-text-muted,#71809a)}.signin-actions{display:flex;gap:10px}.signin-button{min-height:42px;padding:0 16px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.signin-button.secondary{background:#edf3ff;color:#225fc7}.signin-button.compact{min-height:32px;padding:0 11px;font-size:12px}.signin-button:disabled{opacity:.5}.signin-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:hidden}.signin-stats>div{display:grid;gap:5px;padding:17px 20px;border-right:1px solid var(--app-border,#dde4ef)}.signin-stats>div:last-child{border-right:0}.signin-stats span,.signin-checks span{color:var(--app-text-muted,#71809a);font-size:12px}.signin-stats strong{font-size:24px}.signin-panel{padding:22px}.signin-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.signin-panel h2{margin:0;font-size:20px}.signin-sites{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:12px}.signin-site{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:16px;border:1px solid var(--app-border,#dde4ef);border-radius:16px;background:var(--app-surface-muted,#f7f9fc)}.signin-site strong,.signin-site small{display:block}.signin-site small{margin-top:4px;color:var(--app-text-muted,#71809a)}.signin-modes{display:flex;gap:10px;align-items:center}.signin-modes label{display:flex;gap:5px;align-items:center;font-size:13px}.signin-checks{display:grid;grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;overflow:hidden;border:1px solid var(--app-border,#dde4ef);border-radius:12px;background:var(--app-border,#dde4ef)}.signin-checks>div{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:4px 10px;padding:11px;background:var(--app-surface,#fff)}.signin-result{min-width:0;margin:0!important;overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.signin-result.ok{color:#16865b!important}.signin-result.bad{color:#d04444!important}.signin-empty{padding:34px;text-align:center;color:var(--app-text-muted,#71809a)}@media(max-width:720px){.signin-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.signin-stats>div:nth-child(2){border-right:0}.signin-stats>div:nth-child(-n+2){border-bottom:1px solid var(--app-border,#dde4ef)}.signin-checks{grid-template-columns:1fr}}@media(max-width:640px){.signin-hero,.signin-panel-head{align-items:stretch;flex-direction:column}.signin-actions{display:grid}.signin-site{grid-template-columns:1fr}.signin-modes{justify-content:flex-start;flex-wrap:wrap}}
</style>
