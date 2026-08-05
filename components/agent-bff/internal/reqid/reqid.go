// Package reqid propagates the X-Zuno-Request-Id header (ADR-0045:
// "preserve request correlation ... across the chain") through this hop
// (agent-frontend -> agent-bff -> agent-runtime). A small hand-rolled
// UUIDv4 (crypto/rand only) rather than a dependency - see
// components/agent-frontend/internal/reqid, which this package
// deliberately duplicates rather than sharing a module across two
// independently deployed services (same reasoning as
// components/agent-bff/internal/jwks's package comment).
package reqid

import (
	"crypto/rand"
	"fmt"
	"net/http"
)

// Header is the propagated header name, shared by agent-frontend,
// agent-bff and agent-runtime.
const Header = "X-Zuno-Request-Id"

// New generates a random UUIDv4 (RFC 4122).
func New() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40 // version 4
	b[8] = (b[8] & 0x3f) | 0x80 // variant 10 (RFC 4122)
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// FromHeaderOrNew returns the caller-supplied request ID if h already
// carries one (the normal case here - agent-frontend mints it), otherwise
// mints a new one so this service still logs a correlatable ID even when
// called directly (e.g. evaluations/tekos/security_checks.py, which calls
// this BFF without going through agent-frontend).
func FromHeaderOrNew(h http.Header) string {
	if v := h.Get(Header); v != "" {
		return v
	}
	return New()
}
