<script setup lang="ts">
import { computed, ref } from "vue";
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
  const result = payload as {image_bytes?:number[];image_words?:number[];byte_length?:number;mime?:string;width:number;height:number};
  if (!['image/jpeg','image/webp'].includes(result.mime || '')
      || !Number.isInteger(result.width) || !Number.isInteger(result.height) || result.width<=0 || result.height<=0) throw new Error('图片数据不完整，请重试');
  let bytes: Uint8Array<ArrayBuffer>;
  if (Array.isArray(result.image_words)) {
    const length = result.byte_length;
    if (!Number.isInteger(length) || !length || length<0 || length>64*1024*1024 || result.image_words.length!==Math.ceil(length/4)
        || !result.image_words.every(value=>Number.isInteger(value)&&value>=0&&value<=0xffffffff)) throw new Error('图片数据不完整，请重试');
    const packed = new ArrayBuffer(result.image_words.length*4);
    const view = new DataView(packed);
    result.image_words.forEach((value,index)=>view.setUint32(index*4,value,true));
    bytes = new Uint8Array(packed,0,length);
  } else {
    if (!Array.isArray(result.image_bytes) || !result.image_bytes.length || result.image_bytes.length>5_000_000
        || !result.image_bytes.every(value=>Number.isInteger(value)&&value>=0&&value<=255)) throw new Error('图片数据不完整，请重试');
    bytes = new Uint8Array(result.image_bytes);
  }
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
  } catch { if (!disposed) previewError.value='动态样例加载失败，可点击“预览当前设置”重试'; }
}
function disposeImages(): void { disposed=true; for (const image of objectUrls) URL.revokeObjectURL(image); objectUrls.clear(); }
async function renderCurrent(): Promise<void> {
  if (!props.request || rendering.value) return;
  rendering.value=true;
  previewError.value='';
  const requested=signature.value;
  try {
    let payload = await props.request('/plugins/emby-cover-generator/api/preview', {method:'POST',body:JSON.stringify({config:props.modelValue,async:true})}) as {status?:string;preview_id?:string};
    const started = Date.now();
    while (payload.status==='rendering') {
      if (disposed) return;
      if (Date.now()-started>900000) throw new Error('预览等待超时，请稍后重试');
      if (!payload.preview_id || !/^[a-f0-9]{32}$/.test(payload.preview_id)) throw new Error('预览任务返回异常');
      await new Promise(resolve=>setTimeout(resolve,1000));
      if (disposed) return;
      payload = await props.request(`/plugins/emby-cover-generator/api/preview_status?id=${payload.preview_id}`) as typeof payload;
    }
    const result=await decodeImage(payload);
    generated.value={signature:requested,image:result.image,width:result.width,height:result.height};
  } catch(error) { previewError.value=error instanceof Error ? error.message : '生成预览失败，请重试'; }
  finally { rendering.value=false; }
}

let previewRequest = 0;
async function openPreview(sample: Sample): Promise<void> {
  const requestId = ++previewRequest;
  previewError.value = '';
  preview.value = sample;
  actualSize.value = false;
  previewDialog.value?.showModal();
  if (sample.width || sample.value.startsWith('animated') || !props.request) return;
  try {
    const result = await decodeImage(await props.request(`/plugins/emby-cover-generator/api/sample?style=${encodeURIComponent(currentStyle.value)}&variant=${encodeURIComponent(currentVariant.value)}`));
    if (result.width !== 1920 || result.height !== 1080) throw new Error('高清样例返回异常');
    if (requestId === previewRequest && previewDialog.value?.open) preview.value = {...sample,...result};
    else releaseUnusedImages();
  } catch (error) { if (requestId === previewRequest) previewError.value = '高清图加载失败，已保留预览图。' + (error instanceof Error ? error.message : '请重试'); }
}
function closePreview(): void { ++previewRequest; previewDialog.value?.close(); preview.value=null; }
function backdropClick(event: MouseEvent): void {
  if (event.target === previewDialog.value) closePreview();
}

function update(key: string, value: unknown): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
function inputValue(event: Event): string { return (event.target as HTMLInputElement).value; }
function checkedValue(event: Event): boolean { return (event.target as HTMLInputElement).checked; }
</script>

<template>
  <div class="style-editor" @vue:mounted="loadCarouselSample" @vue:updated="releaseUnusedImages" @vue:unmounted="disposeImages">
    <section class="style-selection">
      <div class="style-controls">
        <div class="section-heading"><strong>封面构图</strong><span>选择样式，查看对应效果</span></div>
        <div class="form-grid">
        <div><VSelect label="封面类型" class="cover-mode-select" :model-value="currentMode" :disabled="disabled" @update:model-value="changeMode($event)" :items="[{'value':'static','title':'静态'},{'value':'dynamic','title':'动态'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="样式" class="base-style-select" :model-value="currentStyle" :disabled="disabled" @update:model-value="update('cover_style_base', $event)" :items="availableStyles.map(style => ({value:style.value,title:style.label}))" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="currentStyle === 'animated_diagonal'"><VSelect label="海报移动方向" class="direction-select" :model-value="modelValue.animation_direction || 'up'" :disabled="disabled" @update:model-value="update('animation_direction',$event)" :items="[{'value':'up','title':'向上'},{'value':'down','title':'向下'},{'value':'alternate','title':'交错滚动'}]" variant="outlined" density="comfortable" hide-details /><small>仅右侧海报移动，背景和标题固定</small></div>
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
      <div class="form-grid">
        <div><VSelect label="媒体排序" :model-value="modelValue.sort_by || 'Random'" :disabled="disabled" @update:model-value="update('sort_by', $event)" :items="[{'value':'Random','title':'随机选择'},{'value':'DateCreated','title':'按入库时间'},{'value':'PremiereDate','title':'按首映时间'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="currentMode === 'static'"><VSelect label="输出分辨率" :model-value="modelValue.resolution || '1080p'" :disabled="disabled" @update:model-value="update('resolution', $event)" :items="[{'value':'480p','title':'854 × 480'},{'value':'720p','title':'1280 × 720'},{'value':'1080p','title':'1920 × 1080'},{'value':'custom','title':'自定义'}]" variant="outlined" density="comfortable" hide-details /></div>
        <label v-if="modelValue.resolution === 'custom'"><span>自定义宽度</span><input type="number" min="320" max="7680" :value="modelValue.custom_width || 1920" :disabled="disabled" @input="update('custom_width', Number(inputValue($event)))"></label>
        <label v-if="modelValue.resolution === 'custom'"><span>自定义高度</span><input type="number" min="180" max="4320" :value="modelValue.custom_height || 1080" :disabled="disabled" @input="update('custom_height', Number(inputValue($event)))"></label>
        <div><VSelect label="主标题字体" :model-value="modelValue.zh_font_preset || 'wendao'" :disabled="disabled" @update:model-value="update('zh_font_preset', $event)" :items="zhFonts.map(([value,title]) => ({value,title}))" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="副标题字体" :model-value="modelValue.en_font_preset || 'emblemaone'" :disabled="disabled" @update:model-value="update('en_font_preset', $event)" :items="enFonts.map(([value,title]) => ({value,title}))" variant="outlined" density="comfortable" hide-details /></div>
        <div><VSelect label="文字质感" :model-value="modelValue.text_finish || 'shadow'" :disabled="disabled" @update:model-value="update('text_finish',$event)" :items="[{'value':'clean','title':'海报白字'},{'value':'shadow','title':'柔影立体'},{'value':'silver','title':'银色质感'}]" variant="outlined" density="comfortable" hide-details /></div>
        <div v-if="hasBackground"><VSelect label="留白背景" :model-value="backgroundMode" :disabled="disabled" @update:model-value="update('background_mode',$event)" :items="[{'value':'solid','title':'纯色底'},{'value':'blurred','title':'柔焦取色'},{'value':'gradient','title':'柔和渐变'}]" variant="outlined" density="comfortable" hide-details /></div>
        <label><span>中文字号</span><input type="number" min="20" max="400" :value="modelValue.zh_font_size || 170" :disabled="disabled" @input="update('zh_font_size', Number(inputValue($event)))"></label>
        <label><span>英文字号</span><input type="number" min="12" max="240" :value="modelValue.en_font_size || 75" :disabled="disabled" @input="update('en_font_size', Number(inputValue($event)))"></label>
        <label><span>每张封面最多使用图片</span><input type="number" min="1" max="12" :value="modelValue.source_limit ?? 8" :disabled="disabled" @input="update('source_limit', Number(inputValue($event)))"></label>
        <label v-if="hasBackground && backgroundMode === 'blurred'"><span>背景模糊强度</span><input type="number" min="0" max="80" :value="modelValue.blur_radius ?? 32" :disabled="disabled" @input="update('blur_radius', Number(inputValue($event)))"></label>
        <label v-if="hasBackground && backgroundMode === 'blurred'"><span>底色占比（%）</span><input type="number" min="0" max="100" :value="modelValue.background_mix ?? 80" :disabled="disabled" @input="update('background_mix',Number(inputValue($event)))"></label>
        <label v-if="hasBackground && backgroundMode !== 'solid'"><span>横向提亮（%）</span><input type="number" min="0" max="100" :value="modelValue.background_light ?? 35" :disabled="disabled" @input="update('background_light',Number(inputValue($event)))"></label>
        <label v-if="hasBackground"><span>磨砂颗粒（0–10）</span><input type="number" min="0" max="10" :value="modelValue.background_grain ?? 3" :disabled="disabled" @input="update('background_grain',Number(inputValue($event)))"></label>
        <label><span>JPEG 质量（75–96）</span><input type="number" min="75" max="96" :value="modelValue.jpeg_quality ?? 92" :disabled="disabled" @input="update('jpeg_quality', Number(inputValue($event)))"></label>
        <label class="deferred-label" :class="{ 'label-active': focusedField === 'background_color' || Boolean(modelValue.background_color) }"><span>背景底色／装饰色</span><input type="text" :value="modelValue.background_color || ''" :placeholder="focusedField === 'background_color' ? '留空自动取色，如 #101828' : ''" :disabled="disabled" @focus="focusedField = 'background_color'" @blur="focusedField = ''" @input="update('background_color', inputValue($event))"></label>
        <label class="full deferred-label" :class="{ 'label-active': focusedField === 'title_config' || Boolean(modelValue.title_config) }"><span>媒体库标题配置 <small>可选，每行一个</small></span><textarea :value="String(modelValue.title_config || '')" :disabled="disabled" :placeholder="focusedField === 'title_config' ? '电影=电影|MOVIES\n剧集=剧集|TV SERIES' : ''" @focus="focusedField = 'title_config'" @blur="focusedField = ''" @input="update('title_config', inputValue($event))" /></label>
        <div class="switches full"><label><input type="checkbox" :checked="Boolean(modelValue.use_primary ?? true)" :disabled="disabled" @change="update('use_primary', checkedValue($event))"><span><b>优先使用海报图</b><small>横版剧照不足时更实用</small></span></label><label><input type="checkbox" :checked="Boolean(modelValue.show_item_count)" :disabled="disabled" @change="update('show_item_count', checkedValue($event))"><span><b>显示媒体数量角标</b><small>在左上角显示条目总数</small></span></label></div>
      </div>
    </section>
    <dialog ref="previewDialog" class="cover-preview-dialog" aria-label="封面高清预览" @click="backdropClick" @close="preview = null">
      <div v-if="preview" class="cover-preview-shell">
        <header class="cover-preview-header">
          <div><strong>{{ preview.label }}</strong><span>{{ sampleWidth(preview) }} × {{ sampleHeight(preview) }} · {{ 'signature' in preview ? '当前设置预览' : '插件生成样例' }}</span></div>
          <button type="button" class="preview-scale" :aria-pressed="actualSize" @click="actualSize = !actualSize">{{ actualSize ? '适应屏幕' : '原始尺寸' }}</button>
          <button type="button" class="preview-close" aria-label="关闭大图" autofocus @click="closePreview">✕</button>
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
.section-heading strong { font-size: 16px; }
.section-heading span { color: var(--app-text-secondary, #657087); font-size: 13px; line-height: 1.6; }
.style-selection { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 420px); gap: 28px; align-items: start; }
.style-controls .form-grid { grid-template-columns: 1fr; }
.style-controls .section-heading, .selected-preview .section-heading { flex-direction: column; align-items: flex-start; gap: 4px; margin-bottom: 12px; }
.selected-preview { width: 100%; min-width: 0; margin: 0; }
.sample { position: relative; display: block; width: 100%; padding: 0; overflow: hidden; border: 0; border-radius: 12px; background: #131923; cursor: zoom-in; }
.sample img { display: block; width: 100%; height: auto; aspect-ratio: 16/9; object-fit: contain; }
.sample-resolution, .sample-enlarge { position: absolute; right: 12px; padding: 5px 8px; border-radius: 6px; background: rgba(5, 9, 16, .78); color: #fff; font-size: 12px; line-height: 1.3; }
.sample-resolution { top: 12px; }
.sample-enlarge { bottom: 12px; }
.preview-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:10px; }
.preview-actions button { padding:8px 12px; border:1px solid var(--app-border,#d5dce8); border-radius:8px; background:var(--app-surface,#fff); color:inherit; font:inherit; font-size:13px; cursor:pointer; }
.preview-actions small,.form-grid label > small { color:var(--app-text-secondary,#657087); font-size:12px; }
.preview-error { color:#c23934; font-size:13px; }
button:focus-visible { outline: 3px solid #5575e7; outline-offset: -3px; }
button:disabled { opacity: .55; cursor: not-allowed; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 20px; }
.form-grid label { display: grid; gap: 8px; }
.form-grid > label { position: relative; min-width: 0; padding-top: 8px; align-content: start; }
.form-grid > label > span { position: absolute; top: 0; left: 12px; z-index: 1; max-width: calc(100% - 32px); padding: 0 4px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; background: var(--control-surface, var(--app-surface, #fff)); color: var(--app-control-muted, #8894a8); font-size: 12px; font-weight: 400; line-height: 16px; pointer-events: none; }
.form-grid > label.deferred-label > span { transition: top .15s ease, left .15s ease, padding .15s ease, font-size .15s ease, background-color .15s ease; }
.form-grid > label.deferred-label:not(.label-active) > span { top: 26px; left: 16px; padding: 0; background: transparent; font-size: 13px; }
.form-grid > label:focus-within > span { color: var(--app-control-border-focus, #5575e7); }
.form-grid > label:has(:disabled) { opacity: .55; }
.form-grid label > span small { font-weight: 400; }
.form-grid select, .form-grid input[type=number], .form-grid input[type=text], .form-grid textarea { box-sizing: border-box; width: 100%; min-width: 0; height: var(--app-active-control-height, 52px); min-height: var(--app-active-control-height, 52px); margin: 0; padding: 12px 16px; border: 1px solid var(--app-control-border, #d5dce8); border-radius: var(--app-control-radius, 11px); background: var(--control-surface, var(--app-surface, #fff)); color: var(--app-control-text, inherit); font: inherit; font-size: 13px; line-height: 1.35; }
.form-grid > label > :is(select,input,textarea):hover:not(:disabled) { border-color: var(--app-control-border-hover, #9ba9bd); }
.form-grid > label > :is(select,input,textarea):focus { outline: none; border-color: var(--app-control-border-focus, #5575e7); box-shadow: inset 0 0 0 1px var(--app-control-border-focus, #5575e7), 0 0 0 2px var(--app-control-focus-ring, transparent); }
.form-grid > label > small { padding-inline: 16px; line-height: 1.5; }
.form-grid select { appearance: auto; cursor: pointer; }
.form-grid textarea { height: auto; min-height: 112px; resize: vertical; }
.full { grid-column: 1/-1; }
.switches { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.switches label { display: flex; align-items: center; gap: 10px; padding: 14px; border-radius: 10px; background: var(--app-surface-muted, #f5f7fa); cursor: pointer; }
.switches input { accent-color: #5575e7; }
.switches span { display: grid; gap: 4px; }
.switches b { font-size: 14px; }
.switches small { color: var(--app-text-secondary, #657087); font-size: 12px; }
.cover-preview-dialog { position: fixed; inset: 0; width: min(1960px, calc(100vw - 32px)); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: 0; overflow: hidden; border: 1px solid #394354; border-radius: 14px; background: #10151d; color: #f4f6fc; box-shadow: 0 16px 80px #0009; }
.cover-preview-dialog::backdrop { background: rgba(3, 7, 14, .86); }
.cover-preview-shell { display: flex; flex-direction: column; max-height: calc(100dvh - 34px); }
.cover-preview-header { display: flex; align-items: center; gap: 16px; flex: 0 0 auto; padding: 14px 18px; border-bottom: 1px solid #394354; }
.cover-preview-header > div { display: grid; flex: 1; gap: 4px; }
.cover-preview-header strong { font-size: 16px; }
.cover-preview-header span { color: #bbc5d6; font-size: 12px; }
.cover-preview-header button { min-height: 44px; padding: 8px 12px; border: 1px solid #526178; border-radius: 8px; background: #202b3a; color: inherit; font: inherit; cursor: pointer; }
.preview-close { width: 44px; flex: 0 0 auto; }
.cover-preview-image { display: flex; justify-content: center; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.cover-preview-image img { display: block; width: 100%; height: auto; max-height: calc(100dvh - 116px); object-fit: contain; }
.cover-preview-image.actual-size { display: block; }
.cover-preview-image.actual-size img { width: auto; max-width: none; max-height: none; }
@media (max-width: 680px) {
  .style-selection { grid-template-columns: 1fr; gap: 20px; }
  .selected-preview { max-width: 320px; margin-inline: auto; }
  .form-grid, .switches { grid-template-columns: 1fr; }
  .full { grid-column: auto; }
  .section-heading { align-items: flex-start; flex-direction: column; }
  .cover-preview-dialog { width: 100vw; max-height: 100dvh; border-radius: 0; }
  .cover-preview-shell { max-height: 100dvh; }
  .cover-preview-header { gap: 8px; padding: 10px; }
  .cover-preview-header span { font-size: 11px; }
}
</style>
