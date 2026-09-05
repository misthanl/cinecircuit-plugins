import type { Component, computed, defineComponent, h, onMounted, ref, resolveComponent } from "vue";

export interface PluginInstallation {
  enabled?: boolean;
  next_run_at?: string | null;
  [key: string]: unknown;
}

export interface PluginContributionContext {
  close(): void;
  configure(): void;
  installation?: PluginInstallation;
}

export interface PluginPageRegistration {
  pluginId: string;
  route: string;
  title: string;
  icon: string;
  section: string;
  order?: number;
  component: Component;
}

export interface PluginEditorRegistration {
  domain: string;
  key: string;
  component: Component;
}

export interface PluginContributionRegistration {
  pluginId: string;
  slot: string;
  key: string;
  component: Component;
}

export interface CineCircuitPluginSdk {
  request<T = unknown>(path: string, init?: RequestInit): Promise<T>;
  registerPage(registration: PluginPageRegistration): void;
  registerEditor(registration: PluginEditorRegistration): void;
  registerContribution(registration: PluginContributionRegistration): void;
  vue: {
    computed: typeof computed;
    defineComponent: typeof defineComponent;
    h: typeof h;
    onMounted: typeof onMounted;
    ref: typeof ref;
    resolveComponent: typeof resolveComponent;
  };
  ui: {
    components: Record<string, Component> & {
      Alert: Component;
      Button: Component;
      Card: Component;
      Chip: Component;
      Dialog: Component;
      CronField: Component;
    };
  };
}
