-- Run only in the private D1 database bound as DB. Never commit database exports.
CREATE TABLE IF NOT EXISTS oauth_sessions (
  session_hash TEXT PRIMARY KEY,
  encrypted_payload TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_states (
  owner TEXT PRIMARY KEY CHECK(owner='owner'),
  state_hash TEXT NOT NULL UNIQUE,
  session_hash TEXT NOT NULL,
  encrypted_payload TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS whop_credentials (
  owner TEXT PRIMARY KEY CHECK(owner='owner'),
  encrypted_payload TEXT,
  expires_at INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 0,
  authorization_generation INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'empty'
    CHECK(status IN ('empty','authorizing','ready','rotating','reauthorization_required')),
  updated_at INTEGER NOT NULL DEFAULT 0,
  renewal_count INTEGER NOT NULL DEFAULT 0,
  last_renewed_at INTEGER
);
INSERT OR IGNORE INTO whop_credentials(owner) VALUES ('owner');
CREATE TABLE IF NOT EXISTS whop_observations (
  goal TEXT PRIMARY KEY CHECK(goal IN ('clipping','ugc_content')),
  encrypted_payload TEXT NOT NULL,
  observed_at INTEGER NOT NULL,
  authorization_generation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS owner_login_throttle (
  owner TEXT PRIMARY KEY CHECK(owner='owner'),
  window_start INTEGER NOT NULL,
  attempts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS whop_runs (
  owner TEXT PRIMARY KEY CHECK(owner='owner'),
  observed_at INTEGER NOT NULL,
  status TEXT NOT NULL,
  http_status INTEGER NOT NULL
);
