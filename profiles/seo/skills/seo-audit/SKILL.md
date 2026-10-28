---
name: seo-audit
description: Use when auditing SEO of a Next.js news site.
version: 1.0.0
author: seo
license: MIT
metadata:
  hermes:
    tags: [seo, audit, nextjs, news, indexing]
    related_skills: [news-article-publishing, obsidian]
---

# SEO Audit (Next.js News Sites)

## When to Use

Trigger when Adi (or the leader) asks to: audit SEO health, check indexation/crawlability, verify an SEO fix landed after deploy, research keyword gaps into a content brief, or produce an SEO brief for a teammate on wartanusaku.site or another Next.js news site. Also trigger when an executor reports a brief's fix is done — verification is step 10 of this procedure.

## Role boundary
You are the SEO specialist — you audit, diagnose, write briefs, and verify. You do NOT write articles (writer) or change production code (softwareengineer). Every recommendation must include: evidence (curl/DB output), impact, effort, owner, and a verification command.

## Procedure

1. **Site liveness & basics** — confirm 200 on homepage, sitemap.xml, robots.txt, rss.xml, news-sitemap.xml. Record TTFB and size.
2. **E-E-A-T pages** — curl `/tentang`, `/kontak`, `/pedoman` (or `/kebijakan-editorial`). Check HTTP status AND `<meta name="robots">`. A 200 with `noindex` is as bad as 404 for E-E-A-T.
3. **Global metadata** — grep homepage and one article for `max-image-preview:large`, `max-snippet:-1`, explicit `robots` meta. Missing = Discover images suppressed.
4. **Category indexability** — curl each category (`/teknologi`, `/politik`, `/bisnis`, `/indonesia`, `/olahraga`). Flag any `noindex` — news categories must be indexed.
5. **Article sample deep-check** — pick one recent article URL from sitemap. Verify:
   - SSR body text present in HTML (not just skeleton): strip tags, measure char count; >1000 chars = OK.
   - Single H1 matching title.
   - JSON-LD types: `NewsArticle`, `BreadcrumbList`, `Person`, `NewsMediaOrganization` all present.
   - canonical self-referencing.
   - og:title, og:image, og:description, article:published_time, article:author present.
   - Internal links to other articles (count unique hrefs).
6. **Image quality** — `curl -I` on og:image URL; Content-Length < 50KB likely below 1200×630. Flag for regeneration.
7. **DB content gaps** — query `articles` table for published rows missing `seo_description`. Zero missing = brief closed; N missing = writer brief.
8. **Footer sitewide links** — grep homepage for footer hrefs to E-E-A-T pages. All five (/tentang, /kontak, /pedoman, /privasi, /syarat) should be present.
9. **Write outputs** — save audit report to `~/workspace/seo/audit-YYYY-MM-DD.md` AND `~/.hermes/obsidian/20-Research/`. Write P0/P1 brief to `~/workspace/seo/brief-<owner>-P0-YYYY-MM-DD.md` AND `~/.hermes/obsidian/30-Briefs/`.
10. **Escalate in group** — mention the owner bot (@softengin_bot / @warta_writer_bot) with numbered items, each with: evidence line, fix snippet, verification command. End by asking them to reply with verification output.

## Pitfalls

- **Never trust HTTP status alone for indexability.** A 200 page can carry `noindex`; a 404 may be intentional. Always grep `<meta name="robots">` on every URL you check.
- **Do not assume `/kebijakan-editorial` is required if `/pedoman` exists.** Indonesian news sites often use "Pedoman Pemberitaan" as their editorial policy page. Recommend 301 redirect instead of duplicate content.
- **animate-pulse in HTML does not mean client-only rendering.** Next.js streaming SSR includes skeleton markup alongside server-rendered text. Verify by stripping tags and measuring body text length, not by counting skeleton classes.
- **og:image file size is a reliable proxy for resolution.** Content-Length < 50KB almost always means sub-1200px width; Discover requires ≥1200×630. Flag small files without downloading to measure dimensions.
- **Brief format must include verification commands.** A brief without a curl/grep the executor can run to prove the fix is incomplete. Every P0 item ends with a one-line verification command.
- **Save to BOTH workspace and vault in the same call.** Adi checks both; writing only one creates a sync gap. Batch the two write_file calls.
- **Load DATABASE_URL from `~/news-web/.env.local` inside the query shell** (`set -a; . ~/news-web/.env.local; set +a`) — it is not exported into the agent shell, and it must never be echoed to chat.

## Output shape

Audit report sections (fixed order):
1. Ringkasan (3 sentences: condition, biggest problem, biggest opportunity)
2. Temuan table: # | Masalah | Bukti | Dampak | Usaha | Pemilik
3. Rencana Aksi Prioritas (P0 today, P1 this week) with code snippets
4. Cara Ukur (metric + where to see it)
5. Status Brief Sebelumnya (✅ closed / ⚠️ partial / ❌ blocked)

Brief sections: Dari/Untuk/Prioritas/Dasar → numbered items (each: Bukti + Dampak + Fix code block + Verifikasi command) → Yang Sudah Benar (do-not-touch list) → Post-deploy verification request.

Write in Indonesian for Adi; keep technical identifiers (URLs, meta tags, code) in English.

## Support files

- `scripts/probe.sh` — runnable curl probe suite; outputs structured findings for steps 1–6. Run before writing the report to avoid hand-typing curls.