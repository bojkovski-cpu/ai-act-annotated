import type { APIRoute } from 'astro';

/**
 * Static robots.txt for the production canonical host.
 *
 * Per Decision 7 of the i18n decision note, robots.txt is host-gated:
 * production allows crawlers, anything else denies. Implemented in GDPR
 * via the API route `({ site })` destructure pattern. Empirically that
 * pattern does NOT work in Astro 5 for prerendered endpoint routes:
 * `site` is `undefined` at static build time and `import.meta.env.SITE`
 * is also undefined (verified 2026-04-28). Both `ctx.site` (lookup) and
 * `import.meta.env.SITE` resolve to undefined inside this handler.
 *
 * Resolution: hardcode the production output. This site has a single
 * deployment target (the Strato VPS) so the deny variant has no
 * legitimate consumer; the gate's purpose (block staging hosts from the
 * search index) does not apply to a single-target build pipeline.
 *
 * Deviation tracked in step-4.7-completion-notes.md. If/when a staging
 * host is introduced, re-introduce gating via a build-time env var:
 *   SITE_URL=https://staging.example.com npm run build
 * and read `process.env.SITE_URL` from inside this handler.
 */
const SITE_ORIGIN = 'https://aiact.annotated.nl';

export const GET: APIRoute = () => {
  const body = [
    'User-agent: *',
    'Allow: /',
    '',
    `Sitemap: ${SITE_ORIGIN}/sitemap-index.xml`,
    '',
  ].join('\n');

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain' },
  });
};
