#!/usr/bin/env node
// check_links.mjs - Link-integrity wrapper around linkinator (Step 4.8, v1.1).
// Walks dist/ recursively; reports any internal href that does not resolve.
// External URLs (https?://...) are skipped (format-checked elsewhere).
//
// Outputs:
//   control-room/reference/linkinator-output.json
//   stdout summary; exit 0 if zero broken, 1 otherwise.
// Idempotent: results are sorted before writing.
// Dependency: linkinator (npm install --no-save linkinator).

import { check, LinkState } from 'linkinator';
import { writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const distPath = resolve(repoRoot, 'dist');
const defaultReport = resolve(repoRoot, '..', 'control-room', 'reference', 'linkinator-output.json');

const args = process.argv.slice(2);
let reportPath = defaultReport;
let jsonOnly = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--output' && args[i + 1]) reportPath = resolve(args[++i]);
  else if (args[i] === '--json-only') jsonOnly = true;
  else if (args[i] === '--help' || args[i] === '-h') {
    console.log('Usage: node scripts/check_links.mjs [--output PATH] [--json-only]');
    process.exit(0);
  }
}

if (!jsonOnly) console.log('[check_links] Crawling ' + distPath + ' (recursive, skip external)...');
const t0 = Date.now();

const result = await check({
  path: distPath,
  recurse: true,
  directoryListing: true,
  linksToSkip: ['^https?://', '^mailto:', '^tel:', '^javascript:'],
  silent: true,
});

const elapsedMs = Date.now() - t0;
const links = result.links || [];
const broken = links.filter((l) => l.state === LinkState.BROKEN);
const ok = links.filter((l) => l.state === LinkState.OK);
const skipped = links.filter((l) => l.state === LinkState.SKIPPED);

const sortFn = (a, b) =>
  String(a.url).localeCompare(String(b.url)) ||
  String(a.parent || '').localeCompare(String(b.parent || ''));
broken.sort(sortFn);

function serialize(link) {
  return {
    url: link.url,
    parent: link.parent || null,
    status: link.status === undefined ? null : link.status,
    state: link.state,
  };
}

const report = {
  step: '4.8',
  generated_at: new Date().toISOString(),
  scanned_root: distPath,
  options: {
    recurse: true,
    directory_listing: true,
    linksToSkip: ['^https?://', '^mailto:', '^tel:', '^javascript:'],
  },
  totals: {
    total: links.length,
    ok: ok.length,
    broken: broken.length,
    skipped: skipped.length,
    elapsed_ms_omitted_for_idempotency: true,
  },
  broken: broken.map(serialize),
  skipped_count: skipped.length,
};

writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n', 'utf8');

if (jsonOnly) {
  console.log(JSON.stringify(report, null, 2));
} else {
  console.log('[check_links] Total links:    ' + links.length);
  console.log('[check_links] OK:             ' + ok.length);
  console.log('[check_links] Broken:         ' + broken.length);
  console.log('[check_links] Skipped (ext):  ' + skipped.length);
  console.log('[check_links] Elapsed:        ' + elapsedMs + ' ms');
  console.log('[check_links] Report:         ' + reportPath);
  if (broken.length > 0) {
    console.log('');
    console.log('[check_links] FIRST 10 BROKEN LINKS:');
    for (const b of broken.slice(0, 10)) {
      const code = b.status === undefined || b.status === null ? '???' : b.status;
      console.log('  ' + code + '  ' + b.url);
      console.log('         from: ' + (b.parent || '(unknown)'));
    }
  }
  console.log('');
  if (broken.length === 0) console.log('[check_links] PASS - zero broken internal links.');
  else console.log('[check_links] FAIL - ' + broken.length + ' broken internal links.');
}

process.exit(broken.length === 0 ? 0 : 1);
