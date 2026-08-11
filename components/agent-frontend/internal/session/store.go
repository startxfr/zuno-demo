package session

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/redis/go-redis/v9"
)

// Store persists Session records server-side, keyed by an opaque session
// ID (ADR-0042: "store only an opaque session identifier in the
// browser... keep access token, refresh token, groups, expiry and
// delegated provider tokens in a server-side session store"). Values are
// AES-256-GCM encrypted before being written to Redis ("encryption at
// rest where applicable") - Redis itself has no application-level
// awareness of token contents.
type Store struct {
	client *redis.Client
	aead   cipher.AEAD
	prefix string
}

// NewStore builds a Store. encryptionKey must be exactly 32 bytes
// (AES-256). addr/password/db are passed straight to redis.Options - see
// internal/config for how these are sourced (REDIS_ADDR, REDIS_PASSWORD
// from Vault via ExternalSecret, ADR-0024).
func NewStore(addr, password string, db int, encryptionKey []byte) (*Store, error) {
	if len(encryptionKey) != 32 {
		return nil, fmt.Errorf("session encryption key must be exactly 32 bytes, got %d", len(encryptionKey))
	}
	block, err := aes.NewCipher(encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("building AES cipher: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("building AES-GCM AEAD: %w", err)
	}

	client := redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: password,
		DB:       db,
	})

	return &Store{client: client, aead: aead, prefix: "zuno:session:"}, nil
}

// Ping verifies connectivity - called once at startup so a misconfigured
// Redis address fails loudly instead of degrading every request later.
func (st *Store) Ping(ctx context.Context) error {
	return st.client.Ping(ctx).Err()
}

func (st *Store) key(id string) string {
	return st.prefix + id
}

func (st *Store) encrypt(plaintext []byte) ([]byte, error) {
	nonce := make([]byte, st.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	return st.aead.Seal(nonce, nonce, plaintext, nil), nil
}

func (st *Store) decrypt(ciphertext []byte) ([]byte, error) {
	nonceSize := st.aead.NonceSize()
	if len(ciphertext) < nonceSize {
		return nil, errors.New("ciphertext too short")
	}
	nonce, sealed := ciphertext[:nonceSize], ciphertext[nonceSize:]
	return st.aead.Open(nil, nonce, sealed, nil)
}

// Put writes (creating or overwriting) the session record at id, with a
// Redis-level expiration of ttl. Callers choose ttl based on the
// session's own maximum lifetime (config.SessionMaxLifetime), not the
// short-lived access token's own expiry - a session outlives many access
// token refreshes.
func (st *Store) Put(ctx context.Context, id string, s Session, ttl time.Duration) error {
	plaintext, err := json.Marshal(s)
	if err != nil {
		return err
	}
	ciphertext, err := st.encrypt(plaintext)
	if err != nil {
		return err
	}
	return st.client.Set(ctx, st.key(id), ciphertext, ttl).Err()
}

// Get reads and decrypts the session record at id. Returns
// redis.Nil-wrapping ErrNotFound if the id doesn't exist (expired,
// revoked, or never issued) - callers must treat this as "not
// authenticated", the same as any other Load failure.
var ErrNotFound = errors.New("session not found")

func (st *Store) Get(ctx context.Context, id string) (*Session, error) {
	ciphertext, err := st.client.Get(ctx, st.key(id)).Bytes()
	if errors.Is(err, redis.Nil) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	plaintext, err := st.decrypt(ciphertext)
	if err != nil {
		return nil, fmt.Errorf("decrypting session record: %w", err)
	}
	var s Session
	if err := json.Unmarshal(plaintext, &s); err != nil {
		return nil, err
	}
	return &s, nil
}

// Delete revokes the session record at id (logout, or explicit
// revocation) - unlike clearing only the browser cookie, this makes the
// opaque ID permanently unusable even if an attacker captured it before
// revocation.
func (st *Store) Delete(ctx context.Context, id string) error {
	return st.client.Del(ctx, st.key(id)).Err()
}
