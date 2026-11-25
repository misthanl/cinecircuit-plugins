type Chunk = { image_words: number[]; byte_length: number; mime: string; offset?: number; total_bytes?: number };
type Requester = (path: string, init?: RequestInit) => Promise<unknown>;
const invalid = () => new Error("历史封面数据不完整，请刷新后重试");

function unpack(data: Chunk) {
  if (!Number.isSafeInteger(data.byte_length) || data.byte_length < 0 || data.byte_length > 20 * 1024 * 1024
    || !Array.isArray(data.image_words) || data.image_words.length !== Math.ceil(data.byte_length / 4)
    || !data.image_words.every(value => Number.isInteger(value) && value >= 0 && value <= 0xffffffff)) throw invalid();
  const buffer = new ArrayBuffer(data.image_words.length * 4), view = new DataView(buffer);
  data.image_words.forEach((value, index) => view.setUint32(index * 4, value, true));
  return new Uint8Array(buffer, 0, data.byte_length);
}

function validateChunk(chunk: Chunk, bytes: Uint8Array, offset: number, total: number | undefined, mime: string) {
  const size = chunk.total_bytes ?? 0;
  if (!Number.isSafeInteger(size) || size <= 0 || size > 20 * 1024 * 1024
    || chunk.offset !== offset || !bytes.length || bytes.length > 1024 * 1024) throw invalid();
  validateIdentity(chunk, total, mime);
  return size;
}

function validateIdentity(chunk: Chunk, total: number | undefined, mime: string) {
  if (total !== undefined && (total !== chunk.total_bytes || mime !== chunk.mime)) throw invalid();
}

export async function readHistoryImage(request: Requester, path: string, disposed: () => boolean): Promise<Blob> {
  const parts: Uint8Array<ArrayBuffer>[] = [];
  let offset = 0, total: number | undefined, mime = "";
  do {
    if (disposed()) throw new Error("历史封面查看已关闭");
    const chunk = await request(path + `&offset=${offset}`) as Chunk;
    if (disposed()) throw new Error("历史封面查看已关闭");
    if (!chunk || !["image/jpeg", "image/png", "image/gif", "image/webp"].includes(chunk.mime)) throw invalid();
    const bytes = unpack(chunk);
    if (chunk.total_bytes === undefined && offset === 0) return new Blob([bytes], { type: chunk.mime });
    total = validateChunk(chunk, bytes, offset, total, mime); mime = chunk.mime;
    offset += bytes.length;
    if (offset > total) throw invalid();
    parts.push(bytes);
  } while (offset < total);
  return new Blob(parts, { type: mime });
}
