#!/usr/bin/env python
r"""Record a take from a MIDI input (the silent piano over USB) into a .mid file.

Unverified until the piano is connected: the first practical session checks the port name and that
a take round-trips through midi_compare.py.

Recording starts at the first note, so waiting at the keys costs nothing, and stops after
--silence seconds without input (or Ctrl+C). Needs `pip install mido python-rtmidi`; the analysis
script does not.

  python midi_capture.py --list
  python midi_capture.py --out $LEARN_HOME/recordings/piano/2026-10-30-take1.mid [--port "..."] [--silence 4]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--port", help="input name or a unique substring; default: the only input")
    p.add_argument("--out", type=Path)
    p.add_argument("--silence", type=float, default=4.0, help="stop after this many seconds without a message")
    a = p.parse_args()
    try:
        import mido
    except ImportError:
        sys.exit("needs: pip install mido python-rtmidi")
    names = mido.get_input_names()
    if a.list or not a.out:
        print("\n".join(names) or "no MIDI inputs found (is the piano connected and on?)")
        return
    matches = [n for n in names if a.port is None or a.port.lower() in n.lower()]
    if len(matches) != 1:
        sys.exit(f"pick one input with --port; found: {names}")

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000))  # 120 bpm: 960 ticks per second
    with mido.open_input(matches[0]) as port:
        print(f"listening on {matches[0]}; play when ready (stops after {a.silence}s of silence)")
        first = last = None
        try:
            while True:
                msg = port.poll()
                now = time.perf_counter()
                if msg is None:
                    if last is not None and now - last > a.silence:
                        break
                    time.sleep(0.001)
                    continue
                if msg.type in ("clock", "active_sensing"):
                    continue
                if first is None:
                    if msg.type != "note_on":
                        continue
                    first = last = now
                track.append(msg.copy(time=round((now - last) * 960)))
                last = now
        except KeyboardInterrupt:
            pass
    if first is None:
        sys.exit("no notes received")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mid.save(a.out)
    print(f"saved {a.out} ({sum(m.type == 'note_on' and m.velocity > 0 for m in track)} notes, {last - first:.1f} s)")


if __name__ == "__main__":
    main()
