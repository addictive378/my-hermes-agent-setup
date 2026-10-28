---
name: remotion-video
version: 1.0.0
author: Hermes Agent
license: MIT
description: "Use when building Remotion videos. Render and verify."
tags: [video, remotion, react, rendering, programmatic-video]
metadata:
  hermes:
    tags: [video, remotion, react, rendering, programmatic-video]
    related_skills: []
---

# Remotion Video Production

## When to Use

- User asks for a video produced with Remotion, or the `videomaker` profile is active.
- Setting up or troubleshooting a Remotion project on this machine.
- Rendering, verifying, or debugging a Remotion composition.

Build and render videos programmatically with Remotion. The user's team uses this for 1-minute social-media content produced by the `videomaker` profile.

## Project layout

The workspace is `~/video-studio/`. The videomaker profile's `terminal.cwd` points there. Structure:

```
src/
├── types.ts            # VideoSpec type (what gets edited)
├── specs/<name>.ts     # one spec file per video — edit THIS, not components
├── OneMinuteVideo.tsx  # main composition component
├── Root.tsx            # registers all compositions
└── index.ts            # entry point
out/                    # rendered MP4 / stills
```

The pattern is **data-driven**: content lives in a typed data object (`VideoSpec`) in `src/specs/*.ts`; the React component consumes it. When producing a new video, copy a spec file and register a new `<Composition>` — do not rewrite the component.

## Scaffold a new project

```bash
npx --yes create-video@latest --yes --blank <dir>
```

**Pitfall:** omitting `--yes` drops the tool into an interactive template picker that hangs forever in a non-TTY shell (cron, backgrounded terminal, subagent). Always pass `--yes --blank` (or another explicit template flag) when invoking programmatically.

## System dependencies for headless rendering

Remotion renders via Chrome Headless Shell. On a bare Linux host without a desktop, install these before first render:

```bash
sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0 libx11-xcb1 fonts-liberation
```

Verify with `ldd <path-to-chrome-binary> | grep 'not found'` — empty output means ready. Without these libs, Remotion and any bundled Chromium binary fail silently or exit early.

## Verification ladder

Never trust a single successful render as proof of a working pipeline. Verify in order:

1. **Still image** at a mid-frame: `npx remotion still <CompId> out/test.jpg --frame=<mid>` — confirms bundling, font rendering, layout, and that no text is clipped.
2. **Short segment** (e.g. `--frames=0-89` for 3 seconds): `npx remotion render <CompId> out/test.mp4 --frames=0-89 --codec h264` — confirms the encoding pipeline works end to end.
3. **Full render** (run in background with notify): `npx remotion render <CompId> out/final.mp4 --codec h264` — verify final duration and resolution with ffprobe.

Use `vision_analyze` on the still to confirm layout, readability, and absence of clipping before committing to a full render. A text-first agent cannot otherwise detect visual regressions.

After each render, run:

```bash
ffprobe -v error -show_entries format=duration,size:stream=width,height,r_frame_rate -of json out/<file>.mp4
```

Confirm the reported duration matches the expected frame count / fps.

## Compositions

Register every output variant as a separate `<Composition>` in `src/Root.tsx` with its own id, dimensions, and `defaultProps={{ spec }}`. Standard set for 1-minute content:

| ID | Size | Platform |
|---|---|---|
| `OneMinute-Vertical` | 1080×1920 | Shorts, Reels, TikTok |
| `OneMinute-Horizontal` | 1920×1080 | YouTube, web |
| `OneMinute-Square` | 1080×1080 | IG feed, LinkedIn |

All share the same component; only dimensions differ. The component reads timing from the spec (hookSeconds, outroSeconds) and distributes body-scene frames automatically.

## Useful commands

```bash
npm run list                          # npx remotion compositions
npm run render:vertical               # → out/video-vertical.mp4
npm run render:horizontal
npm run render:square
npm run still                         # thumbnail at frame 60
npx remotion render <ID> out/x.mp4 --frames=0-299   # quick check (10s)
npx remotion studio --port 3000       # interactive preview (needs port access)
```

For long renders, use `terminal(background=true, notify=true)` so the turn can continue while rendering proceeds.

## Resource expectations

On a small server (2 vCPU, ~3–4 GB RAM), a full 1800-frame (60 s @ 30 fps) 1080p render takes several minutes. Always run the short-segment check first. Full renders should be backgrounded.

## License

Remotion is free for individuals and teams of up to three people. Companies with more than three employees need a paid license. Flag this if the user's organization grows past three.

## Pitfalls

- Do not edit React components to change video content — edit the spec data file instead. Components are shared across all videos; editing them breaks every other video.
- Do not assume `remotion studio` is usable on a headless server — it needs browser access to a port. Use stills and short segments for QA.
- Do not skip the still-image verification step — layout bugs (text clipping, overlap, wrong contrast) are invisible in logs but obvious in a rendered frame.
- Do not commit a full-length render until the short-segment test passes — a typo in a scene wastes minutes of render time.
- Do not claim a render succeeded from the process exit code alone — verify the output file exists, has nonzero size, and reports the expected duration via ffprobe.
- Text length is a hard layout constraint: headings beyond roughly 64 characters and body text beyond roughly 150 characters overflow the frame at the current font sizes. Keep spec copy within those bounds or reduce font size deliberately.
