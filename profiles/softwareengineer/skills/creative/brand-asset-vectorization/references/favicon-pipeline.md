# Favicon & icon pipeline (sharp + Next.js app router)

Generating a full icon set from one SVG, with a real multi-resolution `.ico` and a
small-size variant.

Confirm what is installed before pinning anything:

```bash
npm ls sharp          # pin devDependencies to the version npm actually resolved
npm i -D sharp        # only if genuinely absent
```

## Next.js app-router file conventions

Place these under `src/app/` (or `app/`) and Next.js wires them automatically:

| File | Served as | Notes |
|---|---|---|
| `icon.svg` | `/icon.svg` | preferred icon; also declarable in `metadata.icons` |
| `favicon.ico` | `/favicon.ico` | multi-resolution, classic fallback |
| `apple-icon.png` | `/apple-icon.png` | 180x180 for iOS |

Both `/icon.svg` and `/apple-icon.png` show up as their own routes in the `next build`
route table — that listing is the proof the convention took.

Declare them explicitly too, so non-Next consumers and social scrapers see them:

```ts
icons: {
  icon: [
    { url: "/icon.svg", type: "image/svg+xml" },
    { url: "/favicon.ico", sizes: "any" },
  ],
  apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
},
openGraph: {
  siteName: siteConfig.name,
  type: "website",
  locale: "id_ID",
  images: [{ url: "/logo.png", width: 512, height: 512, alt: siteConfig.name }],
},
```

Keep a 512x512 `public/logo.png` even when the page uses SVG: structured data
(`NewsMediaOrganization.logo`, `Organization.logo`) expects a raster URL and several
crawlers reject SVG there.

## Generator script skeleton

```js
import sharp from "sharp";
import { writeFile } from "node:fs/promises";

const png = (svg, size) =>
  sharp(Buffer.from(svg)).resize(size, size).png({ compressionLevel: 9 }).toBuffer();

/** Minimal ICO container holding PNG payloads — accepted by all modern browsers. */
function buildIco(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);            // reserved
  header.writeUInt16LE(1, 2);            // type: icon
  header.writeUInt16LE(images.length, 4);
  let offset = 6 + images.length * 16;
  const entries = images.map(({ size, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(size >= 256 ? 0 : size, 0);   // width
    e.writeUInt8(size >= 256 ? 0 : size, 1);   // height
    e.writeUInt8(0, 2);                        // palette
    e.writeUInt8(0, 3);                        // reserved
    e.writeUInt16LE(1, 4);                     // colour planes
    e.writeUInt16LE(32, 6);                    // bits per pixel
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([header, ...entries, ...images.map(i => i.data)]);
}

await writeFile("src/app/favicon.ico", buildIco([
  { size: 16, data: await png(smallSvg, 16) },
  { size: 32, data: await png(smallSvg, 32) },
  { size: 48, data: await png(smallSvg, 48) },
]));
await writeFile("public/logo.png", await png(fullSvg, 512));
```

Expose it as an npm script (`"assets:brand": "node scripts/generate-favicons.mjs"`) so it
is re-runnable after any artwork tweak. Run it twice to confirm determinism.

## Verifying the icons actually serve

Run the production build on a **spare port** before touching the live service; start it as
a tracked background process, never with `nohup`/`&` wrappers.

```bash
npx next start -p 3100 -H 127.0.0.1
```

```bash
for u in /icon.svg /favicon.ico /apple-icon.png /logo.png; do
  printf "%-18s " "$u"
  curl -s -o /dev/null -w "http=%{http_code} type=%{content_type} bytes=%{size_download}\n" \
    "http://127.0.0.1:3100$u"
done
```

Expect `image/svg+xml`, `image/x-icon`, `image/png`. Then confirm the tags reached the HTML:

```bash
curl -s http://127.0.0.1:3100/ | grep -oE '<link[^>]*(icon|apple)[^>]*>'
```

...and that the DOM holds the real brand colours (not what a thumbnail suggests):

```js
[...document.querySelectorAll('header a[href="/"] svg path')]
  .map(p => getComputedStyle(p).stroke)
```

Only after those pass: rebuild, restart the real service, then re-probe **through the public
HTTPS URL** (nginx + TLS), not just localhost.

## Regression check when the repo has e2e tests

If a Playwright suite exists, run it against the staging port before deploying. Make
`baseURL` env-overridable so you never edit the config to test a branch:

```ts
baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
```

Then:

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 npx playwright test --reporter=line
```

Run the same suite against the **untouched** production build to classify failures. If the
same tests fail there too, they are pre-existing and not yours to fix in this change — say
so explicitly rather than silently absorbing them. Add `/test-results` and
`/playwright-report` to `.gitignore`; they are run artifacts, not source.
