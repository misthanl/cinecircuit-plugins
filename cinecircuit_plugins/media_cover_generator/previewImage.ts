interface ImagePayload {
  image_bytes?: number[];
  image_words?: number[];
  byte_length?: number;
  mime?: string;
  width: number;
  height: number;
}

const invalidImage = () => new Error("图片数据不完整，请重试");
const validInteger = (value: number, maximum: number) => Number.isInteger(value) && value >= 0 && value <= maximum;

function packedBytes(result: ImagePayload): Uint8Array<ArrayBuffer> {
  const words = result.image_words!;
  const length = result.byte_length;
  if (!Number.isInteger(length) || !length || length < 0 || length > 64 * 1024 * 1024
    || words.length !== Math.ceil(length / 4)
    || !words.every(value => validInteger(value, 0xffffffff))) throw invalidImage();
  const packed = new ArrayBuffer(words.length * 4);
  const view = new DataView(packed);
  words.forEach((value, index) => view.setUint32(index * 4, value, true));
  return new Uint8Array(packed, 0, length);
}

function unpackedBytes(result: ImagePayload): Uint8Array<ArrayBuffer> {
  if (!Array.isArray(result.image_bytes) || !result.image_bytes.length || result.image_bytes.length > 5_000_000
    || !result.image_bytes.every(value => validInteger(value, 255))) throw invalidImage();
  return new Uint8Array(result.image_bytes);
}

export function coverImagePayload(payload: unknown) {
  const result = payload as ImagePayload;
  if (!result || !["image/jpeg", "image/webp"].includes(result.mime || "")
    || !Number.isInteger(result.width) || !Number.isInteger(result.height)
    || result.width <= 0 || result.height <= 0) throw invalidImage();
  const bytes = Array.isArray(result.image_words) ? packedBytes(result) : unpackedBytes(result);
  return { bytes, mime: result.mime, width: result.width, height: result.height };
}

type Requester = (path: string, init?: RequestInit) => Promise<unknown>;
interface PreviewTask { status?: string; preview_id?: string }

export async function waitForCoverPreview(request: Requester, config: Record<string, unknown>, disposed: () => boolean) {
  let payload = await request('/plugins/emby-cover-generator/api/preview', {
    method: 'POST', body: JSON.stringify({ config, async: true }),
  }) as PreviewTask;
  const started = Date.now();
  while (payload.status === 'rendering') {
    if (disposed()) return null;
    if (Date.now() - started > 900000) throw new Error('预览等待超时，请稍后重试');
    if (!payload.preview_id || !/^[a-f0-9]{32}$/.test(payload.preview_id)) throw new Error('预览任务返回异常');
    await new Promise(resolve => setTimeout(resolve, 1000));
    if (disposed()) return null;
    payload = await request(`/plugins/emby-cover-generator/api/preview_status?id=${payload.preview_id}`) as PreviewTask;
  }
  return payload;
}
