/** Synthetic owner state only; never uses environment credentials or production D1. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {randomValue} from '../src/worker.mjs';

const schema = readFileSync(new URL('../schema.sql', import.meta.url), 'utf8');

export function createFixture() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(schema);
  const adapter = {
    prepare(sql) {
      const statement = sqlite.prepare(sql);
      let args = [];
      const result = {
        bind(...values) { args = values; return result; },
        async first() { return statement.get(...args) || null; },
        async all() { return {results: statement.all(...args)}; },
        async run() { return {meta: statement.run(...args)}; },
      };
      return result;
    },
    async batch(statements) {
      sqlite.exec('BEGIN');
      try {
        const result = [];
        for (const statement of statements) result.push(await statement.run());
        sqlite.exec('COMMIT');
        return result;
      } catch (error) {
        sqlite.exec('ROLLBACK');
        throw error;
      }
    },
    withSession(value) { assert.equal(value, 'first-primary'); return adapter; },
  };
  return {
    sqlite,
    env: {
      DB: adapter,
      PUBLIC_ORIGIN: 'https://owner.example.workers.dev',
      WHOP_CLIENT_ID: 'app_browser_fixture',
      OWNER_PASSWORD: randomValue(),
      WHOP_BROKER_API_TOKEN: randomValue(),
      TOKEN_ENCRYPTION_KEY: randomValue(),
      REWARDS_LIVE_PUBLISHING: 'false',
    },
  };
}
