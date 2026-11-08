// node --experimental-strip-types --test src/video.test.ts   (Node 22+; the CI image has it)
import assert from "node:assert/strict";
import { test } from "node:test";
import { codecFromAnnexB, parseVideoMessage, quantile } from "./video.ts";

function message(payload: number[], opts: { key?: boolean; pts?: number; seq?: number | null } = {}): ArrayBuffer {
  const buf = new ArrayBuffer(14 + payload.length);
  const view = new DataView(buf);
  view.setUint8(0, 0x56);
  view.setUint8(1, opts.key ? 1 : 0);
  view.setBigUint64(2, BigInt(opts.pts ?? 0));
  view.setUint32(10, opts.seq === undefined || opts.seq === null ? 0xffffffff : opts.seq);
  new Uint8Array(buf, 14).set(payload);
  return buf;
}

test("parses the header the runtime writes", () => {
  const m = parseVideoMessage(message([0, 0, 0, 1, 9], { key: true, pts: 123456, seq: 7 }));
  assert.ok(m);
  assert.equal(m.keyframe, true);
  assert.equal(m.ptsUs, 123456);
  assert.equal(m.seq, 7);
  assert.deepEqual([...m.data], [0, 0, 0, 1, 9]);
});

test("a frame before any control carries no sequence", () => {
  assert.equal(parseVideoMessage(message([1, 2, 3]))?.seq, null);
});

test("anything else is ignored", () => {
  assert.equal(parseVideoMessage(new ArrayBuffer(4)), null);
  const wrongTag = message([1, 2, 3]);
  new DataView(wrongTag).setUint8(0, 0x58);
  assert.equal(parseVideoMessage(wrongTag), null);
});

test("the codec string comes from the SPS", () => {
  // 00 00 00 01 | 67 42 c0 1f ... : NAL type 7, profile 0x42, constraints 0xc0, level 0x1f
  const au = new Uint8Array([0, 0, 0, 1, 0x67, 0x42, 0xc0, 0x1f, 0xda, 0, 0, 0, 1, 0x68, 0xce]);
  assert.equal(codecFromAnnexB(au), "avc1.42c01f");
  assert.equal(codecFromAnnexB(new Uint8Array([0, 0, 0, 1, 0x65, 0x88, 0x84, 0, 0, 0, 0])), null);
});

test("quantiles", () => {
  assert.equal(quantile([], 0.95), 0);
  assert.equal(quantile([5], 0.5), 5);
  assert.equal(quantile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.5), 6);
  assert.equal(quantile([10, 1, 5], 1), 10);
});
