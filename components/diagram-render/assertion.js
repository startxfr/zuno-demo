"use strict";
// WP-250 lot 2: the per-call assertion of the mcp-gateway (typ zuno-call+jwt, EdDSA, signed by
// Vault Transit, see components/mcp-gateway/app/call_assertion.py), verified here instead of the
// retired shared workload token. Same checks as the Python verifier in the MCP servers, minus
// the arguments hash (the body of /render is not the tool-call arguments JSON): the signature,
// the issuer, the audience, a lifetime of at most 60 s, the gateway actor, the tool name and a
// single use per jti. Fail closed: no public key configured means every request is refused.
const crypto = require("crypto");

const TYPE = "zuno-call+jwt";
const ISSUER = "mcp-gateway";
const MAX_TTL_SECONDS = 60;
const LEEWAY_SECONDS = 5;

class AssertionError extends Error {}

function b64urlDecode(part) {
  if (!/^[A-Za-z0-9_-]*$/.test(part)) throw new AssertionError("malformed call assertion");
  return Buffer.from(part.replace(/-/g, "+").replace(/_/g, "/"), "base64");
}

function parseJson(buffer) {
  try {
    const value = JSON.parse(buffer.toString("utf8"));
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("not an object");
    return value;
  } catch (e) {
    throw new AssertionError("malformed call assertion");
  }
}

function createVerifier({ publicKeyPem, audience, tool, now = () => Date.now() / 1000 }) {
  let key = null;
  if (publicKeyPem) {
    try {
      const candidate = crypto.createPublicKey(publicKeyPem);
      if (candidate.asymmetricKeyType === "ed25519") key = candidate;
    } catch (e) {
      key = null;
    }
  }
  const seen = new Map();

  function consume(jti, exp) {
    const t = now();
    for (const [id, until] of seen) if (until < t) seen.delete(id);
    if (seen.has(jti)) return false;
    seen.set(jti, exp + LEEWAY_SECONDS);
    return true;
  }

  function verify(token) {
    if (!key) throw new AssertionError("no call-assertion public key is configured");
    const parts = String(token || "").split(".");
    if (parts.length !== 3) throw new AssertionError("malformed call assertion");
    const header = parseJson(b64urlDecode(parts[0]));
    if (header.typ !== TYPE || header.alg !== "EdDSA") throw new AssertionError("not a gateway call assertion");
    const signature = b64urlDecode(parts[2]);
    if (!crypto.verify(null, Buffer.from(parts[0] + "." + parts[1], "ascii"), key, signature)) {
      throw new AssertionError("invalid call assertion signature");
    }
    const claims = parseJson(b64urlDecode(parts[1]));
    const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (claims.iss !== ISSUER || !aud.includes(audience)) throw new AssertionError("call assertion for another audience");
    const { iat, exp } = claims;
    if (!Number.isInteger(iat) || !Number.isInteger(exp) || exp < iat || exp - iat > MAX_TTL_SECONDS) {
      throw new AssertionError("call assertion lifetime is not within 60 seconds");
    }
    const t = now();
    if (iat > t + LEEWAY_SECONDS || t > exp + LEEWAY_SECONDS) throw new AssertionError("call assertion expired or not yet valid");
    if (!claims.act || claims.act.sub !== ISSUER) throw new AssertionError("call assertion has no gateway actor");
    if (typeof claims.jti !== "string" || claims.jti === "") throw new AssertionError("call assertion has no jti");
    if (claims.tool !== tool) throw new AssertionError("the call assertion was minted for another tool");
    if (!consume(claims.jti, exp)) throw new AssertionError("the call assertion was already used");
    return claims;
  }

  return { verify };
}

function middleware(verifier) {
  return (req, res, next) => {
    const header = req.get("Authorization") || "";
    const token = header.slice(0, 7).toLowerCase() === "bearer " ? header.slice(7).trim() : "";
    if (!token) return res.status(401).json({ error: "a gateway call assertion is required" });
    try {
      verifier.verify(token);
    } catch (e) {
      if (!(e instanceof AssertionError)) throw e;
      return res.status(401).json({ error: e.message });
    }
    return next();
  };
}

module.exports = { AssertionError, createVerifier, middleware, TYPE, ISSUER };
