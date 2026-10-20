import test from 'node:test';
import assert from 'node:assert/strict';
import { gunzipSync } from 'node:zlib';
import { collectOnce, objectKey } from '../src/collector.mjs';

const time = Date.parse('2026-10-20T11:05:00.000Z');
function fixtureFeed(type, count = 1517, stale = false) {
  return JSON.stringify({
    lastUpdatedOther: Math.floor(time / 1000) - (stale ? 4000 : 60),
    data: { stations: Array.from({length: count}, (_, i) => ({station_id: i+1, ...(type === 'station_status' ? {num_bikes_available:4, num_docks_available:6} : {capacity:10,lat:48.8,lon:2.3})})) },
  });
}
function setup({statusCode = 200, stale = false, staleInfo = false, count = 1517} = {}) {
  const data = new Map();
  const calls = [];
  const bucket = {
    async head(key) { return data.has(key) ? {} : null; },
    async put(key, payload, options) {
      if (data.has(key)) return null;
      assert.equal(options.storageClass, 'Standard');
      assert.equal(options.onlyIf.get('If-None-Match'), '*');
      assert.ok(payload instanceof ArrayBuffer);
      const bytes = new Uint8Array(payload);
      data.set(key, bytes);
      return {key,size:bytes.length};
    },
  };
  async function fetchMock(url) {
    calls.push(url);
    const which = url.endsWith('station_status.json') ? 'station_status' : 'station_information';
    return new Response(statusCode === 200 ? fixtureFeed(which, count, (which === 'station_status' && stale) || (which === 'station_information' && staleInfo)) : 'error', {status:statusCode});
  }
  return {data, calls, bucket, fetchMock};
}

test('one scheduled run compresses a complete provenance record and stores once', async () => {
  const x = setup();
  const options = {scheduledTime:time,now:time,fetchImpl:x.fetchMock};
  const first = await collectOnce({URBAN_ARCHIVES:x.bucket}, options);
  assert.equal(first.state,'archived');
  assert.equal(first.stations,1517);
  assert.equal(x.data.size,1);
  const second = await collectOnce({URBAN_ARCHIVES:x.bucket}, options);
  assert.equal(second.state,'already_archived');
  assert.equal(x.calls.length,2);
  const record=JSON.parse(gunzipSync(x.data.get(first.key)).toString());
  assert.equal(record.schema_version,1);
  assert.equal(record.scheduled_at,'2026-10-20T11:05:00Z');
  assert.equal(record.counts.station_status,1517);
  assert.equal(record.sha256_raw.station_information.length,64);
  assert.equal(JSON.parse(record.raw_json.station_status).data.stations.length,1517);
});
test('fail closed on HTTP error, never write', async () => {
  const x = setup({statusCode:503});
  await assert.rejects(collectOnce({URBAN_ARCHIVES:x.bucket},{scheduledTime:time,now:time,fetchImpl:x.fetchMock}),/HTTP 503/);
  assert.equal(x.data.size,0);
});
test('fail closed on stale published data', async () => {
  const x = setup({stale:true});
  await assert.rejects(collectOnce({URBAN_ARCHIVES:x.bucket},{scheduledTime:time,now:time,fetchImpl:x.fetchMock}),/stale feed/);
  assert.equal(x.data.size,0);
});
test('fail closed on suspicious station count', async () => {
  const x=setup({count:2});
  await assert.rejects(collectOnce({URBAN_ARCHIVES:x.bucket},{scheduledTime:time,now:time,fetchImpl:x.fetchMock}),/station count/);
});
test('must have configured bucket binding', async () => {
  await assert.rejects(collectOnce({}, {scheduledTime:time,now:time}),/binding/);
});
test('UTC object key deterministic', () => {
  assert.equal(objectKey(time),'r2-captures/v1/2026-10-20/snapshot-20261020T110500Z.json.gz');
});
test('older station_information is permitted while station_status must be fresh', async () => {
  const x=setup({staleInfo:true});
  const result=await collectOnce({URBAN_ARCHIVES:x.bucket},{scheduledTime:time,now:time,fetchImpl:x.fetchMock});
  assert.equal(result.state,'archived');
});
