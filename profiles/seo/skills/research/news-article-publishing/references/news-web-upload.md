# news-web upload: helper, payload fields, DB checks

## Integration behaviour worth knowing

- `POST /api/integrations/hermes/articles`, `Authorization: Bearer $HERMES_API_KEY`,
  `schema_version: "1.0"`, body limit 256 KB.
- Response codes: `201 created`, `200 duplicate` (same key + same payload hash),
  `401`, `409 IDEMPOTENCY_CONFLICT`, `413`, `422 VALIDATION_ERROR` (with an `issues` array
  naming the offending path — read it, it tells you exactly which field broke).
- The payload hash is computed over the **whole** payload. Any field you regenerate per
  attempt (`publication_context_time`, `event_time`, a timestamp in `slug`) changes the hash,
  so a retry of the same key conflicts instead of deduplicating.
- Slug collisions are auto-suffixed with a base36 timestamp and reported in `warnings`.
- HTML is sanitised server-side (DOMPurify); `script`/`style`/`iframe`/event handlers are
  stripped, so do not rely on embedded widgets.
- Sources are stored as rows and linked; warnings about missing publisher / private URL /
  invalid date come back in the response and are also visible in the admin CMS.

## Reusable upload helper

```python
import json, subprocess

ENV = "/home/ubuntu/news-web/.env.local"
env = {}
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

BASE = env.get("NEXT_PUBLIC_SITE_URL", "http://localhost:3000").rstrip("/")

def post(payload):
    r = subprocess.run(
        ["curl", "-sS", "-w", "\n%{http_code}", "-X", "POST",
         BASE + "/api/integrations/hermes/articles",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {env['HERMES_API_KEY']}",
         "--data-binary", "@-"],
        input=json.dumps(payload, ensure_ascii=False).encode(), capture_output=True)
    out = r.stdout.decode("utf-8", "replace")
    code = out.rsplit("\n", 1)[-1].strip()
    body = json.loads(out.rsplit("\n", 1)[0])
    return code, body
```

Write one small script per article under the scratch dir and run it with `python3`; keep the
payload in the script so re-runs are reproducible. Assert lengths before posting (title ≤300,
slug ≤190, `seo_title` ≤70, `seo_description` ≤160, summary ≤1000) so a 422 never costs a round
trip.

## Payload fields actually used

`schema_version`, `title`, `slug`, `summary`, `body`, `content_format: "html"`,
`category_slug`, `tag_slugs[]`, `author_slug`, `language: "id"`, `event_time`,
`publication_context_time`, `sources[{title,url,publisher,publishedDate,accessedDate}]`,
`seo_title`, `seo_description`, `reading_time`, `editorial_notes[{type,content}]`
(types used: `context`, `limitation`, `verification`, `disclosure`),
`research_warnings[{severity,message}]` (`info` | `warning` | `critical`),
`disclosure_text`, `requested_status`, `idempotency_key`.

`editorial_notes` types and `research_warnings` severities are free-form enough that the admin
UI renders them by label — keep the vocabulary consistent across a batch.

## Known-good reference values

Categories: `indonesia`, `politik`, `bisnis`, `internasional`, `olahraga`, `sains`,
`teknologi`, `opini`.

Authors: `budi-santoso`, `dewi-anggraini`, `rizal-pratama`, `siti-nurhaliza`.

Always re-query — these are seeded rows, not a guarantee:

```bash
psql "$DBURL" -c "select slug from categories order by slug;"
psql "$DBURL" -c "select slug from authors order by slug;"
```

## Post-upload DB checks

```sql
-- per-article integrity
select a.slug, a.status, length(a.body) body_len, c.slug cat,
       (select count(*) from article_sources s
          join articles_to_sources ats on ats.source_id = s.id
         where ats.article_id = a.id) srcs,
       (select count(*) from articles_to_tags t where t.article_id = a.id) tags
  from articles a left join categories c on c.id = a.category_id
 order by a.created_at desc limit 10;

-- SEO budgets
select seo_title, length(seo_title), length(seo_description) from articles
 order by created_at desc limit 10;

-- idempotency trail (did a retry actually land?)
select idempotency_key, article_id, created_at from integration_imports
 order by created_at desc limit 10;
```

Run these **before** re-posting anything. An orphan `integration_imports` row with no live
article is the only case where re-using the same key is legitimate (the API allows re-import
when the article row is gone).

## Health check

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://wartanusaku.site/
curl -sS https://wartanusaku.site/api/health
```
