import type { CineCircuitPluginSdk } from "@cinecircuit/plugin-sdk";
import type { Ref } from "vue";

const PLUGIN_ID = "auto-signin";
const STYLE = `
.signin-page{display:grid;gap:18px;color:var(--app-text,#17243a)}.signin-hero,.signin-panel{border:1px solid var(--app-border,#dde4ef);border-radius:22px;background:var(--app-surface,#fff);box-shadow:0 16px 38px rgba(37,61,99,.06)}.signin-hero{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:24px}.signin-hero h1{margin:0;font-size:30px}.signin-hero p,.signin-panel p{margin:5px 0 0;color:var(--app-text-muted,#71809a)}.signin-actions{display:flex;gap:10px}.signin-button{min-height:42px;padding:0 16px;border:0;border-radius:12px;background:#2f74f6;color:#fff;font-weight:750;cursor:pointer}.signin-button.secondary{background:#edf3ff;color:#225fc7}.signin-button:disabled{opacity:.5}.signin-panel{padding:22px}.signin-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.signin-panel h2{margin:0;font-size:20px}.signin-sites{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.signin-site{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:16px;border:1px solid var(--app-border,#dde4ef);border-radius:16px;background:var(--app-surface-muted,#f7f9fc)}.signin-site strong,.signin-site small{display:block}.signin-site small{margin-top:4px;color:var(--app-text-muted,#71809a)}.signin-modes{display:flex;gap:8px;align-items:center}.signin-modes label{display:flex;gap:5px;align-items:center;font-size:13px}.signin-result{grid-column:1/-1;margin:0;padding-top:9px;border-top:1px solid var(--app-border,#dde4ef);font-size:13px}.signin-result.ok{color:#16865b}.signin-result.bad{color:#d04444}.signin-empty{padding:34px;text-align:center;color:var(--app-text-muted,#71809a)}@media(max-width:640px){.signin-hero,.signin-panel-head{align-items:stretch;flex-direction:column}.signin-actions{display:grid}.signin-site{grid-template-columns:1fr}.signin-modes{justify-content:flex-start}}
.signin-sites{grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))}@media(max-width:640px){.signin-modes{flex-wrap:wrap}}
`;

interface SiteItem {
  id: string;
  name: string;
  enabled?: boolean;
}

interface SigninResult {
  ok?: boolean;
  message?: string;
  status?: string;
}

interface InventoryResponse {
  items?: SiteItem[];
  config?: Record<string, unknown>;
  selected?: { sign_sites?: string[]; login_sites?: string[] };
}

export function install(sdk: CineCircuitPluginSdk) {
  const { defineComponent, h, onMounted, ref } = sdk.vue;
  const Page = defineComponent({
  name: "SiteCheckinPage",
    setup() {
      const sites = ref<SiteItem[]>([]);
      const signSites = ref<string[]>([]);
      const loginSites = ref<string[]>([]);
      const loading = ref(false);
      const saving = ref(false);
      const running = ref("");
      const results = ref<Record<string, SigninResult>>({});
      const config = ref<Record<string, unknown>>({});
      const message = ref("");

      async function load() {
        loading.value = true;
        try {
          const data = await sdk.request<InventoryResponse>(`/plugins/${PLUGIN_ID}/api/inventory`);
          sites.value = Array.isArray(data?.items) ? data.items : [];
          config.value = data?.config && typeof data.config === "object" ? data.config : {};
          signSites.value = Array.isArray(data?.selected?.sign_sites) ? data.selected.sign_sites : [];
          loginSites.value = Array.isArray(data?.selected?.login_sites) ? data.selected.login_sites : [];
        } catch (error) {
          message.value = error instanceof Error ? error.message : "站点读取失败";
        } finally { loading.value = false; }
      }
      function toggle(list: Ref<string[]>, id: string, checked: boolean) {
        const values = new Set(list.value);
        checked ? values.add(id) : values.delete(id);
        list.value = [...values];
      }
      async function save() {
        saving.value = true;
        try {
          await sdk.request(`/plugins/${PLUGIN_ID}`, { method: "PATCH", body: JSON.stringify({ config: { ...config.value, sign_sites: signSites.value, login_sites: loginSites.value } }) });
          config.value = { ...config.value, sign_sites: signSites.value, login_sites: loginSites.value };
          message.value = "站点选择已保存";
        } catch (error) { message.value = error instanceof Error ? error.message : "保存失败"; }
        finally { saving.value = false; }
      }
      async function runSite(site: SiteItem, mode: "sign" | "login") {
        running.value = `${site.id}:${mode}`;
        try {
          const result = await sdk.request<SigninResult>(`/plugins/${PLUGIN_ID}/api/site`, { method: "POST", body: JSON.stringify({ site_id: site.id, mode }) });
          results.value = { ...results.value, [site.id]: result };
        } catch (error) {
          results.value = { ...results.value, [site.id]: { ok: false, message: error instanceof Error ? error.message : "执行失败" } };
        } finally { running.value = ""; }
      }
      onMounted(load);
      return () => h("section", { class: "signin-page" }, [
        h("style", STYLE),
        h("header", { class: "signin-hero" }, [
        h("div", [h("h1", "站点签到助手"), h("p", "勾选需要每日签到或仅保持登录的站点；保存后由插件定时执行。")]),
          h("div", { class: "signin-actions" }, [
            h("button", { class: "signin-button secondary", disabled: loading.value, onClick: load }, loading.value ? "读取中…" : "刷新站点"),
            h("button", { class: "signin-button", disabled: saving.value, onClick: save }, saving.value ? "保存中…" : "保存选择"),
          ]),
        ]),
        h("main", { class: "signin-panel" }, [
          h("div", { class: "signin-panel-head" }, [h("div", [h("h2", "站点列表"), h("p", "签到与保持登录可以分别选择；单站测试不会修改选择。")]), h("span", message.value)]),
          sites.value.length ? h("div", { class: "signin-sites" }, sites.value.map((site) => {
            const result = results.value[site.id];
            return h("article", { class: "signin-site" }, [
              h("div", [h("strong", site.name), h("small", site.enabled ? "站点已启用" : "站点已停用")]),
              h("div", { class: "signin-modes" }, [
                h("label", [h("input", { type: "checkbox", checked: signSites.value.includes(site.id), onChange: (event: Event) => toggle(signSites, site.id, (event.currentTarget as HTMLInputElement).checked) }), "每日签到"]),
                h("label", [h("input", { type: "checkbox", checked: loginSites.value.includes(site.id), onChange: (event: Event) => toggle(loginSites, site.id, (event.currentTarget as HTMLInputElement).checked) }), "保持登录"]),
                h("button", { class: "signin-button secondary", disabled: Boolean(running.value), onClick: () => runSite(site, "sign") }, running.value === `${site.id}:sign` ? "执行中…" : "测试"),
              ]),
              result ? h("p", { class: ["signin-result", result.ok ? "ok" : "bad"] }, result.message || result.status) : null,
            ]);
          })) : h("div", { class: "signin-empty" }, loading.value ? "正在读取站点…" : "尚未配置 PT 站点"),
        ]),
      ]);
    },
  });
  sdk.registerPage({ pluginId: PLUGIN_ID, route: `plugin-${PLUGIN_ID}`, title: "自动签到", icon: "mdi-calendar-check-outline", section: "tools", order: 72, component: Page });
}
