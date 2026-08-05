// Package reqid generates/propagates the X-Zuno-Request-Id header
// (ADR-0045: "preserve request correlation ... across the chain") used to
// correlate one chat turn's SSE stream across the
// Frontend -> BFF -> Agent Runtime hops in each service's logs. A small
// hand-rolled UUIDv4 (crypto/rand only) rather than a dependency,
// consistent with this component's existing stdlib-only choices (see
// README.md's "Why standard library only").
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
// carries one, otherwise mints a new one. agent-frontend is normally the
// first hop (browser -> frontend has no request ID yet), so it is
// normally the one minting the ID that agent-bff and agent-runtime then
// propagate unchanged.
func FromHeaderOrNew(h http.Header) string {
	if v := h.Get(Header); v != "" {
		return v
	}
	return New()
}
