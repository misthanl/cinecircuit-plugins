const ID = "cookiecloud";
const STYLE = `
.cookie-overview { display: grid; gap: 18px; min-width: 0; color: var(--app-text); }
.cookie-tone--neutral { --cookie-tone: var(--app-text-secondary); }
.cookie-tone--primary { --cookie-tone: rgb(var(--v-theme-primary)); }
.cookie-tone--success { --cookie-tone: rgb(var(--v-theme-success)); }
.cookie-tone--error { --cookie-tone: rgb(var(--v-theme-error)); }
.cookie-tone--muted { --cookie-tone: var(--app-text-muted); }
.cookie-overview__heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-top: 6px; }
.cookie-overview__heading h3 { margin: 0; font-size: 15px; font-weight: 650; }
.cookie-overview__heading > span { color: var(--app-text-muted); font-size: 12px; }
.cookie-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0; }
.cookie-metric { padding: 15px 16px 13px; border: 1px solid color-mix(in srgb, var(--cookie-tone) 15%, transparent); border-radius: 12px; background: color-mix(in srgb, var(--cookie-tone) 5%, transparent); }
.cookie-metric dt { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: 12px; }
.cookie-metric dt .v-icon { color: var(--cookie-tone); }
.cookie-metric dd { display: flex; align-items: baseline; gap: 6px; margin: 12px 0 0; color: var(--cookie-tone); font-family: "Bahnschrift", "Aptos", sans-serif; font-size: 32px; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.1; }
.cookie-metric dd > span { color: var(--app-text-muted); font-family: inherit; font-size: 11px; font-weight: 400; }
.cookie-results { display: grid; gap: 12px; }
.cookie-results__bar { display: flex; gap: 4px; height: 6px; overflow: hidden; border-radius: 4px; }
.cookie-results__bar > span { min-width: 2px; background: var(--cookie-tone); }
.cookie-results__legend { display: flex; flex-wrap: wrap; gap: 10px 20px; padding: 0; margin: 0; list-style: none; }
.cookie-results__legend li { display: flex; align-items: center; gap: 7px; color: var(--app-text-secondary); font-size: 12px; }
.cookie-results__legend i { width: 6px; height: 6px; border-radius: 50%; background: var(--cookie-tone); }
.cookie-results__legend strong { color: var(--app-text); font-variant-numeric: tabular-nums; }
.cookie-results p { margin: 0; color: var(--app-text-muted); font-size: 11px; }
.cookie-results .cookie-results__empty { padding: 8px 0; font-size: 13px; }
.cookie-schedule { display: flex; align-items: center; gap: 12px; padding: 18px 0 2px; border-top: 1px solid var(--app-border-subtle); }
.cookie-schedule__icon { display: grid; place-items: center; width: 42px; height: 42px; flex: 0 0 auto; border-radius: 12px; color: rgb(var(--v-theme-primary)); background: rgba(var(--v-theme-primary), .08); }
.cookie-schedule__time { display: grid; flex: 1; gap: 5px; min-width: 0; }
.cookie-schedule__time > span { color: var(--app-text-muted); font-size: 12px; }
.cookie-schedule__time strong { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .cookie-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .cookie-schedule { flex-wrap: wrap; }
}

.cc-statistics-dialog{display:flex;flex-direction:column;max-height:calc(100dvh - 32px);border:1px solid var(--app-border);border-radius:18px!important;background:var(--app-dialog-surface)!important;color:var(--app-text)}
.cc-statistics-header{display:flex;align-items:center;gap:12px;padding:20px;border-bottom:1px solid var(--app-border-subtle)}
.cc-statistics-header>div{flex:1;min-width:0}.cc-statistics-header h2{font-size:19px;margin:0;line-height:1.5}.cc-statistics-header p{font-size:12px;color:var(--app-text-muted);margin:2px 0 0}
.cc-statistics-logo{display:grid;place-items:center;width:44px;height:44px;flex-shrink:0;border-radius:13px;background:var(--app-info-soft);color:rgb(var(--v-theme-primary))}
.cc-statistics-content{min-height:0;overflow:auto;padding:20px}.cc-statistics-actions{display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid var(--app-border-subtle)}
.cc-statistics-message{padding:40px 12px;text-align:center;color:var(--app-text-muted)}
.cookiecloud-config-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 14px}.cookiecloud-config-hint{grid-column:1/-1;color:var(--app-text-muted);font-size:12px;margin:0}
@media(max-width:600px){.cookiecloud-config-fields{grid-template-columns:1fr}.cc-statistics-header h2{font-size:16px}}
`;

export function install(sdk) {
  const { computed, defineComponent, h, onMounted, ref, resolveComponent } = sdk.vue;
  const { Button, Card, Dialog, Chip, Alert } = sdk.ui.components;
  const icon = (name, size = 22) => h(resolveComponent("VIcon"), { icon: name, size });
  const localTime = (value, fallback) => {
    if (!value) return fallback;
    const text = String(value);
    const date = new Date(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text) ? `${text.replace(" ", "T")}Z` : text);
    return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN", { hour12: false }) : fallback;
  };
  const Statistics = defineComponent({
    name: "CookieCloudStatistics", inheritAttrs: false,
    props: { context: { type: Object, required: true } },
    setup(props) {
      const runs = ref([]), loading = ref(false), error = ref("");
      const groups = computed(() => {
        const groups = [
          { label: "成功", tone: "success", icon: "mdi-check-circle-outline", states: ["completed"] },
          { label: "异常", tone: "error", icon: "mdi-alert-circle-outline", states: ["failed", "partial"] },
          { label: "进行中", tone: "primary", icon: "mdi-refresh", states: ["running", "pending"] },
          { label: "已跳过", tone: "muted", states: ["skipped"] },
          { label: "其他", tone: "muted", states: [] },
        ];
        const known = groups.flatMap(group => group.states);
        return groups.map(group => ({ ...group, count: runs.value.filter(run => {
          const state = run.display_status || run.status;
          return group.states.includes(state) || (group.label === "其他" && !known.includes(state));
        }).length }));
      });
      async function load() {
        if (loading.value) return;
        loading.value = true; error.value = "";
        try { runs.value = (await sdk.request(`/plugins/${ID}/runs?limit=100`)).items || []; }
        catch (reason) { error.value = reason.message || "插件统计加载失败"; }
        finally { loading.value = false; }
      }
      onMounted(load);
      function overview() {
        const installation = props.context.installation || {};
        const visible = groups.value.filter(group => group.count > 0);
        const metrics = [{ label: "运行次数", tone: "neutral", icon: "mdi-cloud-sync-outline", count: runs.value.length }, ...groups.value.slice(0, 3)];
        return h("section", { class: "cookie-overview", "aria-label": "CookieCloud 同步概览" }, [
          h("div", { class: "cookie-overview__heading" }, [h("h3", "运行概览"), h("span", "最近 100 次运行")]),
          h("dl", { class: "cookie-metrics" }, metrics.map(metric => h("div", { class: `cookie-metric cookie-tone--${metric.tone}` }, [h("dt", [h("span", metric.label), icon(metric.icon, 18)]), h("dd", [String(metric.count), h("span", "次")])]))) ,
          h("div", { class: "cookie-results" }, runs.value.length ? [
            h("div", { class: "cookie-results__bar", "aria-hidden": "true" }, visible.map(group => h("span", { class: `cookie-tone--${group.tone}`, style: { flex: group.count } }))),
            h("ul", { class: "cookie-results__legend", "aria-label": "运行结果分布" }, visible.map(group => h("li", { class: `cookie-tone--${group.tone}` }, [h("i", { "aria-hidden": "true" }), group.label, h("strong", String(group.count))]))),
            h("p", "异常包含失败和部分成功"),
          ] : [h("p", { class: "cookie-results__empty" }, "暂无运行数据，首次同步后将在这里显示统计。")]),
          h("div", { class: "cookie-schedule" }, [h("span", { class: "cookie-schedule__icon" }, [icon("mdi-clock-outline")]), h("div", { class: "cookie-schedule__time" }, [h("span", "下次执行"), h("strong", installation.enabled ? localTime(installation.next_run_at, "等待调度") : "已停用")]), h(Chip, { color: installation.enabled ? "primary" : undefined, size: "small", variant: "tonal" }, () => installation.enabled ? "调度已启用" : "调度已停用")]),
        ]);
      }
      return () => h(Dialog, { modelValue: true, maxWidth: 780, width: "calc(100vw - 32px)", "onUpdate:modelValue": open => { if (!open) props.context.close(); } }, () => h(Card, { class: "cc-statistics-dialog" }, () => [
        h("style", STYLE),
        h("header", { class: "cc-statistics-header" }, [h("span", { class: "cc-statistics-logo" }, [icon("mdi-cloud-sync-outline")]), h("div", [h("h2", "CookieCloud 站点同步 · 数据统计"), h("p", "浏览器 Cookie 同步与站点更新概览")]), h(Button, { icon: "mdi-close", variant: "text", "aria-label": "关闭", onClick: props.context.close })]),
        h("div", { class: "cc-statistics-content" }, loading.value ? h("p", { class: "cc-statistics-message", role: "status" }, "正在读取插件统计…") : error.value ? h(Alert, { type: "error", variant: "tonal" }, () => error.value) : overview()),
        h("footer", { class: "cc-statistics-actions" }, [h(Button, { prependIcon: "mdi-refresh", variant: "text", loading: loading.value, onClick: load }, () => "刷新")]),
      ]));
    },
  });
  const ConnectionEditor = defineComponent({
    name: "CookieCloudConnectionEditor", inheritAttrs: false,
    props: { modelValue: { type: Object, required: true }, disabled: Boolean }, emits: ["update:modelValue"],
    setup(props, { emit }) {
      const visible = ref(false), revealed = ref(""), revealError = ref("");
      async function togglePassword() {
        if (visible.value) { visible.value = false; revealed.value = ""; return; }
        revealError.value = "";
        try {
          if (!props.modelValue.password && props.modelValue.password_configured) {
            revealed.value = (await sdk.request(`/plugins/${ID}/config/secret/password`)).value || "";
          }
          visible.value = true;
        } catch { revealError.value = "密码读取失败，请重试"; }
      }
      const update = (key, value) => emit("update:modelValue", { ...props.modelValue, [key]: value });
      return () => h("div", { class: "cookiecloud-config-fields" }, [
        revealError.value ? h("p", { class: "cookiecloud-config-hint", role: "alert" }, revealError.value) : null,
        h("style", STYLE),
        h(resolveComponent("VSwitch"), { modelValue: Boolean(props.modelValue.enabled), disabled: props.disabled, label: "启用站点 Cookie 同步", color: "primary", hideDetails: true, "onUpdate:modelValue": value => update("enabled", value) }),
        h(resolveComponent("VSwitch"), { modelValue: Boolean(props.modelValue.password_clear), disabled: props.disabled, label: "清除已保存的端对端加密密码", color: "error", hideDetails: true, "onUpdate:modelValue": value => emit("update:modelValue", { ...props.modelValue, password: value ? "" : props.modelValue.password, password_clear: Boolean(value) }) }),
        h(resolveComponent("VTextField"), { modelValue: props.modelValue.user_key, disabled: props.disabled, label: "用户 KEY", prependInnerIcon: "mdi-key-outline", autocomplete: "off", hideDetails: true, "onUpdate:modelValue": value => update("user_key", value) }),
        h(resolveComponent("VTextField"), { modelValue: props.modelValue.password_clear ? "" : props.modelValue.password || (visible.value ? revealed.value : ""), label: "端对端加密密码", type: visible.value ? "text" : "password", prependInnerIcon: "mdi-lock-outline", appendInnerIcon: visible.value ? "mdi-eye-off-outline" : "mdi-eye-outline", disabled: props.disabled || Boolean(props.modelValue.password_clear), autocomplete: "off", hideDetails: true, "onClick:appendInner": togglePassword, "onUpdate:modelValue": value => update("password", value) }),
      ]);
    },
  });
  sdk.registerEditor({ domain: "plugin", key: `${ID}:connection`, component: ConnectionEditor });
  sdk.registerContribution({ pluginId: ID, slot: "plugin.statistics", key: "overview", component: Statistics });
}
