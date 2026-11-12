"use strict";
// node --test test/   (Node >= 18) or  node test/assertion.test.js  (Node >= 12, plain asserts)
const assert = require("assert");
const crypto = require("crypto");
const { createVerifier, middleware, AssertionError } = require("../assertion");

const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
const other = crypto.generateKeyPairSync("ed25519");
const pem = publicKey.export({ type: "spki", format: "pem" });
const b64 = (o) => Buffer.from(typeof o === "string" ? o : JSON.stringify(o)).toString("base64url");

function mint(over = {}, key = privateKey, header = { typ: "zuno-call+jwt", alg: "EdDSA" }) {
  const iat = over.iat !== undefined ? over.iat : 1000;
  const claims = { iss: "mcp-gateway", aud: "diagram-render", sub: "ana", act: { sub: "mcp-gateway" }, tool: "render",
    iat, exp: iat + 60, jti: crypto.randomBytes(8).toString("hex"), ...over };
  const signing = b64(header) + "." + b64(claims);
  return signing + "." + crypto.sign(null, Buffer.from(signing), key).toString("base64url");
}

const make = (extra = {}) => createVerifier({ publicKeyPem: pem, audience: "diagram-render", tool: "render", now: () => 1010, ...extra });
const refused = (token, verifier = make(), re = /./) => assert.throws(() => verifier.verify(token), (e) => e instanceof AssertionError && re.test(e.message));

const tests = {
  "a valid assertion is accepted"() { assert.strictEqual(make().verify(mint()).sub, "ana"); },
  "a replayed assertion is refused"() { const v = make(), t = mint(); v.verify(t); refused(t, v, /already used/); },
  "a forged signature is refused"() { refused(mint({}, other.privateKey), make(), /signature/); },
  "another audience is refused"() { refused(mint({ aud: "aap" }), make(), /audience/); },
  "another issuer is refused"() { refused(mint({ iss: "evil" }), make(), /audience/); },
  "another tool is refused"() { refused(mint({ tool: "other" }), make(), /another tool/); },
  "a schema-read assertion (no tool) is refused"() { refused(mint({ tool: "" }), make(), /another tool/); },
  "an expired assertion is refused"() { refused(mint({ iat: 900 }), make(), /expired/); },
  "an assertion dated in the future is refused"() { refused(mint({ iat: 1100 }), make(), /expired|valid/); },
  "a lifetime above 60 s is refused"() { refused(mint({ exp: 1000 + 61 }), make(), /lifetime/); },
  "no gateway actor is refused"() { refused(mint({ act: { sub: "x" } }), make(), /actor/); },
  "a wrong type or algorithm is refused"() {
    refused(mint({}, privateKey, { typ: "JWT", alg: "EdDSA" }), make(), /not a gateway/);
    refused(mint({}, privateKey, { typ: "zuno-call+jwt", alg: "none" }), make(), /not a gateway/);
  },
  "garbage is refused"() { for (const t of ["", "a.b", "a.b.c", "!!.!!.!!", undefined]) refused(t); },
  "no key means everything is refused"() { refused(mint(), createVerifier({ publicKeyPem: "", audience: "diagram-render", tool: "render" }), /no call-assertion/); },
  "an RSA key is not accepted as the public key"() {
    const rsa = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 }).publicKey.export({ type: "spki", format: "pem" });
    refused(mint(), make({ publicKeyPem: rsa }), /no call-assertion/);
  },
  "the middleware answers 401 without a bearer and passes a good one"() {
    const mw = middleware(make());
    const res = () => ({ code: 0, status(c) { this.code = c; return this; }, json() { return this; } });
    const req = (h) => ({ get: () => h });
    const r1 = res(); let called = false;
    mw(req(""), r1, () => { called = true; });
    assert.strictEqual(r1.code, 401); assert.strictEqual(called, false);
    const r2 = res(); mw(req("Bearer " + mint()), r2, () => { called = true; });
    assert.strictEqual(called, true);
    const r3 = res(); called = false; mw(req("Bearer " + mint({ aud: "aap" })), r3, () => { called = true; });
    assert.strictEqual(r3.code, 401); assert.strictEqual(called, false);
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { fn(); console.log("PASS", name); } catch (e) { failed += 1; console.log("FAIL", name, "-", e.message); }
}
process.exit(failed ? 1 : 0);
