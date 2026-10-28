# Next.js Production Bugs: Images and Stale Caches

Three bug classes that look like "the site is broken" and are routinely misdiagnosed. All are
diagnosable in minutes with a probe against the running server, and none should be "fixed"
by weakening a protection.

Probe order that separates them in four curls — run every one on the asset itself before
reading any application code:

```bash
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://<site>/uploads/file.jpg
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "https://<site>/_next/image?url=%2Fuploads%2Ffile.jpg&w=1080&q=75"
```

| direct | optimizer | class |
|---|---|---|
| `200 image/*` | `400 not allowed` | 1 — own-host absolute URL / SSRF guard |
| `200 image/*` | `200 image/*` | healthy — look at the page, not the asset |
| `200 text/html` | `400 isn't a valid image` | 3 — file written to `public/` after boot |

---

## 1. Images render blank although the file is served fine

### Symptom

Cover/hero images are empty boxes on the list page and the detail page. The raw asset returns
`200 image/jpeg` when requested directly.

### Diagnose: probe the optimizer, not the file

`next/image` does not request your asset directly — it proxies every image through
`/_next/image?url=...&w=...&q=...`. Probe that endpoint:

```bash
# 1. asset itself — usually already fine
curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" \
  https://<site>/uploads/cover.jpg

# 2. optimizer with the URL the page actually emits
curl -s "https://<site>/_next/image?url=https%3A%2F%2F<site>%2Fuploads%2Fcover.jpg&w=640&q=75"
# -> "url" parameter is not allowed

# 3. bypass the reverse proxy to prove whether it is nginx or the app
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:3000/_next/image?url=...&w=640&q=75"
```

Also read what the page emits — `src`, `srcSet`, and the encoded `url=` value:

```bash
curl -s https://<site>/ | grep -oE '<img[^>]*>' | head -1
curl -s https://<site>/ | grep -oE 'srcSet="[^"]{0,300}' | head -3
```

### Root cause

An absolute URL pointing back at the deployment's own hostname. The optimizer fetches image
URLs **server-side**; `<site>` resolves to the server's own address (public IP that is local to
the box, or a private/NAT address). Next.js 16 guards this as SSRF and rejects with
`400 "url parameter is not allowed"` — see `fetchExternalImage()` in
`node_modules/next/dist/server/image-optimizer.js`, which rejects when the hostname resolves to
any private IP.

Any of these also produce the same message: hostname resolves to `127.0.0.1`, `10.x`, or the
box's own public IP; or `images.remotePatterns` does not list the hostname.

### Fix: store and render root-relative paths

1. Persist `/uploads/file.ext`, never `https://<own-host>/uploads/file.ext`.
2. Normalise at the data boundary so legacy rows and future ingest both behave. A small helper
   that rewrites own-host absolute URLs under your asset prefixes to their pathname, plus a zod
   transform in the validators so new writes are converted on the way in:

```ts
// absolute own-host asset URL -> root-relative path; anything else untouched
export function normalizeImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("/")) return url;                       // already relative
  let parsed: URL;
  try { parsed = new URL(url); } catch { return url; }
  const own = process.env.NEXT_PUBLIC_SITE_URL
    ? new URL(process.env.NEXT_PUBLIC_SITE_URL).hostname.toLowerCase()
    : null;
  const localPrefix = ["/uploads/", "/media/", "/images/"].some(p => parsed.pathname.startsWith(p));
  return parsed.hostname.toLowerCase() === own && localPrefix ? parsed.pathname : url;
}
```

3. Apply it in the query mapper (so every consumer gets clean data) **and** in the input
   validators (so new rows are stored clean), not only in the component.
4. Metadata is the exception: OpenGraph, Twitter cards and JSON-LD require fully qualified URLs.
   Keep an inverse helper (`toAbsoluteUrl`) and use it only there. A relative path in JSON-LD
   `image` is invalid structured data.
5. Migrate existing rows:

```sql
UPDATE articles
SET featured_image_url = regexp_replace(featured_image_url, '^https?://[^/]+/uploads/', '/uploads/')
WHERE featured_image_url ~ '^https?://[^/]+/uploads/';
```

### What NOT to do

- Do **not** set `images.dangerouslyAllowLocalIP = true` to silence it — that disables the SSRF
guard for every image and you are back to blank images the moment a hostname or IP changes.
- Do **not** swap `next/image` for a raw `<img>` as the fix. It hides the real problem and loses
  responsive `srcSet` plus the lint rule that catches it. Acceptable only as an emergency stopgap
  with an explicit follow-up.
- Do **not** chase nginx. If the app returns the same 400 when you hit `127.0.0.1:3000` directly,
  the proxy is innocent.

---

## 2. New content 404s while the list page shows it

### Symptom

The homepage lists an article, but clicking it returns the site's not-found page. Because the
not-found page is rendered by `notFound()`, the HTTP status can still be `200` — a soft 404 that
looks fine to uptime checks.

### Diagnose

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://<site>/<category>/<slug>"
curl -s "https://<site>/<category>/<slug>" | grep -oE '<title>[^<]*</title>' | head -1
# <title>Artikel Tidak Ditemukan...</title>  -> the query returned null, not a routing error

curl -s "https://<site>/<category>/<slug>" | grep -c 'NEXT_HTTP_ERROR_FALLBACK'   # >0 confirms notFound()
```

Then read the query: if it is wrapped in `"use cache"` + `cacheLife(...)`, the result — including
`null` — is cached per key. A cache populated while the table was empty (a fresh install, or
right after a content purge) keeps returning `null` for that slug for the whole TTL.

A list page can look healthy at the same time because it uses a shorter `cacheLife` and
re-populated itself first. **"Lists work, details 404" is the signature of a stale cache, not a
broken query.** Confirm by checking that no mutation path calls `revalidatePath`/`revalidateTag`.

### Fix: revalidate on every write path

Every code path that inserts/updates/deletes content must invalidate the public pages that
read it — not just the admin UI. In practice that is the integration/ingest API *and* the admin
server actions:

```ts
revalidatePath("/");
revalidatePath("/rss.xml");
if (status === "published") {
  if (categorySlug) revalidatePath(`/${categorySlug}`);
  revalidatePath(`/${categorySlug ?? "artikel"}/${slug}`);
  revalidatePath("/sitemap.xml");
  revalidatePath("/news-sitemap.xml");
}
```

Cover create, update, **autosave**, status change and delete. Then restart the service so the
previously cached `null` entries are dropped.

### Derive the path from the data, never guess it

`revalidatePath` fails silently on a path that does not correspond to a real route: it returns
without error and clears nothing that matters. The single most common way this fix is written
wrong is assuming the article route is `/artikel/<slug>` when the file is
`app/[category]/[slug]/page.tsx` and the live URL is `/indonesia/<slug>`. `/artikel/<slug>`
still *renders* — it falls into the same dynamic segment — so the page looks fine and the bug
survives: every read misses the cache entry that was never cleared.

Symptom that identifies this specific mistake: **new articles appear immediately, but edits to
existing articles never do.** The create path revalidated `/` (which is enough for the list), while
the detail path stayed stale for its whole `cacheLife`.

Rules:

- Resolve the category slug from the foreign key (`SELECT slug FROM categories WHERE id = …`) —
  admin forms usually post a UUID, not a slug, so the path is not available in the payload.
- Revalidate both the canonical path and, when slug or category changed, the **previous**
  path too. Otherwise an old URL serves a ghost copy of the record.
- Prefer one exported helper (`revalidateArticle(article, {previousSlug, previousCategorySlug})`)
  that every mutation path calls, over copy-pasted `revalidatePath` blocks. A per-call-site
  block is how autosave gets missed.
- Also revalidate the route that serves the file's own cache when you change an image:
  `revalidatePath("/_next/image/")` busts the optimizer's stored variants for a replaced cover.

### Prove the invalidation with the real mutation path

A DB write plus a revalidate called from a standalone script proves nothing —
`revalidatePath` throws `Invariant: static generation store missing` outside a request scope.
Drive the actual server action:

1. Mint a short-lived session JWT locally from the app's own `SESSION_SECRET` (never read or print
   a password), then POST to the edit route with headers
   `Next-Action: <action-id>` and `Cookie: <session-cookie>=<jwt>`, body `JSON.stringify([...args])`.
2. Get the action id from `.next/server/server-reference-manifest.json` by matching the exported
   action name.
3. Assert on the public URL before and after — the title/content must change on the very next
   request, not after a TTL wait.
4. Restore the original values and re-trigger the same action so the probe value is purged from
   both DB and cache. Leaving `VERIFY …` strings in production is a self-inflicted incident.

Expected proof looks like:

```
before          : 200 | <original title>
action HTTP     : 200
after edit      : 200 | <new title>        <- changed immediately
```

### Rule for new code

Any query using `"use cache"`/`cacheLife` needs a named, known mutation path that revalidates
it. If you cannot point at the `revalidatePath` for a cached query, the cache will eventually
serve a record that does not exist — this is not hypothetical, it is the default outcome.

Enumerate the layers before blaming one. A stale page can come from four different places, and
`Cache-Control` tells you which ones are ruled out:

```bash
curl -sI "https://<site>/<category>/<slug>" | grep -iE 'cache-control|age|x-nextjs'
```

| Layer | Owned by | Cleared by |
|---|---|---|
| Route/segment cache | Next.js `"use cache"` + `cacheLife` | `revalidatePath` / `revalidateTag` |
| Static/prerender output | build + ISR | revalidate, or rebuild for pure-static routes |
| Image optimizer | `/_next/image` stored variants | `revalidatePath("/_next/image/")` |
| Browser / CDN | headers | `no-store` rules the browser out; a CDN needs its own purge, `revalidatePath` will not touch it |

`Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate` proves the browser is
not the culprit — say that explicitly to the user instead of telling them to hard-refresh, which
is the reflexive and usually wrong first answer.

---

## 3. A newly uploaded file serves the HTML 404 page instead of the image

### Symptom

Upload "succeeds" in the admin UI — no error, the URL field fills with `/uploads/<uuid>.jpg`,
and the file really is on disk with the right bytes. But the preview never appears: the `<img>`
exists with `naturalWidth: 0`, and the public article page shows no cover. Images that shipped
with an earlier build work perfectly, which is what makes this look like a data problem.

### Diagnose: check the content type of the asset, not its existence

The asset returns **`200 text/html`** — the app's own not-found page — and the optimizer then
rejects it with `400 The requested resource isn't a valid image.`

```bash
U=/uploads/<uuid>.jpg
curl -s -o /dev/null -w "direct : %{http_code} %{content_type}\n" "https://<site>$U"
curl -s -o /dev/null -w "optimiz: %{http_code} %{content_type}\n" \
  "https://<site>/_next/image?url=%2Fuploads%2F<uuid>.jpg&w=1080&q=75"
curl -s "https://<site>$U" | grep -oE '<title>[^<]*</title>'
```

Compare headers of a **working** asset and a **broken** one — the difference is unmistakable and
is the proof the rest of the investigation hangs on. A static hit carries `Content-Type`, `ETag`,
`Last-Modified`, `Accept-Ranges`. A broken one carries `x-nextjs-prerender`, `Vary: rsc, …`, font
`link:` preloads and `Cache-Control: private, no-cache, no-store` — i.e. the app router rendered
a PAGE:

```bash
curl -sI "https://<site>/uploads/<known-good>.jpg" | head -8
curl -sI "https://<site>/uploads/<newly-uploaded>.jpg" | head -8
```

### Root cause

Next.js builds its static-file manifest by walking `public/` **once, when the production server
starts** — `publicFolderItems` in
`node_modules/next/dist/server/lib/router-utils/filesystem.js`. A file written into `public/`
*after* startup is not in that set, so the filesystem router never matches it and the request
falls through to the app router, which renders the not-found page.

The discriminating evidence is **when each file entered the disk**, not anything about the file:
a file uploaded before the last `next build` works; the same file uploaded after `next start`
returns HTML. This is also why the bug never reproduces in `npm run dev`: the dev server reads
`public/` dynamically, while `next start` uses the boot-time manifest.

Grep the framework source for the guard rather than theorising:

```bash
grep -n 'publicFolderItems' node_modules/next/dist/server/lib/router-utils/filesystem.js
```

### Fix: write runtime media outside `public/` and serve it from a route handler

1. Store uploads in a directory outside `public/` (e.g. `storage/uploads`), gitignored — it is
   runtime data, not source.
2. Add a route handler that streams those bytes with the correct content type. Because it is a
   dynamic route, new files are available immediately with no rebuild or restart:

```ts
// src/app/uploads/[...path]/route.ts
const CONTENT_TYPES: Record<string, string> = {
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
  ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif",
};
const SAFE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;   // flat names only: no /, no ..

export async function GET(_r: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: segments } = await params;
  if (segments?.length !== 1) return new NextResponse("Not found", { status: 404 });
  const filename = decodeURIComponent(segments[0]);
  if (!SAFE_NAME.test(filename)) return new NextResponse("Not found", { status: 404 });
  const type = CONTENT_TYPES[path.extname(filename).toLowerCase()];
  if (!type) return new NextResponse("Not found", { status: 404 });

  const resolved = path.resolve(path.join(UPLOADS_ROOT, filename));
  if (!resolved.startsWith(path.resolve(UPLOADS_ROOT) + path.sep))
    return new NextResponse("Not found", { status: 404 });

  const info = await stat(resolved).catch(() => null);
  if (!info?.isFile()) return new NextResponse("Not found", { status: 404 });
  return new NextResponse(new Uint8Array(await readFile(resolved)), {
    headers: { "Content-Type": type, "Content-Length": String(info.size),
               "Cache-Control": "public, max-age=31536000, immutable",
               "X-Content-Type-Options": "nosniff" },
  });
}
```

3. Point the upload action at the new root but **keep the public URL `/uploads/<file>`** — then no
   existing database row changes and no article needs re-saving.
4. Migrate the existing files (`cp`), leave `public/uploads/` empty, and gitignore the new root.
5. Keep `/uploads` excluded from middleware matchers so CSP headers do not attach to the handler.

### Prove the fix by writing a file AFTER the server is running

Testing a file that predates the restart proves nothing — that is the case that already worked.
The regression test is: start the server, *then* drop a new file in, *then* request it.

```bash
NEW=runtime-$(date +%s).jpg
cp storage/uploads/<known-good>.jpg "storage/uploads/$NEW"
curl -s -o /dev/null -w "direct : %{http_code} %{content_type}\n" "https://<site>/uploads/$NEW"
curl -s -o /dev/null -w "optimiz: %{http_code} %{content_type}\n" \
  "https://<site>/_next/image?url=%2Fuploads%2F$NEW&w=1080&q=75"
rm -f "storage/uploads/$NEW"
```

Expect `200 image/jpeg` on both. Also assert the traversal guards still 404 —
`../`, `%2e%2e%2f`, `.env.local`, and non-image extensions — and confirm no file body leaks.

### What NOT to do

- Do **not** "just restart the service" as the fix. It makes the currently-uploaded files appear,
  which reads as a success, and the next upload breaks again. Restart is a symptom mask here.
- Do **not** move to `next start` with a rebuild per upload, or disable `next/image`.
- Do not conclude the upload failed. It usually succeeded — check the bytes on disk before
  blaming the upload path. A file present on disk that the server will not serve is this bug.

---

## 4. Internal editorial fields leaking onto the public page

### Symptom

Every article that has ever been edited shows a prominent warning box to readers ("Koreksi",
"Correction", a red alert) whose body is an internal note — a save marker, a reviewer name, an
audit string. Sometimes it is an internal memo rendering as if it were a published correction.

### Root cause

An audit field is being read straight into a public view model. The usual pairing:

- a mutation path writes a generic internal note on **every save** (e.g.
  `changeNote: "Revision sebelum update oleh ${session.name}"`), and
- the public query selects the *latest* note with no filter, mapping it into a field like
  `correctionNote`
- which the body component renders whenever it is non-null.

The feature was never meant to fire. It is a leak, not a styling bug.

### Diagnose: read the actual values, not the component

```bash
psql "$DATABASE_URL" -c "select left(r.change_note,60), r.created_at, a.slug
  from article_revisions r join articles a on a.id = r.article_id
  where r.change_note is not null order by r.created_at desc limit 10;"
```

Then confirm it reaches readers:

```bash
curl -s "https://<site>/<category>/<slug>" | grep -oE 'Koreksi|Revision sebelum update[^<"]{0,40}'
```

If the internal string appears in the HTML, the leak is in the query, not the component.

### Fix at the data boundary, not by deleting the component

Filter the internal marker in the query so the field can still carry a *real* public correction
the same day someone writes one:

```sql
AND ${articleRevisions.changeNote} NOT ILIKE 'Revision sebelum update%'
AND length(trim(${articleRevisions.changeNote})) > 0
```

Why not just remove the alert from `ArticleBody`:

- the audit history stays intact — no rows deleted, versions preserved for internal use;
- the legitimate correction feature survives (a real correction note still renders);
- deleting the component throws away a feature the newsroom will want for retractions.

### Verify across every article, not the one reported

Loop all published URLs and assert the alert count is `0` on each, then assert the article itself
still renders (`200`, correct `<title>`, body container present). Fixing one slug and declaring it
done misses articles whose revisions took a different path.

### Rules

- **An audit/log field is never a public field.** If a view model maps an internal column, the
  query must whitelist what may surface, not blacklist what must not — or better, use a separate
  column (e.g. `articles.correction_note`) that only the editorial form can write.
- A string marker shared between the writer (`adminUpdate*`) and the reader (public query) is an
  implicit contract. Changing the marker text in one place silently re-enables the leak — note it
  in the code comment at both ends.
- Before hiding anything in the UI, check whether the data should have reached the component at
  all. UI-level hiding leaves the leak in every other consumer (feeds, JSON-LD, API responses).

---

## Verification discipline

Probe the real deployment, not the build output. For each fix, capture before/after literal
results (status code, content type, byte size) for: the asset itself, the optimizer endpoint,
the list page, the detail page, and sitemap/JSON-LD. "Build succeeded" is not evidence that a
runtime content bug is fixed.
