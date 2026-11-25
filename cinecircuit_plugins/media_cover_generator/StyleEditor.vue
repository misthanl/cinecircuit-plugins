<script setup lang="ts">
import "../_shared/setting-switch.css";
import { pluginErrorText, pluginErrorFallback, requestErrorNotified } from "../_shared/request-feedback";
import { computed, ref } from "vue";
import { coverImagePayload, waitForCoverPreview } from "./previewImage";
import sampleMulti from "./assets/thumb-sample-multi.jpg?inline";
import samplePoster from "./assets/thumb-sample-poster.jpg?inline";
import sampleSingle from "./assets/thumb-sample-single.jpg?inline";
import variantFocus from "./assets/thumb-variant-focus.jpg?inline";
import variantGrid from "./assets/thumb-variant-grid.jpg?inline";
import variantSplit from "./assets/thumb-variant-split.jpg?inline";
import variantTriptych from "./assets/thumb-variant-triptych.jpg?inline";
import sampleDiagonal from "./assets/thumb-sample-diagonal.jpg?inline";
import sampleDuo from "./assets/thumb-sample-duo.jpg?inline";
import sampleStack from "./assets/thumb-sample-stack.jpg?inline";
import sampleEditorial from "./assets/thumb-sample-editorial.jpg?inline";
import samplePanorama from "./assets/thumb-sample-panorama.jpg?inline";
import sampleCinema from "./assets/thumb-sample-cinema.jpg?inline";
import sampleEcho from "./assets/thumb-sample-echo.jpg?inline";
import sampleWedge from "./assets/thumb-sample-wedge.jpg?inline";

// The host's generic field grid must not split our sections into columns.
defineOptions({ inheritAttrs: false });

type Model = Record<string, unknown>;
const props = defineProps<{ modelValue: Model; disabled?: boolean; request?: (path: string, init?: RequestInit) => Promise<unknown> }>();
const emit = defineEmits<{ "update:modelValue": [value: Model] }>();
const focusedField = ref("");

const styles = [
  { value: "single", label: "焦点单图", note: "背景虚化，右侧突出主海报", image: sampleSingle },
  { value: "multi", label: "多图拼贴", note: "多张剧照组合，适合综合媒体库", image: sampleMulti },
  { value: "poster", label: "海报长廊", note: "竖版海报横向陈列，收藏感更强", image: samplePoster },
  { value: "animated", label: "动态轮播", note: "真实动态样例，图片会渐变切换", image: samplePoster },
  { value: "animated_diagonal", label: "动态斜向海报墙", note: "右侧海报循环移动，标题和背景保持固定", image: sampleDiagonal },
  { value: "animated_wedge", label: "动态斜切轮播", note: "标题固定，大图淡入淡出，背景随图片色调变化", image: sampleWedge },
  { value: "diagonal", label: "斜向画廊", note: "左侧留白，右侧倾斜圆角海报墙", image: sampleDiagonal },
  { value: "echo", label: "扇形叠影", note: "清晰主图搭配渐隐虚化叠影", image: sampleEcho },
  { value: "wedge", label: "斜切大图", note: "磨砂留白与整幅画面斜向分隔", image: sampleWedge },
  { value: "duo", label: "留白双海报", note: "独立标题区，双海报错位陈列", image: sampleDuo },
  { value: "stack", label: "扇形叠卡", note: "三张海报旋转层叠，保留原色", image: sampleStack },
  { value: "editorial", label: "杂志拼版", note: "窄标题栏、主海报与双图侧栏", image: sampleEditorial },
  { value: "panorama", label: "胶片横窗", note: "三幅横图，下方独立标题区", image: samplePanorama },
  { value: "cinema", label: "极简巨幕", note: "全幅画面与居中标题，适合横版剧照", image: sampleCinema },
] as const;
const variants = [
  { value: "1", label: "八宫格", note: "八张剧照均匀排列", image: variantGrid },
  { value: "2", label: "主次拼贴", note: "一张主图搭配四张副图", image: variantFocus },
  { value: "3", label: "左右分镜", note: "两张主图左右并排", image: variantSplit },
  { value: "4", label: "三联画", note: "三张竖向画面连续排列", image: variantTriptych },
] as const;
const zhFonts = [["wendao", "文道潮黑"], ["cuyasong", "粗雅宋"], ["modern", "现代黑体"], ["bold", "电影粗黑"], ["serif", "典雅宋体"]] as const;
const enFonts = [["emblemaone", "EmblemaOne"], ["melete", "Melete"], ["phosphate", "Phosphate"], ["josefinsans", "JosefinSans"], ["lilitaone", "LilitaOne"], ["monoton", "Monoton"], ["plaster", "Plaster"], ["inter", "Inter 简洁"], ["cinema", "Cinema 宽体"], ["editorial", "Editorial 衬线"]] as const;
const currentStyle = computed(() => String(props.modelValue.cover_style_base || "multi"));
const hasBackground = computed(() => !['multi','cinema'].includes(currentStyle.value));
const backgroundMode = computed(() => String(props.modelValue.background_mode || 'blurred'));
const isAnimated = (style: string) => ['animated', 'animated_diagonal', 'animated_wedge'].includes(style);
const currentMode = computed(() => isAnimated(currentStyle.value) ? 'dynamic' : 'static');
const availableStyles = computed(() => styles.filter(style => isAnimated(style.value) === (currentMode.value === 'dynamic')));
const rememberedStyles = ref({
  static: isAnimated(currentStyle.value) ? (currentStyle.value === 'animated_wedge' ? 'wedge' : currentStyle.value === 'animated_diagonal' ? 'diagonal' : 'poster') : currentStyle.value,
  dynamic: isAnimated(currentStyle.value) ? currentStyle.value : (currentStyle.value === 'wedge' ? 'animated_wedge' : currentStyle.value === 'diagonal' ? 'animated_diagonal' : 'animated'),
});
function changeMode(mode: string): void {
  if (props.disabled || (mode !== 'static' && mode !== 'dynamic') || mode === currentMode.value) return;
  rememberedStyles.value[currentMode.value] = currentStyle.value;
  update('cover_style_base', rememberedStyles.value[mode]);
}
const currentVariant = computed(() => String(props.modelValue.cover_style_variant || "1"));
type Sample = { value: string; label: string; note: string; image: string; width?:number; height?:number };
const preview = ref<Sample | null>(null);
const previewDialog = ref<HTMLDialogElement | null>(null);
const actualSize = ref(false);
const animationSamples = ref<Record<string,{image:string}>>({});
const animationRequested = new Set<string>();
const selectedSample = computed<Sample>(() => currentStyle.value === 'multi'
  ? variants.find(sample => sample.value === currentVariant.value) || variants[0]
  : animationSamples.value[currentStyle.value]
    ? {...styles.find(sample => sample.value === currentStyle.value)!,...animationSamples.value[currentStyle.value]}
    : styles.find(sample => sample.value === currentStyle.value) || variants[0]);
const rendering = ref(false);
const previewError = ref('');
const generated = ref<{ signature:string; image:string; width:number; height:number } | null>(null);
const signature = computed(() => JSON.stringify(props.modelValue));
const activeSample = computed<Sample>(() => generated.value?.signature === signature.value
  ? {...selectedSample.value,...generated.value} : selectedSample.value);
const sampleWidth = (sample: Sample) => sample.width || (isAnimated(sample.value) ? 1280 : 960);
const sampleHeight = (sample: Sample) => sample.height || (isAnimated(sample.value) ? 720 : 540);
async function decodeImage(payload: unknown): Promise<{image:string;width:number;height:number}> {
  const { bytes, ...result } = coverImagePayload(payload);
  const image = URL.createObjectURL(new Blob([bytes],{type:result.mime}));
  const probe = new Image();
  probe.src = image;
  try {
    await probe.decode();
    if (disposed || probe.naturalWidth!==result.width || probe.naturalHeight!==result.height) throw new Error('图片尺寸校验失败');
  } catch (error) { URL.revokeObjectURL(image); throw error; }
  objectUrls.add(image);
  return {image,width:result.width,height:result.height};
}
const objectUrls = new Set<string>();
let disposed = false;
function releaseUnusedImages(): void {
  for (const image of objectUrls) if (image!==generated.value?.image && image!==preview.value?.image && !Object.values(animationSamples.value).some(sample=>sample.image===image)) {
    URL.revokeObjectURL(image); objectUrls.delete(image);
  }
  void loadCarouselSample();
}
async function loadCarouselSample(): Promise<void> {
  const style=currentStyle.value;
  if (disposed || animationRequested.has(style) || !isAnimated(style) || !props.request) return;
  animationRequested.add(style);
  try {
    const result=await decodeImage(await props.request(`/plugins/emby-cover-generator/api/sample?style=${style}&variant=1`));
    animationSamples.value={...animationSamples.value,[style]:{image:result.image}};
    if(preview.value?.value===style && !preview.value.width) preview.value={...preview.value,image:result.image};
  } catch (cause) { if (!disposed) previewError.value=pluginErrorFallback(cause, '动态样例加载失败，可点击“预览当前设置”重试'); }
}
function disposeImages(): void { disposed=true; for (const image of objectUrls) URL.revokeObjectURL(image); objectUrls.clear(); }
async function renderCurrent(): Promise<void> {
  if (!props.request || rendering.value) return;
  rendering.value=true;
  previewError.value='';
  const requested=signature.value;
  try {
    const payload = await waitForCoverPreview(props.request, props.modelValue, () => disposed);
    if (payload === null) return;
    const result=await decodeImage(payload);
    generated.value={signature:requested,image:result.image,width:result.width,height:result.height};
  } catch(error) { previewError.value=pluginErrorText(error, '生成预览失败，请重试'); }
  finally { rendering.value=false; }
}

function needsHighResolution(sample: Sample): boolean {
  return !sample.width && !sample.value.startsWith('animated') && Boolean(props.request);
}
let previewRequest = 0;
async function openPreview(sample: Sample): Promise<void> {
  const requestId = ++previewRequest;
  previewError.value = '';
  preview.value = sample;
  actualSize.value = false;
  previewDialog.value?.showModal();
  if (!needsHighResolution(sample)) return;
  try {
    const result = await decodeImage(await props.request!(`/plugins/emby-cover-generator/api/sample?style=${encodeURIComponent(currentStyle.value)}&variant=${encodeURIComponent(currentVariant.value)}`));
    if (result.width !== 1920 || result.height !== 1080) throw new Error('高清样例返回异常');
    if (requestId === previewRequest && previewDialog.value?.open) preview.value = {...sample,...result};
    else releaseUnusedImages();
  } catch (error) { if (requestId === previewRequest) previewError.value = previewFailureMessage(error); }
}
function previewFailureMessage(error: unknown) {
  if (requestErrorNotified(error)) return "";
  return '高清图加载失败，已保留预览图。' + (pluginErrorText(error, '请重试'));
}
function closePreview(): void { ++previewRequest; previewDialog.value?.close(); preview.value=null; }
function backdropClick(event: MouseEvent): void {
  if (event.target === previewDialog.value) closePreview();
}

function update(key: string, value: unknown): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
</script>

<template>
  <div class="style-editor" @vue:mounted="loadCarouselSample" @vue:updated="releaseUnusedImages" @vue:unmounted="disposeImages">
    <section class="style-selection">
      <div class="style-controls">
        <div class="section-heading"><strong>封面构图</strong><span>选择样式，查看对应效果</span></div>
        <div class="form-grid plugin-config-grid app-form-layout">
        <div><VSelect label="封面类型" class="cover-mode-select" :model-value="currentMode" :disabled="disabled" @update:model-value="changeMode($event)" :items="[{'value':'static','title':'静态'},{'value':'dynamic','title':'动态'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="样式" class="base-style-select" :model-value="currentStyle" :disabled="disabled" @update:model-value="update('cover_style_base', $event)" :items="availableStyles.map(style => ({value:style.value,title:style.label}))" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="currentStyle === 'animated_diagonal'"><VSelect label="海报移动方向" class="direction-select" :model-value="modelValue.animation_direction || 'up'" :disabled="disabled" @update:model-value="update('animation_direction',$event)" :items="[{'value':'up','title':'向上'},{'value':'down','title':'向下'},{'value':'alternate','title':'交错滚动'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="currentStyle === 'multi'" class="variant-section"><VSelect label="多图布局" class="variant-select" :model-value="currentVariant" :disabled="disabled" @update:model-value="update('cover_style_variant', $event)" :items="variants.map(variant => ({value:variant.value,title:variant.label}))" variant="outlined" density="comfortable" hide-details /></div>
        </div>
      </div>
      <figure class="selected-preview">
        <figcaption class="section-heading" aria-live="polite"><strong>{{ selectedSample.label }} · 效果预览</strong><span>{{ selectedSample.note }}</span></figcaption>
        <button type="button" class="sample" :aria-label="`放大查看${activeSample.label}`" @click="openPreview(activeSample)">
          <img :src="activeSample.image" :alt="`${activeSample.label}成品封面样例`" :width="sampleWidth(activeSample)" :height="sampleHeight(activeSample)">
          <span class="sample-resolution">{{ activeSample.width ? '当前设置' : '构图样例' }}</span>
          <span class="sample-enlarge">查看大图 ↗</span>
        </button>
        <div class="preview-actions"><button type="button" :disabled="disabled || rendering || !request" @click="renderCurrent">{{ rendering ? '正在生成…' : '预览当前设置' }}</button><small>使用样例图片，不保存、不上传</small></div>
        <p v-if="previewError" class="preview-error" role="alert">{{ previewError }}</p>
      </figure>
    </section>

    <section class="settings-section">
      <div class="section-heading"><strong>画面与标题</strong></div>
      <div class="form-grid plugin-config-grid app-form-layout">
        <div><VSelect label="媒体排序" :model-value="modelValue.sort_by || 'Random'" :disabled="disabled" @update:model-value="update('sort_by', $event)" :items="[{'value':'Random','title':'随机选择'},{'value':'DateCreated','title':'按入库时间'},{'value':'PremiereDate','title':'按首映时间'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="currentMode === 'static'"><VSelect label="输出分辨率" :model-value="modelValue.resolution || '1080p'" :disabled="disabled" @update:model-value="update('resolution', $event)" :items="[{'value':'480p','title':'854 × 480'},{'value':'720p','title':'1280 × 720'},{'value':'1080p','title':'1920 × 1080'},{'value':'custom','title':'自定义'}]" variant="outlined" density="comfortable" hide-details /></div>
        <VTextField v-if="currentMode === 'static' && modelValue.resolution === 'custom'" label="自定义宽度" type="number" min="320" max="7680" :model-value="modelValue.custom_width || 1920" :disabled="disabled" @update:model-value="update('custom_width', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField v-if="currentMode === 'static' && modelValue.resolution === 'custom'" label="自定义高度" type="number" min="180" max="4320" :model-value="modelValue.custom_height || 1080" :disabled="disabled" @update:model-value="update('custom_height', Number($event))" variant="outlined" density="comfortable" hide-details />
        <div><VSelect label="主标题字体" :model-value="modelValue.zh_font_preset || 'wendao'" :disabled="disabled" @update:model-value="update('zh_font_preset', $event)" :items="zhFonts.map(([value,title]) => ({value,title}))" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="副标题字体" :model-value="modelValue.en_font_preset || 'emblemaone'" :disabled="disabled" @update:model-value="update('en_font_preset', $event)" :items="enFonts.map(([value,title]) => ({value,title}))" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="文字质感" :model-value="modelValue.text_finish || 'shadow'" :disabled="disabled" @update:model-value="update('text_finish',$event)" :items="[{'value':'clean','title':'海报白字'},{'value':'shadow','title':'柔影立体'},{'value':'silver','title':'银色质感'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="hasBackground"><VSelect label="留白背景" :model-value="backgroundMode" :disabled="disabled" @update:model-value="update('background_mode',$event)" :items="[{'value':'solid','title':'纯色底'},{'value':'blurred','title':'柔焦取色'},{'value':'gradient','title':'柔和渐变'}]" variant="outlined" density="comfortable" hide-details /></div>
        <VTextField label="中文字号" type="number" min="20" max="400" :model-value="modelValue.zh_font_size || 170" :disabled="disabled" @update:model-value="update('zh_font_size', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField label="英文字号" type="number" min="12" max="240" :model-value="modelValue.en_font_size || 75" :disabled="disabled" @update:model-value="update('en_font_size', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField label="每张封面最多使用图片" type="number" min="1" max="12" :model-value="modelValue.source_limit ?? 8" :disabled="disabled" @update:model-value="update('source_limit', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField v-if="hasBackground && backgroundMode === 'blurred'" label="背景模糊强度" type="number" min="0" max="80" :model-value="modelValue.blur_radius ?? 32" :disabled="disabled" @update:model-value="update('blur_radius', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField v-if="hasBackground && backgroundMode === 'blurred'" label="底色占比（%）" type="number" min="0" max="100" :model-value="modelValue.background_mix ?? 80" :disabled="disabled" @update:model-value="update('background_mix',Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField v-if="hasBackground && backgroundMode !== 'solid'" label="横向提亮（%）" type="number" min="0" max="100" :model-value="modelValue.background_light ?? 35" :disabled="disabled" @update:model-value="update('background_light',Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField v-if="hasBackground" label="磨砂颗粒（0–10）" type="number" min="0" max="10" :model-value="modelValue.background_grain ?? 3" :disabled="disabled" @update:model-value="update('background_grain',Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField label="JPEG 质量（75–96）" type="number" min="75" max="96" :model-value="modelValue.jpeg_quality ?? 92" :disabled="disabled" @update:model-value="update('jpeg_quality', Number($event))" variant="outlined" density="comfortable" hide-details />
        <VTextField label="背景底色／装饰色" :model-value="modelValue.background_color || ''" :placeholder="focusedField === 'background_color' ? '留空自动取色，如 #101828' : ''" :disabled="disabled" @update:focused="focusedField = $event ? 'background_color' : ''" @update:model-value="update('background_color', $event)" variant="outlined" density="comfortable" hide-details />
        <VSwitch class="plugin-setting-switch" color="primary" hide-details inset label="优先使用海报图" :model-value="Boolean(modelValue.use_primary ?? true)" :disabled="disabled" @update:model-value="update('use_primary', Boolean($event))" />
          <VSwitch class="plugin-setting-switch" color="primary" hide-details inset label="显示媒体库标题" :model-value="Boolean(modelValue.show_library_title ?? true)" :disabled="disabled" @update:model-value="update('show_library_title', Boolean($event))" />
          <VSwitch class="plugin-setting-switch" color="primary" hide-details inset label="显示媒体数量角标" :model-value="Boolean(modelValue.show_item_count)" :disabled="disabled" @update:model-value="update('show_item_count', Boolean($event))" />
        <VTextarea class="full title-config-field" no-resize label="媒体库标题配置（可选，每行一个）" :model-value="String(modelValue.title_config || '')" :disabled="disabled" :placeholder="focusedField === 'title_config' ? '电影=电影|MOVIES\n剧集=剧集|TV SERIES' : ''" @update:focused="focusedField = $event ? 'title_config' : ''" @update:model-value="update('title_config', $event)" variant="outlined" density="comfortable" rows="4" hide-details />

      </div>
    </section>
    <dialog ref="previewDialog" class="cover-preview-dialog" aria-label="封面高清预览" @click="backdropClick" @close="preview = null">
      <div v-if="preview" class="cover-preview-shell">
        <header class="cover-preview-header">
          <div><strong>{{ preview.label }}</strong><span>{{ sampleWidth(preview) }} × {{ sampleHeight(preview) }} · {{ 'signature' in preview ? '当前设置预览' : '插件生成样例' }}</span></div>
          <button type="button" class="preview-scale" :aria-pressed="actualSize" @click="actualSize = !actualSize">{{ actualSize ? '适应屏幕' : '原始尺寸' }}</button>
          <button type="button" class="app-dialog-close preview-close" aria-label="关闭大图" autofocus @click="closePreview">✕</button>
        </header>
        <p v-if="previewError" role="alert">{{ previewError }}</p>
        <div class="cover-preview-image" :class="{ 'actual-size': actualSize }"><img :src="preview.image" :alt="`${preview.label}高清成品封面`"></div>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
.style-editor { display: flex; flex-direction: column; width: 100%; min-width: 0; gap: 20px; color: var(--app-text, #1a2336); }
.style-editor > section { width: 100%; min-width: 0; }
.style-editor > section + section { padding-top: 20px; border-top: 1px solid var(--app-border-subtle, #e2e6ee); }
.section-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 20px; margin-bottom: 16px; }
.section-heading strong { font-size: 12px; font-weight: 500; }
.section-heading span { color: var(--app-text-secondary, #657087); font-size: 13px; line-height: 1.6; }
.style-selection { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 420px); gap: 28px; align-items: start; }
.style-controls .form-grid { --app-plugin-config-columns: 1; }
.style-controls .section-heading, .selected-preview .section-heading { flex-direction: column; align-items: flex-start; gap: 4px; margin-bottom: 12px; }
.selected-preview { width: 100%; min-width: 0; margin: 0; }
.sample { position: relative; display: block; width: 100%; padding: 0; overflow: hidden; border: 0; border-radius: 12px; background: #131923; cursor: zoom-in; }
.sample img { display: block; width: 100%; height: auto; aspect-ratio: 16/9; object-fit: contain; }
.sample-resolution, .sample-enlarge { position: absolute; right: 12px; padding: 5px 8px; border-radius: 6px; background: rgba(5, 9, 16, .78); color: #fff; font-size: 12px; line-height: 1.3; }
.sample-resolution { top: 12px; }
.sample-enlarge { bottom: 12px; }
.preview-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:10px; }
.preview-actions button { padding:8px 12px; border:1px solid var(--app-border,#d5dce8); border-radius:var(--app-radius-action, 8px); background:var(--app-surface,#fff); color:inherit; font:inherit; font-size:13px; cursor:pointer; }
.preview-actions small { color:var(--app-text-secondary,#657087); font-size:12px; }
.preview-error { color:#c23934; font-size:10px; }
button:focus-visible { outline: 3px solid #5575e7; outline-offset: -3px; }
button:disabled { opacity: .55; cursor: not-allowed; }
.form-grid { display: grid; row-gap: var(--app-plugin-config-row-gap, 14px); column-gap: var(--app-plugin-config-column-gap, 16px); }
.full { grid-column: 1/-1; }
/* Keep the native scrollbar inside the outline, clear of its rounded corners. */
.title-config-field :deep(.v-field__field) { padding-block: 10px; padding-inline-end: 10px; }
.title-config-field :deep(textarea.v-field__input) { height: auto; padding-block: 0 !important; mask-image: none; -webkit-mask-image: none; }
/* Host plugin grids reset switch padding; keep the standard row's inner gutter. */
.form-grid :deep(.plugin-setting-switch.v-input) { padding-inline: 14px !important; }
.form-grid :deep(.plugin-setting-switch .v-label) { color: var(--app-text) !important; }
.cover-preview-dialog { position: fixed; inset: 0; width: min(1960px, calc(100vw - 32px)); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: 0; overflow: hidden; border: 1px solid #394354; border-radius: var(--app-dialog-radius, 16px); background: #10151d; color: #f4f6fc; box-shadow: 0 16px 80px #0009; }
.cover-preview-dialog::backdrop { background: rgba(3, 7, 14, .86); }
.cover-preview-shell { display: flex; flex-direction: column; max-height: calc(100dvh - 34px); }
.cover-preview-header { display: flex; align-items: center; gap: 16px; flex: 0 0 auto; padding: 14px 18px; border-bottom: 1px solid #394354; }
.cover-preview-header > div { display: grid; flex: 1; gap: 4px; }
.cover-preview-header strong { font-size: 12px; font-weight: 500; }
.cover-preview-header span { color: #bbc5d6; font-size: 12px; }
.cover-preview-header button { min-height: 44px; padding: 8px 12px; border: 1px solid #526178; border-radius: var(--app-radius-action, 8px); background: #202b3a; color: inherit; font: inherit; cursor: pointer; }
.preview-close { width: 44px; flex: 0 0 auto; }
.cover-preview-image { display: flex; justify-content: center; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.cover-preview-image img { display: block; width: 100%; height: auto; max-height: calc(100dvh - 116px); object-fit: contain; }
.cover-preview-image.actual-size { display: block; }
.cover-preview-image.actual-size img { width: auto; max-width: none; max-height: none; }
@media (max-width: 760px) {
  .style-selection { grid-template-columns: 1fr; gap: 20px; }
  .selected-preview { max-width: 320px; margin-inline: auto; }
  .full { grid-column: auto; }
  .section-heading { align-items: flex-start; flex-direction: column; }
  .cover-preview-dialog { width: 100vw; max-height: 100dvh; border-radius: 0; }
  .cover-preview-shell { max-height: 100dvh; }
  .cover-preview-header { gap: 8px; padding: 10px; }
  .cover-preview-header span { font-size: 11px; }
}
</style>
