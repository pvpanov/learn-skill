#!/usr/bin/env python
r"""Compare a performed MIDI take against a reference and say where it went wrong.

The reference is whatever the owner is aiming at: a score exported to MIDI, or an earlier clean take.
The report answers the questions chunked practice needs — which notes were wrong, missed or added,
where the take hesitated, whether the tempo drifted, and which bars are worst — so the next attempt
can target one weakness instead of replaying the whole piece.

Why align instead of comparing note by note: one missed note would shift every later comparison.
Notes struck together (within --chord-ms) form one event; event sequences are aligned with an edit
distance, so a wrong, missing or extra note costs one local error.

Why timing is relative: a slower take is not a mistake. A straight line is fitted through the
matched onsets (performance time against reference time); its slope is the overall tempo ratio and
the residuals are timing deviations. Small residuals are expression, not error, so only deviations
beyond --timing-ms are listed, and a gap far longer than the reference's is reported as a hesitation.

Stdlib only: reads Standard MIDI Files directly, so no mido is needed to analyse a recording.

  python midi_compare.py --ref piece.mid --take take.mid [--from-bar 1 --to-bar 8] [--json out.json]
  python midi_compare.py --selftest
"""
from __future__ import annotations

import argparse
import json
import statistics
import struct
import sys
from pathlib import Path


# ---------- reading SMF ----------

def read_varlen(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    while True:
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, i


def read_midi(path: Path) -> dict:
    """Notes as {pitch, start (s), beat, velocity} plus the time signature numerator."""
    data = path.read_bytes()
    if data[:4] != b"MThd":
        sys.exit(f"{path}: not a Standard MIDI File")
    _, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        sys.exit(f"{path}: SMPTE time division is not supported")
    i = 8 + struct.unpack(">I", data[4:8])[0]
    events = []  # (tick, kind, payload)
    for _ in range(ntracks):
        assert data[i:i + 4] == b"MTrk", "bad track header"
        length = struct.unpack(">I", data[i + 4:i + 8])[0]
        j, end, tick, status = i + 8, i + 8 + length, 0, 0
        while j < end:
            delta, j = read_varlen(data, j)
            tick += delta
            b = data[j]
            if b == 0xFF:
                mtype, (mlen, j) = data[j + 1], read_varlen(data, j + 2)
                payload = data[j:j + mlen]
                j += mlen
                if mtype == 0x51:
                    events.append((tick, "tempo", int.from_bytes(payload, "big")))
                elif mtype == 0x58:
                    events.append((tick, "timesig", payload[0]))
                continue
            if b in (0xF0, 0xF7):
                slen, j = read_varlen(data, j + 1)
                j += slen
                continue
            if b & 0x80:
                status, j = b, j + 1
            kind = status & 0xF0
            nbytes = 1 if kind in (0xC0, 0xD0) else 2
            args = data[j:j + nbytes]
            j += nbytes
            if kind == 0x90 and args[1] > 0:
                events.append((tick, "on", (args[0], args[1])))
            elif kind == 0x80 or (kind == 0x90 and args[1] == 0):
                events.append((tick, "off", args[0]))
        i = end
    events.sort(key=lambda e: (e[0], e[1] != "tempo"))
    # ticks -> seconds through the tempo map
    tempo, last_tick, seconds, beats_per_bar = 500000, 0, 0.0, 4
    notes = []
    for tick, kind, payload in events:
        seconds += (tick - last_tick) * tempo / division / 1e6
        last_tick = tick
        if kind == "tempo":
            tempo = payload
        elif kind == "timesig":
            beats_per_bar = payload
        elif kind == "on":
            notes.append({"pitch": payload[0], "velocity": payload[1], "start": seconds, "beat": tick / division})
    return {"notes": notes, "beats_per_bar": beats_per_bar}


# ---------- writing SMF (selftest fixtures) ----------

def write_varlen(v: int) -> bytes:
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    return bytes(reversed(out))


def write_midi(path: Path, notes: list[tuple[float, int, int, float]], bpm: float = 60, division: int = 480) -> None:
    """notes: (start_beat, pitch, velocity, length_beats)."""
    evs = []
    for start, pitch, vel, length in notes:
        evs.append((round(start * division), 1, bytes([0x90, pitch, vel])))
        evs.append((round((start + length) * division), 0, bytes([0x80, pitch, 0])))
    evs.sort()
    body = b"\x00\xff\x51\x03" + int(60e6 / bpm).to_bytes(3, "big") + b"\x00\xff\x58\x04\x04\x02\x18\x08"
    last = 0
    for tick, _, msg in evs:
        body += write_varlen(tick - last) + msg
        last = tick
    body += b"\x00\xff\x2f\x00"
    path.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, division) + b"MTrk" + struct.pack(">I", len(body)) + body)


# ---------- comparison ----------

def group_events(notes: list[dict], chord_s: float) -> list[dict]:
    events = []
    for n in sorted(notes, key=lambda n: n["start"]):
        if events and n["start"] - events[-1]["start"] <= chord_s:
            events[-1]["pitches"].append(n["pitch"])
            events[-1]["velocities"].append(n["velocity"])
        else:
            events.append({"start": n["start"], "beat": n["beat"], "pitches": [n["pitch"]], "velocities": [n["velocity"]]})
    for e in events:
        e["pitches"] = sorted(e["pitches"])
    return events


def align(ref: list[dict], take: list[dict]) -> list[tuple[int | None, int | None]]:
    """Edit-distance alignment of chord events; substitution cost is the share of differing pitches."""
    def sub(a, b):
        sa, sb = set(a["pitches"]), set(b["pitches"])
        return len(sa ^ sb) / max(len(sa | sb), 1)

    n, m = len(ref), len(take)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i - 1][j - 1] + sub(ref[i - 1], take[j - 1]) * 1.5, cost[i - 1][j] + 1, cost[i][j - 1] + 1)
    pairs, i, j = [], n, m
    while i or j:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + sub(ref[i - 1], take[j - 1]) * 1.5:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return pairs[::-1]


def note_name(p: int) -> str:
    return ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][p % 12] + str(p // 12 - 1)


def compare(ref_midi: dict, take_midi: dict, chord_ms: float, timing_ms: float,
            from_bar: int | None, to_bar: int | None) -> dict:
    bpb = ref_midi["beats_per_bar"]
    ref = group_events(ref_midi["notes"], chord_ms / 1000)
    if from_bar or to_bar:
        lo = ((from_bar or 1) - 1) * bpb
        hi = (to_bar or 10**6) * bpb
        ref = [e for e in ref if lo <= e["beat"] < hi]
    take = group_events(take_midi["notes"], chord_ms / 1000)
    if not ref or not take:
        sys.exit("nothing to compare: empty reference range or take")
    pairs = align(ref, take)
    bar = lambda e: int(e["beat"] // bpb) + 1

    issues = []
    matched = []
    for ri, ti in pairs:
        if ri is not None and ti is not None:
            r, t = ref[ri], take[ti]
            if r["pitches"] == t["pitches"]:
                matched.append((r, t))
            else:
                missing = sorted(set(r["pitches"]) - set(t["pitches"]))
                extra = sorted(set(t["pitches"]) - set(r["pitches"]))
                issues.append({"bar": bar(r), "beat": round(r["beat"] % bpb + 1, 2), "kind": "wrong" if extra else "missed",
                               "missing": [note_name(p) for p in missing], "played": [note_name(p) for p in extra]})
                if set(r["pitches"]) & set(t["pitches"]):
                    matched.append((r, t))  # a partly right chord still carries timing
        elif ri is not None:
            r = ref[ri]
            issues.append({"bar": bar(r), "beat": round(r["beat"] % bpb + 1, 2), "kind": "missed",
                           "missing": [note_name(p) for p in r["pitches"]]})
        else:
            t = take[ti]
            prev = next((ref[p[0]] for p in reversed(pairs[:pairs.index((ri, ti))]) if p[0] is not None), ref[0])
            issues.append({"bar": bar(prev), "kind": "extra", "played": [note_name(p) for p in t["pitches"]],
                           "take_time_s": round(t["start"], 2)})

    report = {"ref_events": len(ref), "take_events": len(take), "issues": issues}
    if len(matched) >= 3:
        # Tempo from the median inter-onset ratio, so one hesitation does not bend the estimate.
        gaps = [(r1["start"] - r0["start"], t1["start"] - t0["start"]) for (r0, t0), (r1, t1) in zip(matched, matched[1:])]
        slope = statistics.median(g_t / g_r for g_r, g_t in gaps if g_r > 1e-3)
        report["tempo_ratio"] = round(1 / slope, 3)  # >1 = faster than the reference
        # Each note judged against the previous one: deviation of its inter-onset interval, in ms.
        hes, devs = [], []
        for ((r0, t0), (r1, t1)), (g_r, g_t) in zip(zip(matched, matched[1:]), gaps):
            want = g_r * slope
            d = (g_t - want) * 1000
            where = {"bar": bar(r1), "beat": round(r1["beat"] % bpb + 1, 2)}
            if g_t - want > max(0.25, want * 0.5):
                hes.append({**where, "extra_s": round(g_t - want, 2)})
            else:
                devs.append((where, d))
        report["timing_rms_ms"] = round((sum(d * d for _, d in devs) / max(len(devs), 1)) ** 0.5, 1)
        report["timing_outliers"] = [{**w, "ms": round(d)} for w, d in devs if abs(d) > timing_ms]
        report["hesitations"] = hes
        # Drift: local tempo in the first vs the last third of the passage.
        k = max(len(matched) // 3, 2)
        def local(seg):
            return (seg[-1][1]["start"] - seg[0][1]["start"]) / max(seg[-1][0]["start"] - seg[0][0]["start"], 1e-9)
        if len(matched) >= 2 * k:
            report["drift"] = {"first_third_ratio": round(1 / local(matched[:k]), 3), "last_third_ratio": round(1 / local(matched[-k:]), 3)}
        vels = [statistics.fmean(t["velocities"]) for _, t in matched]
        report["velocity"] = {"mean": round(statistics.fmean(vels)), "sd": round(statistics.pstdev(vels), 1)}

    # Worst bars: errors count 1, hesitations 1, timing outliers 0.5.
    score: dict[int, float] = {}
    for it in issues:
        score[it["bar"]] = score.get(it["bar"], 0) + 1
    for it in report.get("hesitations", []):
        score[it["bar"]] = score.get(it["bar"], 0) + 1
    for it in report.get("timing_outliers", []):
        score[it["bar"]] = score.get(it["bar"], 0) + 0.5
    report["worst_bars"] = [b for b, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
    report["exact_events_pct"] = round(100 * sum(r["pitches"] == t["pitches"] for r, t in matched) / len(ref), 1)
    return report


def print_report(rep: dict) -> None:
    print(f"events: reference {rep['ref_events']}, take {rep['take_events']}; exact {rep['exact_events_pct']}%")
    if "tempo_ratio" in rep:
        print(f"tempo: {rep['tempo_ratio']}x reference; timing rms {rep['timing_rms_ms']} ms; "
              f"velocity mean {rep['velocity']['mean']} sd {rep['velocity']['sd']}")
        if "drift" in rep:
            print(f"drift: first third {rep['drift']['first_third_ratio']}x, last third {rep['drift']['last_third_ratio']}x")
    for it in rep["issues"]:
        print(f"  bar {it['bar']}: {it['kind']} " + json.dumps({k: v for k, v in it.items() if k not in ('bar', 'kind')}))
    for it in rep.get("hesitations", []):
        print(f"  bar {it['bar']} beat {it['beat']}: hesitation +{it['extra_s']} s")
    for it in rep.get("timing_outliers", []):
        print(f"  bar {it['bar']} beat {it['beat']}: {it['ms']:+d} ms")
    print(f"worst bars: {rep['worst_bars'] or 'none'}")


def selftest() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Two bars of C major scale up and down in quarters, with a chord on each downbeat.
        scale = [60, 62, 64, 65, 67, 65, 64, 62]
        ref = [(b, p, 70, 0.9) for b, p in enumerate(scale)] + [(0, 48, 60, 3.9), (4, 43, 60, 3.9)]
        write_midi(tmp / "ref.mid", ref, bpm=60)
        # Take: 10% slower; E4 -> Eb4 in bar 1 beat 3; G4 missed in bar 2; a 0.8 s hesitation before bar 2 beat 3.
        take = []
        shift = 0.0
        for b, p in enumerate(scale):
            if b == 4:
                continue
            if b == 6:
                shift = 0.8
            take.append((b * 1.1 + shift, 63 if b == 2 else p, 75, 0.9))
        take += [(0.0, 48, 60, 3.9), (4.4, 43, 60, 3.9)]
        write_midi(tmp / "take.mid", take, bpm=60)
        rep = compare(read_midi(tmp / "ref.mid"), read_midi(tmp / "take.mid"), 40, 80, None, None)
        kinds = {(i["bar"], i["kind"]) for i in rep["issues"]}
        assert (1, "wrong") in kinds, rep
        assert any(i["kind"] == "wrong" and i["missing"] == ["E4"] and i["played"] == ["D#4"] for i in rep["issues"]), rep
        assert any(i["kind"] in ("missed", "wrong") and "G4" in i.get("missing", []) for i in rep["issues"]), rep
        assert any(h["bar"] == 2 for h in rep["hesitations"]), rep
        assert 0.85 < rep["tempo_ratio"] < 0.95, rep
        assert 2 in rep["worst_bars"], rep
        print_report(rep)
    print("selftest ok")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--ref", type=Path)
    p.add_argument("--take", type=Path)
    p.add_argument("--from-bar", type=int)
    p.add_argument("--to-bar", type=int)
    p.add_argument("--chord-ms", type=float, default=40, help="notes struck within this window are one event")
    p.add_argument("--timing-ms", type=float, default=80, help="list onset deviations larger than this")
    p.add_argument("--json", type=Path, help="also write the report here")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not (a.ref and a.take):
        p.error("--ref and --take are required")
    rep = compare(read_midi(a.ref), read_midi(a.take), a.chord_ms, a.timing_ms, a.from_bar, a.to_bar)
    print_report(rep)
    if a.json:
        a.json.write_text(json.dumps(rep, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
