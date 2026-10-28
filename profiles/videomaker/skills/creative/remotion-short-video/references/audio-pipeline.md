# Audio Pipeline for Remotion Videos

All paths relative to `~/video-studio/public/`.

## SFX generation (ffmpeg, one command each)

```bash
mkdir -p public/sfx public/vo public/music public/logos
cd public

# Whoosh — filtered pink-noise sweep, 0.3s
ffmpeg -y -f lavfi -i "anoisesrc=d=0.3:c=pink:r=44100" \
  -af "highpass=f=800,lowpass=f=3000,afade=t=in:st=0:d=0.05,afade=t=out:st=0.15:d=0.15,volume=0.3" \
  sfx/whoosh.wav

# Pop — short sine blip, 0.08s (logo entrance)
ffmpeg -y -f lavfi -i "sine=frequency=600:duration=0.08" \
  -af "afade=t=out:st=0.02:d=0.06,volume=0.4" sfx/pop.wav

# Chime — two sine tones, 0.15s + 0.2s (CTA)
ffmpeg -y -f lavfi -i "sine=frequency=880:duration=0.15" sfx/chime1.wav
ffmpeg -y -f lavfi -i "sine=frequency=1320:duration=0.2" sfx/chime2.wav
```

If a source is .mp4, convert to .wav first: `ffmpeg -y -i sfx/x.mp4 sfx/x.wav`.

## Voice-over (Indonesian)

1. Generate with gTTS via execute_code (edge TTS may 403):

```python
from gtts import gTTS
tts = gTTS(text=<script>, lang="id", slow=False)
tts.save("public/vo/<name>-vo.mp3")
```

2. Check length: `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 public/vo/<name>-vo.mp3`
   Target: video length minus ~8s. Too long → shorten script, regenerate.
3. Normalize:

```bash
ffmpeg -y -i vo/<name>-vo.mp3 -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ar 44100 vo/<name>-vo.wav
```

## Music bed (50s ambient synth, A-minor pad + bass pulse)

```bash
ffmpeg -y -f lavfi -i "aevalsrc=exprs='0.16*(sin(2*PI*110*t)+0.6*sin(2*PI*164.81*t)+0.4*sin(2*PI*261.63*t))*sin(2*PI*0.125*t)^2 + 0.20*sin(2*PI*55*t)*pow(1-mod(t*2\\,1)\\,6) + 0.06*(random(0)-0.5)*pow(1-mod(t*2\\,1)\\,24)':s=44100:d=50" \
  -af "lowpass=f=4500,afade=t=in:d=1.5,afade=t=out:st=46:d=4" -ac 2 music/<name>-music.wav
```

Adjust `d=50` and the `st=46` fade-out start to the video length.

## Wiring in the component

```tsx
import { Audio, staticFile } from "remotion";

// Inside each scene <Sequence>: scene-local SFX
<Audio src={staticFile("/sfx/whoosh.wav")} volume={0.6} />

// At the AbsoluteFill root: full-length beds
<Audio src={staticFile("/music/<name>-music.wav")} volume={0.18} />
<Audio src={staticFile("/vo/<name>-vo.wav")} volume={1.0} />
```

Mix levels: music ~0.18, SFX 0.3–0.6, VO 1.0. `<Audio>` inside a Sequence starts when the Sequence starts.
