# What each tool can and cannot judge

Tag every practical-skill judgement as **M** (measured by a tool) or **I** (inferred by a model, an
opinion). When nothing can judge something, say so. Don't pad feedback to hide it: the owner will
notice and discount everything else.

| Source | Can judge | Cannot judge |
| --- | --- | --- |
| **MIDI** (silent piano) | Exact notes, onsets, durations, velocity, pedal if sent; wrong, missed and extra notes; hesitations; drift | Acoustic tone, posture, tension, musicality. Velocity is not calibrated loudness. |
| **librosa pYIN / onsets** (a transcription script; not included) | Pitch of one isolated voice or line, including bends and vibrato; onset timing; level | Voice and guitar mixed together; chords; timbre; breath; diction; "healthy" technique. Its octave and bend heuristics were tuned on guitar lines. |
| **Voice stats** (a voice-analysis script; not included) | Overall pitch range, level, silence ratio | Phrasing, diction, expression |
| **Claude, Codex, DeepSeek** (text) | Structure and content of transcripts, roleplay and written explanations; interpreting the measured reports | Anything audible or visible. They do not hear audio here. |
| **Vision model on video frames** | Gross posture, hand position, visible strumming pattern, from stills | Tension, subtle motion, timing |
| **Gemini 4 Argon** (not subscribed) | Plausibly tone, phrasing, delivery and posture from audio or video. An opinion (I), uncalibrated. | Anything it cannot timestamp. It is no substitute for a human teacher on technique or health. |

librosa reads phone `.m4a` through ffmpeg.

## When to add Gemini

Add it only after a real session where the measured report and the owner's blind A/B could not answer
"which take is better, and why?" Then:

1. **Validate it.** The owner labels 5–10 clips (better or worse, and the reason). Gemini must
   reproduce those judgements with timestamps and may abstain. If it can't, stop.
2. **Use it as a second opinion,** tagged I, never as the grade.

Occasional lessons with a human teacher are still the right check for vocal technique.
