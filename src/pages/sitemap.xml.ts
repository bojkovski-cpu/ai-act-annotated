import data from '@data/ai_act_structured.json';
import history from '@data/drafting_history.json';
import type { APIRoute } from 'astro';

const SITE = 'https://aiact.annotated.nl';

export const GET: APIRoute = async () => {
  const urls: string[] = [];

  // Top-level pages
  urls.push('/');
  urls.push('/about/');
  urls.push('/articles/');
  urls.push('/recitals/');
  urls.push('/annexes/');
  urls.push('/history/');

  // Chapter pages (legacy roman + new arabic aliases)
  for (const ch of data.chapters) {
    urls.push(`/chapter/${ch.roman.toLowerCase()}/`);
    urls.push(`/articles/chapter-${ch.number}/`);
  }

  // Articles
  for (const a of data.articles) {
    urls.push(`/articles/chapter-${a.chapter}/article-${a.number}/`);
  }

  // Recitals
  for (const r of data.recitals) {
    urls.push(`/recitals/recital-${r.number}/`);
  }

  // Annexes
  for (const ax of (data.annexes || [])) {
    urls.push(`/annexes/annex-${ax.id.toLowerCase()}/`);
  }

  // History
  for (const [vKey, vData] of Object.entries(history.by_version as any)) {
    urls.push(`/history/${vKey}/`);
    for (const n of Object.keys((vData as any).articles || {})) {
      urls.push(`/history/${vKey}/articles/${n}/`);
    }
    for (const n of Object.keys((vData as any).recitals || {})) {
      urls.push(`/history/${vKey}/recitals/${n}/`);
    }
  }

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map(u => `  <url><loc>${SITE}${u}</loc></url>`).join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
