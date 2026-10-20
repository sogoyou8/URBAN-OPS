import test from 'node:test';
import assert from 'node:assert/strict';
import { dispatchOnce } from '../src/dispatcher.mjs';

const WHEN = Date.parse('2026-10-20T12:05:00Z');
const TOKEN = 'fake-test-token-not-a-real-secret';
const ENV = { GITHUB_DISPATCH_TOKEN: TOKEN };

test('dispatches existing P3 workflow on public main with least privilege', async () => {
  let calls = 0;
  const result = await dispatchOnce(ENV, {
    scheduledTime: WHEN,
    fetchImpl: async (url, request) => {
      calls++;
      assert.equal(url, 'https://api.github.com/repos/sogoyou8/URBAN-OPS/actions/workflows/collect.yml/dispatches');
      assert.equal(request.method, 'POST');
      assert.equal(request.headers.Authorization, 'Bearer ' + TOKEN);
      assert.deepEqual(JSON.parse(request.body), { ref: 'main' });
      assert.ok(request.signal);
      return new Response(null, { status: 204 });
    },
  });
  assert.equal(calls, 1);
  assert.deepEqual(result, { state: 'dispatched', scheduled_at: '2026-10-20T12:05:00.000Z', workflow: 'collect.yml' });
});

test('no token means no external call', async () => {
  let calls = 0;
  await assert.rejects(dispatchOnce({}, {
    scheduledTime: WHEN,
    fetchImpl: async () => { calls++; return new Response(null, { status: 204 }); },
  }), /Missing GitHub dispatch secret/);
  assert.equal(calls, 0);
});

test('expired or unauthorized token fails without revealing credentials', async () => {
  let error;
  try {
    await dispatchOnce(ENV, { scheduledTime: WHEN,
      fetchImpl: async () => new Response('bad credentials', { status: 401 }) });
  } catch (e) { error = e; }
  assert.ok(error);
  assert.match(error.message, /HTTP 401/);
  assert.ok(!error.message.includes(TOKEN));
  assert.ok(!error.message.includes('bad credentials'));
});

test('rate limit and server errors are not counted as captures', async () => {
  for (const status of [403, 422, 429, 500]) {
    await assert.rejects(
      dispatchOnce(ENV, { scheduledTime: WHEN, fetchImpl: async () => new Response(null, { status }) }),
      new RegExp('HTTP ' + status),
    );
  }
});

test('invalid cron timestamp fails closed before network', async () => {
  await assert.rejects(
    dispatchOnce(ENV, { scheduledTime: 'not-a-date',
      fetchImpl: async () => { throw new Error('Unexpected call'); } }),
    /Missing scheduled timestamp/,
  );
});

test('only cron handler is functional; HTTP entrypoint returns 404', async () => {
  const module = await import('../src/dispatcher.mjs');
  const response = await module.default.fetch();
  assert.equal(response.status, 404);
});
