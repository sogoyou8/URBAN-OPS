// Cloudflare Workers FREE plan: dispatch the existing GitHub P3 collector.
// This Worker never reads the Velib API, uses R2, or stores observations.
// GITHUB_DISPATCH_TOKEN must be installed as a Cloudflare encrypted secret.
const endpoint = 'https://api.github.com/repos/sogoyou8/URBAN-OPS/actions/workflows/collect.yml/dispatches';

export async function dispatchOnce(env, {
  scheduledTime, fetchImpl = fetch, timeoutMs = 15000,
} = {}) {
  if (!env || typeof env.GITHUB_DISPATCH_TOKEN !== 'string' ||
      env.GITHUB_DISPATCH_TOKEN.trim().length < 12) {
    throw new Error('Missing GitHub dispatch secret. No action launched.');
  }
  const when = new Date(scheduledTime);
  if (!Number.isFinite(when.getTime())) {
    throw new Error('Missing scheduled timestamp.');
  }
  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: {
      'Accept': 'application/vnd.github+json',
      'Authorization': 'Bearer ' + env.GITHUB_DISPATCH_TOKEN,
      'Content-Type': 'application/json',
      'User-Agent': 'urban-ops-free-cron-dispatcher',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({ ref: 'main' }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  // GitHub workflow_dispatch returns 204 on success.
  if (response.status !== 204) {
    // Never log response body or request headers: token must not leak.
    throw new Error('GitHub workflow dispatch rejected: HTTP ' + response.status);
  }
  return { state: 'dispatched', scheduled_at: when.toISOString(), workflow: 'collect.yml' };
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(dispatchOnce(env, { scheduledTime: controller.scheduledTime })
      .then(result => console.log(JSON.stringify(result)))
      .catch(error => {
        // Only output message; NEVER output env/secrets or request.
        console.error('FREE_DISPATCH_FAILED:', String(error?.message || error));
        throw error;
      }));
  },
  // No HTTP endpoint: cannot be used as a public workflow trigger.
  async fetch() { return new Response('Not found', { status: 404 }); },
};
