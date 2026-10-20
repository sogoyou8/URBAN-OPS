// Data-only Cloudflare Scheduled Worker. No public data access and no deployment by default.
const API = 'https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/';
const URLS = Object.freeze({
  station_information: `${API}station_information.json`,
  station_status: `${API}station_status.json`,
});
const textDecoder = new TextDecoder('utf-8', { fatal: true });

const iso = (time) => new Date(time).toISOString().replace(/\.\d{3}Z$/, 'Z');
const hex = (buffer) => [...new Uint8Array(buffer)].map(byte => byte.toString(16).padStart(2, '0')).join('');

async function readFeed(name, fetchImpl, now) {
  const response = await fetchImpl(URLS[name], {
    method: 'GET', headers: { accept: 'application/json' }, signal: AbortSignal.timeout(25000),
  });
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length < 50 || bytes.length > 4_000_000) throw new Error(`${name}: implausible payload bytes=${bytes.length}`);
  const text = textDecoder.decode(bytes);
  const payload = JSON.parse(text);
  const stations = payload?.data?.stations;
  if (!Array.isArray(stations) || stations.length < 1000 || stations.length > 4000) {
    throw new Error(`${name}: unexpected station count`);
  }
  const epoch = payload?.lastUpdatedOther;
  if (!Number.isInteger(epoch) || epoch < 1_600_000_000 ||
      (name === 'station_status' && (now - epoch * 1000) > 30 * 60_000) ||
      (now - epoch * 1000) < -5 * 60_000) {
    throw new Error(`${name}: invalid/stale feed publication timestamp`);
  }
  if (!stations[0] || !Number.isInteger(stations[0].station_id)) {
    throw new Error(`${name}: invalid station identifier`);
  }
  const sha = hex(await crypto.subtle.digest('SHA-256', bytes));
  return { text, bytes: bytes.length, sha256: sha, count: stations.length, feed_epoch: epoch };
}

export function objectKey(scheduledTime) {
  const d = new Date(scheduledTime);
  if (!Number.isFinite(d.getTime())) throw new Error('Invalid scheduledTime');
  return `r2-captures/v1/${d.toISOString().slice(0, 10)}/snapshot-${iso(d.getTime()).replaceAll(':', '').replaceAll('-', '')}.json.gz`;
}

// The injected fetch and clock are for *offline tests only*. Production calls official HTTPS endpoints.
export async function collectOnce(env, { scheduledTime, fetchImpl = fetch, now = Date.now() } = {}) {
  if (!env?.URBAN_ARCHIVES || typeof env.URBAN_ARCHIVES.put !== 'function') {
    throw new Error('R2 binding URBAN_ARCHIVES missing — not archiving');
  }
  if (!Number.isFinite(scheduledTime)) throw new Error('A scheduled UTC timestamp is required');
  const key = objectKey(scheduledTime);
  if (await env.URBAN_ARCHIVES.head(key)) return { state: 'already_archived', key };
  const [information, status] = await Promise.all([
    readFeed('station_information', fetchImpl, now),
    readFeed('station_status', fetchImpl, now),
  ]);
  const record = {
    schema_version: 1,
    source: 'Vélib Métropole public open data (ODbL)',
    scheduled_at: iso(scheduledTime),
    collected_at: iso(now),
    sha256_raw: { station_information: information.sha256, station_status: status.sha256 },
    counts: { station_information: information.count, station_status: status.count },
    feed_updated_at: { station_information: iso(information.feed_epoch * 1000), station_status: iso(status.feed_epoch * 1000) },
    raw_json: { station_information: information.text, station_status: status.text },
  };
  // Streaming gzip to keep R2 Standard storage consumption down.
  const stream = new Blob([JSON.stringify(record)]).stream().pipeThrough(new CompressionStream('gzip'));
  // R2 put requires a known-length body: buffer the compressed snapshot (bounded by 2 x 4 MB feeds).
  const compressed = await new Response(stream).arrayBuffer();
  const saved = await env.URBAN_ARCHIVES.put(key, compressed, {
    onlyIf: new Headers({ 'If-None-Match': '*' }),
    httpMetadata: { contentType: 'application/json', contentEncoding: 'gzip' },
    customMetadata: { schema: 'urbanops-r2-1', captured_utc: record.collected_at },
    storageClass: 'Standard',
  });
  if (!saved) return { state: 'already_archived', key };
  return { state: 'archived', key, stations: status.count, info: information.count };
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(collectOnce(env, { scheduledTime: controller.scheduledTime })
      .then(result => console.log(JSON.stringify(result)))
      .catch(error => { console.error('ARCHIVE_FAILED', String(error)); throw error; }));
  },
  async fetch() { return new Response('Not found', { status: 404 }); },
};