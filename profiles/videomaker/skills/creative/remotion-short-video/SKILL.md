---
name: remotion-short-video
version: 1.0.0
author: videomaker
license: MIT
description: Use when producing animated MP4 shorts in ~/video-studio.
metadata:
  hermes:
    tags: [video, remotion, mp4, animation, tts]
    related_skills: [manim-video, youtube-content]
---

## When to Use

- The user asks for a short animated video (Shorts/Reels/TikTok style, ~30–60s) produced as an MP4 with the Remotion project in `~/video-studio`.
- The user asks to add animation, logos, sound effects, music, or voice-over to an existing Remotion video.
- Not for Manim math animations (see manim-video) or for script-only deliverables with no render.

## Pipeline routing (three production paths, pick before building)

- **Remotion (this skill) = default** for 60s Shorts/Reels deliverables: direct MP4 output, deterministic specs, audio-capable (VO + SFX + music), tested end-to-end in this studio.
- **bang-motion** (skill `bang-motion`) for cinematic motion-graphic openers/promos/explainers built as one autoplay `index.html` (HTML+CSS+GSAP). Its MP4 export needs Node + puppeteer (not preinstalled — heavy download); by default deliver the HTML, and say so when proposing it.
- **Higgsfield** (skills `higgsfield-*`, CLI `higgsfield`) for AI-generated ASSETS — stills, video clips, voice/SFX/music, thumbnails, Soul characters — not as a full-video pipeline. Feed its outputs into Remotion via `public/` + `staticFile`, or into a bang-motion project via its `assets/` folder. Generation costs credits; check the plan balance before promising output.
- A brief can combine paths (e.g. Higgsfield VO + Remotion video); name the combination in the plan before producing.

# Remotion Short Video (~50–60s vertical)

Produce spec-driven animated videos in `~/video-studio` (2 vCPU / ~3.6 GB — full renders take minutes; always smoke-test first).

## Procedure

1. **Write the spec** — copy `src/specs/example.ts` → `src/specs/<name>.ts` and fill `VideoSpec` (hook, scenes, cta, palette, `hookSeconds`, `outroSeconds`). Keep heading ≤ ~64 chars and body ≤ ~150 chars per scene or text clips.
2. **Component** — the base `src/OneMinuteVideo.tsx` renders plain fade/slide scenes. For rich animation (spin-in logos, particles, glitch hook, pulsing CTA), create a separate component (see `src/FrameworkVideo.tsx` as template) rather than overwriting the base. Import `staticFile` from `remotion` at the top — a mid-file import compiles but is wrong shape.
3. **Register compositions** in `src/Root.tsx`. Duration is per-composition: frames = seconds × 30. For a 50s video use `durationInFrames={50 * FPS}` — do NOT reuse the 1800-frame `OneMinute-*` compositions for shorter videos. Create one composition per aspect ratio (Vertical 1080×1920, Horizontal 1920×1080, Square 1080×1080).
4. **Verify registration**: `npm run list` must show the new composition with the correct duration (e.g. `1500 (50.00 sec)`).
5. **Smoke-test**: `npx remotion render <ID> out/test.mp4 --frames=0-299`. Only render full after this passes.
6. **Full render**: `npx remotion render <ID> out/<name>.mp4` (foreground, timeout 600). `npm run render:vertical` etc. always render the DEFAULT 60s example compositions — never use the npm shortcuts for a custom composition.
7. **Verify with ffprobe**: check `duration` matches target and an `aac` audio stream exists when audio was intended.
8. Deliver the MP4 via `MEDIA:/home/ubuntu/video-studio/out/<name>.mp4` in the Telegram reply.

## Assets

- **Logos**: `curl -sL -o public/logos/<name>.svg https://cdn.simpleicons.org/<slug>/<hexcolor>` (brand-colored SVGs; react, django, springboot, express, flutter all work). Render via `<Img src={staticFile(...)}>` with a `drop-shadow` glow in the scene's accent color.
- **SFX via ffmpeg** (see `references/audio-pipeline.md` for exact commands): whoosh (filtered pink-noise sweep), pop (short sine blip), chime (sine tones). Convert any mp4 audio to `.wav` — Remotion `<Audio src>` is happiest with wav/mp3.
- **Music bed**: ffmpeg `aevalsrc` synth (A-minor pad + bass pulse, 50s, fade in/out), played at volume ~0.18 under the VO.

## Audio layering (in component)

- `<Audio src={staticFile(...)}>` inside each `<Sequence>` for scene-local SFX; full-length music + VO `<Audio>` tracks at the AbsoluteFill root.
- Voice-over drives the script: write VO text first, measure its duration, then fit the on-screen text to it. Total speech should run ~8s shorter than the video so hook/CTA have breathing room.

## Pitfalls

- **Check which composition a render used** — a background/queued `npm run render:*` that was kicked off before the new composition existed silently produces the 60s example video. Always render the new composition by explicit ID.
- **TTS fallback order for Indonesian VO**: profile TTS (edge) can fail with 403; fall back to Python `gTTS(text, lang="id")` via execute_code — it works and takes seconds. Normalize the result with `ffmpeg loudnorm=I=-16:TP=-1.5:LRA=11`.
- **VO length check before render**: `ffprobe` the generated VO; if it exceeds target minus ~8s, shorten the script and regenerate rather than speeding it up.
- **write_file refuses to overwrite a component it hasn't fully read this session** — for base components, create a new file (e.g. `FrameworkVideo.tsx`) instead of rewriting `OneMinuteVideo.tsx`.
- **Derive scene-exit timing from the actual scene length, never hardcode frame numbers** — an exit fade written as fixed frames (e.g. `interpolate(frame,[200,234])`) only matches one scene count; for a 50s/5-scene layout perScene = 234 frames, but any change to duration or scene count leaves a dead hold before the cut. Compute the fade start from the component's own math (e.g. `fadeStart = perScene - 34`) so the same file survives layout changes.

## references/

- `audio-pipeline.md` — exact ffmpeg commands for SFX, music bed, VO normalization, and the Remotion `<Audio>` wiring.
