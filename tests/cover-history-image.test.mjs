import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readHistoryImage } from '../cinecircuit_plugins/media_cover_generator/historyImage.ts';

function packet(bytes, offset, total) {
  const words = [];
  for (let i = 0; i < bytes.length; i += 4) {
    words.push(((bytes[i] || 0) | (bytes[i + 1] || 0) << 8 | (bytes[i + 2] || 0) << 16 | (bytes[i + 3] || 0) << 24) >>> 0);
  }
  return { image_words: words, byte_length: bytes.length, mime: 'image/webp', offset, total_bytes: total };
}

test('history image assembles bounded chunks without changing animated image bytes', async () => {
  const source = Uint8Array.from({ length: 1024 * 1024 + 7 }, (_, i) => i % 256);
  const offsets = [];
  const blob = await readHistoryImage(async path => {
    const offset = Number(new URL(path, 'http://local').searchParams.get('offset'));
    offsets.push(offset);
    return packet(source.subarray(offset, offset + 1024 * 1024), offset, source.length);
  }, '/history_image?id=cover', () => false);
  assert.deepEqual(offsets, [0, 1024 * 1024]);
  assert.equal(blob.type, 'image/webp');
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), source);
});

test('history image rejects mismatched offsets, changed totals and oversized declarations', async () => {
  for (const second of [packet([2], 0, 2), packet([2], 1, 3), packet([2], 1, 21 * 1024 * 1024)]) {
    let calls = 0;
    await assert.rejects(readHistoryImage(async () => ++calls === 1 ? packet([1], 0, 2) : second,
      '/history_image?id=cover', () => false), /数据不完整/);
  }
});

test('history image stops after disposal and accepts legacy image responses', async () => {
  let disposed = false, calls = 0;
  await assert.rejects(readHistoryImage(async () => {
    calls++; disposed = true;
    return packet([1], 0, 2);
  }, '/history_image?id=cover', () => disposed), /已关闭/);
  assert.equal(calls, 1);
  const blob = await readHistoryImage(async () => packet([1, 2, 3]), '/history_image?id=cover', () => false);
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), new Uint8Array([1, 2, 3]));
});
