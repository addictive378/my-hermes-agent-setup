/**
 * Technical SEO auditor for a live news/content site.
 *
 * Checks what search engines actually require, against the RUNNING deployment:
 *   - sitemap vs database (both directions)
 *   - canonical, OpenGraph, title/description length
 *   - JSON-LD NewsArticle completeness and ISO 8601 dates
 *   - broken self-links (footer/header/policy pages)
 *
 * Usage:
 *   npx tsx scripts/audit-seo.ts --base https://example.com
 *   npx tsx scripts/audit-seo.ts            # defaults to localhost:3000
 *
 * Exit code 1 when blockers are found, so it can gate a release.
 */
import { db } from "../src/db";
import { articles, categories } from "../src/db/schema";
import { eq, desc, sql } from "drizzle-orm";

const BASE = (() => {
  const i = process.argv.indexOf("--base");
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : "http://127.0.0.1:3000";
})();

const CRAWLER_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";

/** ISO 8601 with explicit zone — the only format Google reliably parses. */
const ISO_8601 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

/** Self-links every content site should serve; 404s here block Google News. */
const POLICY_PATHS = [
  "/tentang", "/about", "/kontak", "/contact", "/redaksi",
  "/privasi", "/privacy", "/syarat", "/pedoman", "/kebijakan-editorial",
];

type Problem = { level: "BLOCKER" | "WARN"; where: string; message: string };
const problems: Problem[] = [];
const blocker = (where: string, message: string) =>
  problems.push({ level: "BLOCKER", where, message });
const warn = (where: string, message: string) =>
  problems.push({ level: "WARN", where, message });

async function get(path: string) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "User-Agent": CRAWLER_UA },
    cache: "no-store",
  });
  return { status: res.status, body: await res.text() };
}

function extractJsonLd(html: string): unknown[] {
  const out: unknown[] = [];
  const re = /<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const parsed = JSON.parse(m[1]);
    out.push(...(Array.isArray(parsed) ? parsed : [parsed]));
  }
  return out;
}

function findByType(nodes: unknown[], type: string): Record<string, unknown> | null {
  for (const n of nodes) {
    if (n && typeof n === "object" && (n as Record<string, unknown>)["@type"] === type) {
      return n as Record<string, unknown>;
    }
  }
  return null;
}

async function main() {
  console.log(`\n=== SEO audit ${BASE} ===\n`);

  // ── 1. Published records, from the database ──────────────────
  const rows = await db
    .select({
      slug: articles.slug,
      status: articles.status,
      title: articles.title,
      authorId: articles.authorId,
      categorySlug: categories.slug,
    })
    .from(articles)
    .leftJoin(categories, eq(articles.categoryId, categories.id))
    .orderBy(desc(articles.publishedAt));

  const published = rows.filter((r) => r.status === "published");
  const pathOf = (r: { slug: string; categorySlug: string | null }) =>
    r.categorySlug ? `/${r.categorySlug}/${r.slug}` : `/artikel/${r.slug}`;

  console.log(`published: ${published.length} | total: ${rows.length}\n`);

  // ── 2. Sitemap reconciliation ────────────────────────────────
  const sitemap = await get("/sitemap.xml");
  const locs = [...sitemap.body.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  const sitemapPaths = new Set(
    locs.map((u) => {
      try { return new URL(u).pathname; } catch { return u; }
    })
  );
  const publishedPaths = new Set(published.map(pathOf));

  console.log(`sitemap.xml: HTTP ${sitemap.status}, ${locs.length} URL`);

  for (const p of sitemapPaths) {
    if (/\/[a-z0-9-]+\/[a-z0-9-]+$/.test(p) && !publishedPaths.has(p)) {
      blocker("sitemap", `memuat URL non-published (crawler akan kena 404): ${p}`);
    }
  }
  for (const p of publishedPaths) {
    if (!sitemapPaths.has(p)) {
      blocker("sitemap", `published tapi tidak ada di sitemap (mungkin tidak terindeks): ${p}`);
    }
  }

  // ── 3. Policy pages ──────────────────────────────────────────
  console.log(`\nCek halaman kebijakan:`);
  for (const p of POLICY_PATHS) {
    const { status } = await get(p);
    if (status === 404) {
      blocker("policy", `${p} -> 404 (syarat Google News; cek juga apakah footer menautkannya)`);
      console.log(`  404  ${p}`);
    }
  }

  // ── 4. Per-article checks ────────────────────────────────────
  console.log(`\nCek artikel:`);
  for (const row of published) {
    const path = pathOf(row);
    const { status, body: html } = await get(path);
    if (status !== 200) {
      blocker(path, `HTTP ${status}`);
      continue;
    }

    const canonical = html.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
    if (!canonical) blocker(path, "canonical hilang");
    else if (!canonical.startsWith("https://")) blocker(path, `canonical bukan absolut: ${canonical}`);
    else if (!canonical.endsWith(path)) blocker(path, `canonical tidak cocok path: ${canonical}`);

    for (const prop of ["og:title", "og:description", "og:url", "og:image"]) {
      if (!new RegExp(`<meta property="${prop}"`).test(html)) warn(path, `${prop} hilang`);
    }

    const title = html.match(/<title>([^<]*)<\/title>/)?.[1] ?? "";
    if (title.length > 70) warn(path, `title ${title.length} char (ideal <=60, dipotong Google)`);
    const desc = html.match(/<meta name="description" content="([^"]*)"/)?.[1] ?? "";
    if (desc.length > 165) warn(path, `meta description ${desc.length} char (ideal 120-160)`);

    let nodes: unknown[];
    try {
      nodes = extractJsonLd(html);
    } catch (e) {
      blocker(path, `JSON-LD tidak valid: ${(e as Error).message}`);
      continue;
    }

    const ld = findByType(nodes, "NewsArticle");
    if (!ld) {
      blocker(path, "JSON-LD NewsArticle tidak ditemukan");
    } else {
      if (!ld.headline) blocker(path, "headline kosong");
      if (!ld.publisher) blocker(path, "publisher kosong");
      // author is REQUIRED by Google for news content
      if (!ld.author) blocker(path, "author hilang di JSON-LD (wajib untuk Google News)");
      if (!ld.image) warn(path, "image kosong di JSON-LD");

      for (const f of ["datePublished", "dateModified"]) {
        const v = ld[f];
        if (!v) blocker(path, `${f} kosong`);
        else if (!ISO_8601.test(String(v))) {
          blocker(path, `${f} bukan ISO 8601: ${v} (Google membuang tanggal ini)`);
        }
      }
    }
    if (!findByType(nodes, "BreadcrumbList")) warn(path, "BreadcrumbList hilang");

    console.log(`  ok  ${path}`);
  }

  // ── 5. Summary ───────────────────────────────────────────────
  const blockers = problems.filter((p) => p.level === "BLOCKER");
  const warns = problems.filter((p) => p.level === "WARN");

  console.log(`\n--- Ringkasan ---`);
  console.log(`BLOCKER ${blockers.length} | WARN ${warns.length}`);
  for (const p of blockers) console.log(`  [BLOCKER] ${p.where}: ${p.message}`);
  for (const p of warns) console.log(`  [WARN   ] ${p.where}: ${p.message}`);

  process.exit(blockers.length > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error("Audit gagal:", e);
  process.exit(2);
});
