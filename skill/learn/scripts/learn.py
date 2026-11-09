#!/usr/bin/env python
r"""State for the `learn` skill: topics, the review queue, process feedback and the calendar plan.

Everything lives under one folder (default ~/learning, or $LEARN_HOME, or --home) as small
JSON/JSONL files an agent or the owner can read directly. This script exists so that ids, due dates,
spacing and the calendar diff are computed the same way by Claude, Codex and pi, not re-derived.

Why reviews double as the error log: a mistake worth remembering is a mistake worth re-testing, so
each record holds the error *and* the prompt that re-tests it. One record per weakness, no parallel
summaries.

Why the calendar is a diff, not a write: only Claude has the Google Calendar connector. `plan` prints
create/update/delete actions; whoever can reach the calendar executes them and calls `cal record`.
An agent without the connector leaves them pending and `status` shows the drift.

  python learn.py init
  python learn.py status [--date D] [--topic SLUG]     (also runs prep-check per booked session + the checklist)
  python learn.py topic new SLUG --type paper|concept|practical --goal "..."
  python learn.py topic next SLUG --date D --minutes N --task "..." [--slot morning|evening] [--at HH:MM]
  python learn.py topic prep SLUG --status ready|blocked --note "..." [--date D [--slot morning|evening]]
                             [--override "why"]     (ready runs prep-check and refuses on a FAIL)
  python learn.py topic set SLUG --status active|paused|done
  python learn.py prep-check SLUG D [--page PATH] [--no-page-scripts]
  python learn.py review add --topic SLUG --prompt "..." --criterion "..." [--error "..."] [--evidence REF]
                             [--kind vocab|pattern|concept] [--due D | --first-due-days N]
  python learn.py review result ID again|hard|good|easy [--note "..."]   (pass = good, fail = again)
  python learn.py review defer ID [--to D]          (default: 2 days after its last check)
  python learn.py review list [--due] [--topic SLUG]
  python learn.py plan [--days 7] [--now ISO]
  python learn.py cal record KEY EVENT_ID   |   python learn.py cal forget KEY
  python learn.py feedback add "..." [--source owner|tutor] [--topic SLUG] [--rule SLUG]
  python learn.py feedback tag ID --rule SLUG   |   python learn.py feedback rules
  python learn.py feedback list [--all]
  python learn.py feedback resolve ID --change "..." [--check "<script that enforces it>" | --no-check-possible "why"]
  python learn.py selftest

Why the feedback commands detect repeats (owner, 2026-11-09: "repair the lane too, so we don't keep circling"):
a correction answered with a prose rule in SKILL.md came back, again and again. `feedback add` compares the
text with earlier rows (and the --rule tag) and prints REPEAT; a repeat cannot be resolved without naming the
check that now enforces it. The ledger is references/recurring-feedback.md.

Dates are local (the calendar connector resolves the owner's time zone). D accepts YYYY-MM-DD,
"today" or "tomorrow".

Review spacing is FSRS-6 (the scheduler Anki uses), at 90% target recall: each item carries a memory
stability S (days until recall falls to 90%) and difficulty D, updated from the grade and the days
since the last review. Kept from Anki: the four grades, interval fuzz, leeches (4 lapses: rewrite or
reteach the item rather than re-asking it). Not kept: decks, learning steps, sync, the optimizer. An
item retires once its next interval would exceed 120 days. Rows written by the old 1/3/7/21 ladder
(`rung`, no `stability`) are converted when next graded.

Several sessions can be booked per topic (a weekend morning and evening, or tonight and Monday).
`topic next` adds one; a booking for the same date and slot replaces the old one, and every session
whose start has already passed (the one just run, or one that was missed) is dropped. Each booked
session gets its own calendar event; that day's due reviews ride with the day's first session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_HOME = Path(os.environ.get("LEARN_HOME", str(Path.home() / "learning")))
TYPES = ("paper", "concept", "practical")
LADDER = [1, 3, 7, 21]  # the pre-FSRS ladder; read only to convert old rows (`rung` k -> stability LADDER[k])

# FSRS-6 default parameters w0..w20, copied from py-fsrs v6.3.2 (open-spaced-repetition/py-fsrs, commit
# 9446cb06605c597a063aeee49f7d188d42e34dc2, fsrs/scheduler.py DEFAULT_PARAMETERS); the formulas below
# follow that file's _initial_stability/_initial_difficulty/_next_difficulty/_next_*_stability/
# _short_term_stability/_next_interval. Fuzz follows Anki rslib/src/scheduler/states/fuzz.rs (commit
# 9d447f0f73defd05fc81e79092eabb28627c5964), seeded from item id + reps as Anki seeds from card id + reps.
FSRS_W = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796,
          1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542)
DESIRED_RETENTION = 0.9
MAX_INTERVAL = 365          # days
RETIRE_AFTER_DAYS = 120     # well-known items stop coming back once the next interval would exceed this
LEECH_LAPSES = 4            # lapses at which an item is flagged: rewrite or reteach it, don't re-ask
# A new item comes from material just worked in the session, so it first comes due a few days later, not
# tomorrow (owner, 2026-11-09: r011 came back the morning after S1 was answered and graded). From an error: 2.
FIRST_DUE_DAYS = 3
FIRST_DUE_DAYS_ERROR = 2
# No review falls due less than 2 days after a check on the same material (owner, 2026-11-09, f048/f049): the
# scheduler's minimum interval, and prep-check fails a due review checked less than this many days before.
MIN_GAP_DAYS = 2
GRADES = {"again": 1, "hard": 2, "good": 3, "easy": 4}
GRADE_ALIASES = {"pass": "good", "fail": "again"}  # the pre-FSRS outcomes, still accepted
KINDS = ("vocab", "pattern", "concept")
LEECH_NOTE = "leech: rewrite or reteach, don't re-ask"

# Owner's cadence (2026-10-29): weekday morning brief + evening medium; weekends longer, both ends.
DEFAULT_SLOTS = {
    "weekday": [
        {"name": "morning", "start": "07:45", "end": "08:30"},
        {"name": "evening", "start": "20:30", "end": "21:15"},
    ],
    "weekend": [
        {"name": "morning", "start": "10:00", "end": "12:00"},
        {"name": "evening", "start": "19:30", "end": "21:30"},
    ],
}


# ---------- files ----------

def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def write_text(path: Path, text: str) -> None:
    # Replace atomically so a reader never sees half a file.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


class State:
    def __init__(self, home: Path):
        self.home = home
        self.topics_dir = home / "topics"
        self.reviews_path = home / "reviews.jsonl"
        self.feedback_path = home / "feedback.jsonl"
        self.calendar_path = home / "calendar.json"
        self.slots_path = home / "slots.json"

    def topics(self) -> dict[str, dict]:
        out = {}
        if self.topics_dir.exists():
            for meta in sorted(self.topics_dir.glob("*/meta.json")):
                m = read_json(meta, {})
                out[m["slug"]] = m
        return out

    def topic(self, slug: str) -> dict:
        path = self.topics_dir / slug / "meta.json"
        if not path.exists():
            sys.exit(f"no topic '{slug}' (try: topic new {slug} --type ... --goal ...)")
        return read_json(path, {})

    def save_topic(self, meta: dict) -> None:
        write_json(self.topics_dir / meta["slug"] / "meta.json", meta)

    def slots(self) -> dict:
        return read_json(self.slots_path, DEFAULT_SLOTS)


# ---------- dates ----------

def parse_day(s: str | None, today: dt.date) -> dt.date:
    if s in (None, "today"):
        return today
    if s == "tomorrow":
        return today + dt.timedelta(days=1)
    return dt.date.fromisoformat(s)


def session_start(st: State, ns: dict) -> dt.datetime:
    day = dt.date.fromisoformat(ns["date"])
    if ns.get("at"):
        t = ns["at"]
    else:
        slots = st.slots()["weekend" if day.weekday() >= 5 else "weekday"]
        t = next((x["start"] for x in slots if x["name"] == (ns.get("slot") or "evening")), slots[-1]["start"])
    return dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=hm(t))


def booked(st: State, meta: dict) -> list[dict]:
    """Booked sessions, earliest first. State written before 2026-11-08 kept one `next_session`."""
    rows = meta.get("sessions")
    if rows is None:
        rows = [meta["next_session"]] if meta.get("next_session") else []
    return sorted(rows, key=lambda ns: session_start(st, ns))


def set_booked(st: State, meta: dict, rows: list[dict]) -> None:
    meta["sessions"] = sorted(rows, key=lambda ns: session_start(st, ns))
    meta.pop("next_session", None)


def next_id(rows: list[dict], prefix: str) -> str:
    nums = [int(r["id"][len(prefix):]) for r in rows if re.fullmatch(prefix + r"\d+", r.get("id", ""))]
    return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"


# ---------- FSRS-6 ----------

_DECAY = -FSRS_W[20]
_FACTOR = 0.9 ** (1 / _DECAY) - 1


def rnd(x: float) -> int:
    return math.floor(x + 0.5)  # half away from zero for x >= 0, as Rust's round in Anki


def fsrs_init_s(g: int) -> float:
    return max(FSRS_W[g - 1], 0.001)


def fsrs_init_d(g: int, clamp: bool = True) -> float:
    d = FSRS_W[4] - math.exp(FSRS_W[5] * (g - 1)) + 1
    return min(max(d, 1.0), 10.0) if clamp else d


def fsrs_next_d(d: float, g: int) -> float:
    delta = -FSRS_W[6] * (g - 3)
    damped = d + (10.0 - d) * delta / 9.0                           # linear damping
    d2 = FSRS_W[7] * fsrs_init_d(4, clamp=False) + (1 - FSRS_W[7]) * damped  # mean reversion to D0(easy)
    return min(max(d2, 1.0), 10.0)


def fsrs_retrievability(s: float, elapsed: int) -> float:
    return (1 + _FACTOR * elapsed / s) ** _DECAY


def fsrs_next_s(s: float, d: float, g: int, elapsed: int) -> float:
    if elapsed < 1:  # same-day review: FSRS-6 short-term stability
        inc = math.exp(FSRS_W[17] * (g - 3 + FSRS_W[18])) * s ** -FSRS_W[19]
        if g > 1:
            inc = max(inc, 1.0)
        return max(s * inc, 0.001)
    r = fsrs_retrievability(s, elapsed)
    if g == 1:
        long_term = FSRS_W[11] * d ** -FSRS_W[12] * ((s + 1) ** FSRS_W[13] - 1) * math.exp((1 - r) * FSRS_W[14])
        return max(min(long_term, s / math.exp(FSRS_W[17] * FSRS_W[18])), 0.001)
    hard = FSRS_W[15] if g == 2 else 1
    easy = FSRS_W[16] if g == 4 else 1
    return max(s * (1 + math.exp(FSRS_W[8]) * (11 - d) * s ** -FSRS_W[9]
                    * (math.exp((1 - r) * FSRS_W[10]) - 1) * hard * easy), 0.001)


def fsrs_interval(s: float) -> float:
    """Days until predicted recall falls to DESIRED_RETENTION (unrounded; equals s at 0.9)."""
    return s / _FACTOR * (DESIRED_RETENTION ** (1 / _DECAY) - 1)


def fuzz_bounds(ivl: float, minimum: int) -> tuple[int, int]:
    minimum = min(minimum, MAX_INTERVAL)
    ivl = min(max(ivl, minimum), MAX_INTERVAL)
    delta = 0.0 if ivl < 2.5 else 1.0 + sum(f * max(min(ivl, end) - start, 0.0)
                                            for start, end, f in ((2.5, 7.0, 0.15), (7.0, 20.0, 0.1), (20.0, math.inf, 0.05)))
    lower = min(max(rnd(ivl - delta), minimum), MAX_INTERVAL)
    upper = min(max(rnd(ivl + delta), minimum), MAX_INTERVAL)
    if upper == lower and 2 < upper < MAX_INTERVAL:
        upper = lower + 1
    return lower, upper


def fuzzed_days(ivl: float, seed: str, minimum: int = 1) -> int:
    lower, upper = fuzz_bounds(ivl, minimum)
    frac = int(hashlib.sha256(seed.encode()).hexdigest()[:13], 16) / 16 ** 13  # deterministic, in [0, 1)
    return math.floor(lower + frac * (1 + upper - lower))


def fsrs_migrate(row: dict) -> None:
    """Give a ladder-era row (`rung`, no `stability`) FSRS state. Unreviewed rows stay `new`."""
    if "stability" in row:
        return
    graded = [(h["date"], GRADES.get(h.get("grade") or GRADE_ALIASES.get(h.get("result") or h.get("outcome"), "")))
              for h in row.get("history", [])]
    graded = [(day, g) for day, g in graded if g]
    rung = row.pop("rung", 0) or 0
    row.setdefault("kind", "pattern")
    # A fail on an item's first grading is not a lapse (Anki counts lapses of reviewed items only).
    row.update(reps=len(graded), lapses=sum(1 for _, g in graded[1:] if g == 1), migrated_from_rung=rung)
    if not graded:
        row.update(stability=None, difficulty=None, last_review=None, interval=None, state="new")
        return
    s = float(LADDER[rung]) if rung > 0 else fsrs_init_s(graded[-1][1])
    row.update(stability=s, difficulty=fsrs_init_d(3), last_review=graded[-1][0], interval=LADDER[rung],
               state="relearning" if graded[-1][1] == 1 else "review")


def fsrs_review(row: dict, grade: str, today: dt.date) -> dict:
    """Apply one graded review to `row` in place; return the history entry."""
    fsrs_migrate(row)
    g = GRADES[grade]
    new = row["state"] == "new" or row["stability"] is None
    elapsed = 0 if new else max((today - dt.date.fromisoformat(row["last_review"])).days, 0)
    if new:
        s, d = fsrs_init_s(g), fsrs_init_d(g)
    else:
        s = fsrs_next_s(row["stability"], row["difficulty"], g, elapsed)
        d = fsrs_next_d(row["difficulty"], g)
        if g == 1 and (row["state"] == "review" or elapsed >= 1):  # a same-day re-fail is the same lapse
            row["lapses"] += 1
    ivl = fsrs_interval(s)
    minimum, prev = MIN_GAP_DAYS, row.get("interval")
    if g > 1 and not new and prev:  # Anki: fuzz may not shrink a passing interval below the previous one
        rounded, upper = rnd(ivl), fuzz_bounds(ivl, 1)[1]
        minimum = max(prev + 1 if rounded > prev else (prev if prev <= upper else 1), MIN_GAP_DAYS)
    days = fuzzed_days(ivl, f"{row['id']}:{row['reps']}", minimum)
    row.update(stability=round(s, 4), difficulty=round(d, 4), last_review=today.isoformat(), interval=days,
               reps=row["reps"] + 1, state="relearning" if g == 1 and not new else "review")
    if row["lapses"] >= LEECH_LAPSES:
        row["leech"] = True
    if g > 1 and ivl > RETIRE_AFTER_DAYS:
        row.update(status="retired", due=None)
    else:
        row["due"] = (today + dt.timedelta(days=days)).isoformat()
    return {"grade": grade, "elapsed_days": elapsed, "interval": None if row["due"] is None else days}


# ---------- commands ----------

def cmd_init(st: State, args) -> None:
    st.topics_dir.mkdir(parents=True, exist_ok=True)
    (st.home / "recordings").mkdir(exist_ok=True)
    if not st.slots_path.exists():
        write_json(st.slots_path, DEFAULT_SLOTS)
    for p in (st.reviews_path, st.feedback_path):
        if not p.exists():
            write_text(p, "")
    if not st.calendar_path.exists():
        write_json(st.calendar_path, {})
    print(f"ready: {st.home}")


def cmd_topic(st: State, args, now: dt.datetime) -> None:
    today = now.date()
    if args.action == "new":
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.slug):
            sys.exit("slug: lowercase letters, digits and hyphens")
        if (st.topics_dir / args.slug / "meta.json").exists():
            sys.exit(f"topic '{args.slug}' exists")
        meta = {"slug": args.slug, "type": args.type, "goal": args.goal or "", "status": "active",
                "created": today.isoformat(), "sessions": []}
        st.save_topic(meta)
        log = st.topics_dir / args.slug / "log.md"
        if not log.exists():
            write_text(log, f"# {args.slug}\n\nType: {args.type}\nGoal: {args.goal or '(set in first session)'}\n"
                            "Sources:\nOwner's emphasis / values for this topic:\n\n## Sessions\n")
        print(f"created topics/{args.slug}/ (meta.json, log.md)")
    elif args.action == "next":
        meta = st.topic(args.slug)
        new = {"date": parse_day(args.date, today).isoformat(), "minutes": args.minutes, "task": args.task,
               "slot": args.slot, "at": args.at, "prep": {"status": "pending", "note": ""}}
        same = lambda ns: (ns["date"], ns.get("slot"), ns.get("at")) == (new["date"], new["slot"], new["at"])
        # A session whose start has passed was run (or missed): booking the next one closes it.
        keep = [ns for ns in booked(st, meta) if session_start(st, ns) > now and not same(ns)]
        set_booked(st, meta, keep + [new])
        st.save_topic(meta)
        print(f"{args.slug}: booked {new['date']} ({args.minutes} min): {args.task}")
        print("  booked now: " + ", ".join(f"{ns['date']} {ns.get('at') or ns.get('slot') or 'evening'}"
                                           for ns in meta["sessions"]))
    elif args.action == "prep":
        meta = st.topic(args.slug)
        rows = booked(st, meta)
        if args.date:
            day = parse_day(args.date, today).isoformat()
            rows = [ns for ns in rows if ns["date"] == day and (not args.slot or ns.get("slot") == args.slot)]
        if not rows:
            sys.exit(f"{args.slug}: no matching session booked")
        prep = {"status": args.status, "note": args.note or ""}
        if args.status == "ready":  # ready means the slot-readiness gate passed (owner, 2026-11-09, f056)
            day = dt.date.fromisoformat(rows[0]["date"])
            out, _ = ready_findings(st, args.slug, day)
            fails = [msg for level, msg in out if level == "FAIL"]
            if fails and not args.override:
                sys.exit(f"{args.slug}: ready-check fails for {day}; not marked ready:\n  " + "\n  ".join(fails)
                         + "\nFix them before the slot (slot time is never spent on tooling), or pass --override \"<why>\".")
            prep["gate"] = f"override: {args.override}" if fails else f"ready-check passed {today.isoformat()}"
        rows[0]["prep"] = prep
        set_booked(st, meta, booked(st, meta))  # same dicts: persists the edit, migrates old state
        st.save_topic(meta)
        print(f"{args.slug}: prep {args.status}" + (f" - {args.note}" if args.note else ""))
    elif args.action == "set":
        meta = st.topic(args.slug)
        meta["status"] = args.status
        if args.status != "active":
            set_booked(st, meta, [])
        st.save_topic(meta)
        print(f"{args.slug}: {args.status}")
    elif args.action == "list":
        for m in st.topics().values():
            rows = booked(st, m)
            nxt = rows[0]["date"] + (f" +{len(rows) - 1}" if len(rows) > 1 else "") if rows else "-"
            print(f"{m['slug']:24} {m['type']:9} {m['status']:7} next={nxt}  {m['goal']}")


def first_due(args, today: dt.date) -> dt.date:
    """--due wins; else --first-due-days; else 2 days for an item made from an error, 3 otherwise."""
    if args.due:
        return parse_day(args.due, today)
    days = args.first_due_days or (FIRST_DUE_DAYS_ERROR if args.error else FIRST_DUE_DAYS)
    return today + dt.timedelta(days=days)


def cmd_review(st: State, args, today: dt.date) -> None:
    rows = read_jsonl(st.reviews_path)
    if args.action == "add":
        st.topic(args.topic)
        row = {"id": next_id(rows, "r"), "topic": args.topic, "prompt": args.prompt, "criterion": args.criterion,
               "error": args.error or "", "evidence": args.evidence or "", "created": today.isoformat(),
               "due": first_due(args, today).isoformat(),
               "kind": args.kind, "history": [], "status": "active", "state": "new", "stability": None,
               "difficulty": None, "last_review": None, "interval": None, "reps": 0, "lapses": 0}
        rows.append(row)
        write_jsonl(st.reviews_path, rows)
        print(f"{row['id']} due {row['due']}: {row['prompt']}")
    elif args.action == "result":
        row = next((r for r in rows if r["id"] == args.id), None)
        if not row:
            sys.exit(f"no review {args.id}")
        grade = GRADE_ALIASES.get(args.outcome, args.outcome)
        entry = fsrs_review(row, grade, today)
        row["history"].append({"date": today.isoformat(), "result": args.outcome, **entry, "note": args.note or ""})
        write_jsonl(st.reviews_path, rows)
        print(f"{row['id']}: {args.outcome} -> " + (f"due {row['due']}" if row["due"] else "retired")
              + f" (stability {row['stability']:.1f}d, difficulty {row['difficulty']:.1f}, lapses {row['lapses']})"
              + (f"  [{LEECH_NOTE}]" if row.get("leech") else ""))
    elif args.action == "defer":
        row = next((r for r in rows if r["id"] == args.id), None)
        if not row:
            sys.exit(f"no review {args.id}")
        floor = last_check(row) + dt.timedelta(days=MIN_GAP_DAYS)
        to = parse_day(args.to, today) if args.to else max(floor, today + dt.timedelta(days=1))
        if to < floor:
            sys.exit(f"{row['id']} was last checked {last_check(row)}: not before {floor} (MIN_GAP_DAYS {MIN_GAP_DAYS})")
        row.setdefault("deferrals", []).append({"date": today.isoformat(), "from": row.get("due"), "to": to.isoformat()})
        row["due"] = to.isoformat()
        write_jsonl(st.reviews_path, rows)
        print(f"{row['id']} deferred to {row['due']}")
    elif args.action == "list":
        for r in rows:
            if r["status"] != "active" or (args.topic and r["topic"] != args.topic):
                continue
            if args.due and r["due"] > today.isoformat():
                continue
            print(f"{r['id']} {r['topic']:20} {r.get('kind', 'pattern'):7} due {r['due']}  {r['prompt']}"
                  + (f"  [{LEECH_NOTE}]" if r.get("leech") else ""))


# ---------- feedback and the repeat detector ----------

# Owner, 2026-11-09: the same corrections came back after being "resolved" with prose in SKILL.md (example-first
# 3x, per-answer page submit 3x+). A repeat is detected here and cannot be resolved without naming its check.
SKILL_DIR = Path(__file__).resolve().parent.parent
LEDGER = "references/recurring-feedback.md"
# Set-cosine of stemmed content words. Calibrated on f001-f058: wording overlap is a weak signal (true repeats
# f041/f042 score 0.20, unrelated f052/f043 0.29), so the --rule tag is the reliable one; at 0.34 only near-verbatim
# repeats auto-flag, and from 0.20 the closest row is shown as a hint to tag.
REPEAT_THRESHOLD = 0.34
SIMILAR_HINT = 0.20
_STOP = set("""the a an and or but to of in on for with at by from as is are was were be been being it its this that
these those i me my you your we our they them their he she his her not no do does did done don so if then than there
here what which who when where why how all any each every just only also too very can could should would will must may
might need needs into out up about after before over under again more most some such own same other one two get got
has have had like make made keep kept still even now yet way one's owner tutor""".split())


def _tokens(text: str) -> set[str]:
    # Crude stem: the first 6 letters, so submit/submitted and review/reviews meet.
    return {w[:6] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in _STOP}


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / math.sqrt(len(ta) * len(tb)) if ta and tb else 0.0


def find_repeat(rows: list[dict], text: str, rule: str | None) -> tuple[dict | None, str, dict | None, float]:
    """(repeated row, rule, closest row, its score): the first row with the same rule tag, else the closest text."""
    best = max(rows, key=lambda r: similarity(text, r["text"]), default=None)
    score = similarity(text, best["text"]) if best else 0.0
    if rule:
        same = [r for r in rows if r.get("rule") == rule]
        if same:
            return same[0], rule, best, score
    if best and score >= REPEAT_THRESHOLD and not rule:
        return best, best.get("rule") or "", best, score
    return None, rule or "", best, score


def rule_count(rows: list[dict], rule: str) -> int:
    return sum(1 for r in rows if rule and r.get("rule") == rule)


def check_refs_ok(check: str) -> str | None:
    """A --check must name the script, page template or file that enforces the rule, and it must exist."""
    refs = re.findall(r"[\w./\\:-]+\.(?:py|js|mjs|html|ps1)\b", check)
    if not refs:
        return "name the script or template that enforces it (e.g. 'learn.py ready-check ...')"
    for ref in refs:
        p = Path(ref)
        cands = [p] if p.is_absolute() else [SKILL_DIR / p, SKILL_DIR / "scripts" / p, SKILL_DIR / "assets" / p]
        if not any(c.exists() for c in cands):
            return f"{ref} does not exist (looked in {SKILL_DIR}/, scripts/, assets/)"
    return None


def cmd_feedback(st: State, args, today: dt.date) -> None:
    rows = read_jsonl(st.feedback_path)
    if args.action == "add":
        match, rule, best, score = find_repeat(rows, args.text, args.rule)
        row = {"id": next_id(rows, "f"), "date": today.isoformat(), "source": args.source,
               "topic": args.topic or "", "text": args.text, "status": "open", "change": "", "rule": rule}
        if match:
            row["repeat_of"] = match["id"]
        rows.append(row)
        write_jsonl(st.feedback_path, rows)
        print(f"{row['id']} recorded" + (f" (rule {rule})" if rule else ""))
        if match:
            n = rule_count(rows, rule) if rule else 2
            print(f"REPEAT of {match['id']} (rule {rule or '?'}, given {n} times): needs a mechanical check, not prose")
            print(f"  {match['id']} {match['date']}: {match['text'][:160]}")
            print(f"  -> add a check; resolve with --check \"<script>\" or --no-check-possible \"<why>\"; update {LEDGER}")
            if not rule:
                print(f"  tag it: learn.py feedback tag {row['id']} --rule <slug> (and tag {match['id']} too)")
        else:
            if best and score >= SIMILAR_HINT:
                print(f"  similar: {best['id']} ({score:.2f}, rule {best.get('rule') or '-'}): {best['text'][:120]}")
                print(f"  if it is the same rule: learn.py feedback tag {row['id']} --rule {best.get('rule') or '<slug>'}")
            if not rule:
                known = sorted({r.get("rule") for r in rows if r.get("rule")})
                print(f"  untagged: learn.py feedback tag {row['id']} --rule <slug>"
                      + (f"  (known: {', '.join(known)})" if known else ""))
    elif args.action == "tag":
        row = next((r for r in rows if r["id"] == args.id), None)
        if not row:
            sys.exit(f"no feedback {args.id}")
        row["rule"] = args.rule
        earlier = [r for r in rows if r.get("rule") == args.rule and r is not row and int(r["id"][1:]) < int(row["id"][1:])]
        if earlier and not row.get("repeat_of"):
            row["repeat_of"] = earlier[0]["id"]
        write_jsonl(st.feedback_path, rows)
        print(f"{row['id']}: rule {args.rule} (given {rule_count(rows, args.rule)} times)"
              + (f", repeat of {row['repeat_of']}" if row.get("repeat_of") else ""))
    elif args.action == "resolve":
        row = next((r for r in rows if r["id"] == args.id), None)
        if not row:
            sys.exit(f"no feedback {args.id}")
        repeat = bool(row.get("repeat_of")) or rule_count(rows, row.get("rule", "")) >= 2
        if repeat and not (args.check or args.no_check_possible):
            sys.exit(f"{row['id']} repeats {row.get('repeat_of') or 'an earlier row'} (rule {row.get('rule') or '?'}, "
                     f"given {max(rule_count(rows, row.get('rule', '')), 2)} times): a prose fix has already failed once. "
                     "Resolve with --check \"<script/check that now enforces it>\" or --no-check-possible \"<why>\".")
        if args.check:
            err = check_refs_ok(args.check)
            if err:
                sys.exit(f"--check: {err}")
        row.update(status="resolved", change=args.change, resolved=today.isoformat())
        if args.check:
            row["check"] = args.check
        if args.no_check_possible:
            row["no_check_possible"] = args.no_check_possible
        write_jsonl(st.feedback_path, rows)
        print(f"{row['id']} resolved" + (f"; check: {args.check}" if args.check else ""))
        if repeat or args.check:
            print(f"  update the row for rule {row.get('rule') or '?'} in {LEDGER}")
    elif args.action == "rules":
        rules: dict[str, list[dict]] = {}
        for r in rows:
            rules.setdefault(r.get("rule") or "(untagged)", []).append(r)
        for rule, rs in sorted(rules.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            checks = sorted({r["check"] for r in rs if r.get("check")})
            print(f"{rule:28} {len(rs):2}x  {' '.join(r['id'] for r in rs)}" + (f"  check: {'; '.join(checks)}" if checks else ""))
    elif args.action == "list":
        for r in rows:
            if args.all or r["status"] == "open":
                tag = (f" <{r['rule']}>" if r.get("rule") else "") + (f" repeat of {r['repeat_of']}" if r.get("repeat_of") else "")
                print(f"{r['id']} {r['date']} [{r['source']}{'/' + r['topic'] if r['topic'] else ''}] "
                      f"{r['status']}{tag}: {r['text']}" + (f"  -> {r['change']}" if r.get("change") else ""))


# ---------- prep-check and ready-check (the slot-readiness gate) ----------

# Owner, 2026-11-09 (f056): "i basically didn't get anything done in this session ... was just fighting you": the
# slot went on tooling and page defects. `topic prep --status ready` now runs ready-check and refuses on a FAIL.
RUN_PAGE_SCRIPTS = True  # selftest turns the external page scripts off (they need node and Chrome)
_RID = re.compile(r"\br(\d{3})\b")
_DASHES = chr(0x2013) + chr(0x2014)  # en and em dash, spelled out so no editor or write tool alters them
_RRANGE = re.compile(r"\br(\d{3})\s*(?:-|[" + _DASHES + r"]|\.\.|to)\s*r?(\d{3})\b")
_CHAT = re.compile(r"\b(?:in|into|via|to|through|over|on)\s+(?:the\s+)?chat\b|:\s*chat\b|\bchat\s+only\b", re.I)
_NOT_CHAT = re.compile(r"\b(?:no|not|never|instead\s+of|rather\s+than)\s+(?:in\s+|via\s+|on\s+)?(?:the\s+)?chat\b", re.I)
_ON_PAGE = re.compile(r"\b(?:page|box|boxes|db|field|textarea)\b", re.I)
_SETTLED = re.compile(r"\b(?:defer|deferred|moved|retired|dropped|done|answered|graded|invalid)\b", re.I)
KEY_PARTS = [  # (what, pattern, topic types, level): SKILL.md Prepare step 4
    ("plan", r"(?im)^\s*(?:#{1,6}[^\n]*\bplan\b|\*\*[^*\n]*\bplan\b|[-*]?\s*plan\s*[:(])", TYPES, "FAIL"),
    ("glossary (terms the owner likely hasn't met, handed over before reading; f007, f008)", r"(?i)\bglossary\b",
     ("paper", "concept"), "FAIL"),
    ("likely mistakes", r"(?im)\bmistakes?\b|\bmisconceptions?\b|^\s*[-*]?\s*likely\s*:", TYPES, "FAIL"),
    ("10-minute version", r"(?i)\b10[- ]?min(?:ute)?s?\b[^\n]{0,20}\bversion\b", TYPES, "FAIL"),
    ("exit or transfer question", r"(?i)\bexit\b|\btransfer\b", TYPES, "WARN"),
    ("bare file:/// URI of the paper, to paste in chat (f004, f039)", r"(?i)file:///\S+\.pdf", ("paper",), "FAIL"),
]


def ids_in(text: str) -> set[str]:
    ids = {"r" + n for n in _RID.findall(text)}
    for a, b in _RRANGE.findall(text):
        lo, hi = int(a), int(b)
        if 0 < hi - lo <= 30:
            ids |= {f"r{i:03d}" for i in range(lo, hi + 1)}
    return ids


def find_key(st: State, slug: str, day: dt.date) -> Path | None:
    d = st.topics_dir / slug / "prep"
    exact = d / f"{day.isoformat()}.tutor-only.md"
    if exact.exists():
        return exact
    found = sorted(d.glob(f"{day.isoformat()}*.tutor-only.md"), key=lambda p: p.stat().st_mtime) if d.exists() else []
    return found[-1] if found else None


def find_page(st: State, slug: str, meta: dict, given: str | None = None) -> Path | None:
    """--page, else meta.json "page" (relative to the topic folder), else the newest .html in the topic folder."""
    if given:
        return Path(given)
    d = st.topics_dir / slug
    if meta.get("page"):
        return d / meta["page"]
    skip = {"sources", "lab", "later", "sessions", "recordings"}
    found = [p for p in d.rglob("*.html") if not skip & set(p.relative_to(d).parts[:-1]) and "pre-" not in p.name]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def last_check(r: dict) -> dt.date:
    days = [r.get("created"), r.get("last_review")] + [h.get("date") for h in r.get("history", [])]
    return max(dt.date.fromisoformat(d) for d in days if d)


def prep_findings(st: State, slug: str, day: dt.date, page: str | None = None) -> tuple[list[tuple[str, str]], Path | None, Path | None]:
    """The prep key's own checks: its parts, due reviews on the page and not in chat, none too soon, ids reconciled."""
    meta = st.topic(slug)
    out: list[tuple[str, str]] = []
    key = find_key(st, slug, day)
    text = ""
    if key is None:
        out.append(("FAIL", f"no prep key topics/{slug}/prep/{day.isoformat()}.tutor-only.md (Prepare step 4)"))
    else:
        text = key.read_text(encoding="utf-8")
        for what, pat, types, level in KEY_PARTS:
            if meta["type"] in types and not re.search(pat, text):
                out.append((level, f"key has no {what}"))
        log = st.topics_dir / slug / "log.md"
        if log.exists() and log.stat().st_mtime > key.stat().st_mtime + 60:
            out.append(("FAIL", f"log.md changed after the key was written: reconcile the key and page with it, "
                                "drop answered items, then save the key (f049)"))
    page_path = find_page(st, slug, meta, page)
    page_ids: set[str] = set()
    if page_path is None or not page_path.exists():
        out.append(("FAIL", f"no study page for {slug}" + (f" at {page_path}" if page_path else "")
                    + ": every topic's checks go on a page, built in prep (f024)"))
    else:
        page_ids = ids_in(page_path.read_text(encoding="utf-8"))
    lines = [re.sub(r"~~.*?~~", "", ln) for ln in text.splitlines()]
    key_page_ids: set[str] = set()
    chat_line: dict[str, int] = {}
    for n, ln in enumerate(lines, 1):
        ids = ids_in(ln)
        bare = _NOT_CHAT.sub("", ln)
        if ids and _CHAT.search(bare):
            for i in ids:
                chat_line.setdefault(i, n)
        elif ids and _ON_PAGE.search(bare):
            key_page_ids |= ids
    reviews = [r for r in read_jsonl(st.reviews_path) if r["topic"] == slug]
    due = [r for r in reviews if r["status"] == "active" and r.get("due") and r["due"] <= day.isoformat()]
    for r in due:
        rid = r["id"]
        if rid in chat_line:
            out.append(("FAIL", f"{rid} is routed to chat (key line {chat_line[rid]}): due reviews are page boxes, "
                                "each with its own Submit (f047)"))
        elif rid not in page_ids and rid not in key_page_ids:
            out.append(("FAIL", f"{rid} is due on {day} but neither the page nor a page item in the key names it (f047)"))
        gap = (day - last_check(r)).days
        if gap < MIN_GAP_DAYS:
            out.append(("FAIL", f"{rid} was last checked {last_check(r)}, {gap} day(s) before {day}: a next-day "
                                f"duplicate; run learn.py review defer {rid} (f048, f049)"))
    due_ids = {r["id"] for r in due}
    others = {r["id"]: r for r in reviews if r["id"] not in due_ids}
    seen: set[str] = set()
    for n, ln in enumerate(lines, 1):
        for rid in sorted((ids_in(ln) & others.keys()) - seen):
            seen.add(rid)
            if not _SETTLED.search(ln):
                out.append(("WARN", f"key line {n} names {rid}, not due on {day} (due {others[rid].get('due') or 'retired'}): "
                                    "reconcile the key with log.md (f049)"))
    return out, key, page_path


def astra_review_path(st: State, slug: str, day: dt.date) -> Path:
    return st.home / "tutor-reviews" / f"{day.isoformat()}-astra-prep-{slug}.md"


def run_script(script: str, *argv: str) -> tuple[int | None, str]:
    path = SKILL_DIR / "scripts" / script
    if not path.exists():
        return None, f"{script} not found"
    try:
        res = subprocess.run([sys.executable, str(path), *argv], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        return 99, f"{script} timed out"
    return res.returncode, (res.stdout + res.stderr).strip()


def tail(text: str, n: int = 4) -> str:
    keep = [ln for ln in text.splitlines() if ln.strip()]
    hits = [ln for ln in keep if "FAIL" in ln] or keep
    return " | ".join(hits[-n:])[:600]


def ready_findings(st: State, slug: str, day: dt.date, page: str | None = None) -> tuple[list[tuple[str, str]], Path | None]:
    """The slot-readiness gate: prep-check, check_page.py, check_explanations.py, a headless render that every
    answer box got its Submit, and the Astra teaching review of the session's explanations."""
    out, _, page_path = prep_findings(st, slug, day, page)
    review = astra_review_path(st, slug, day)
    if not review.exists():
        out.append(("FAIL", f"no Astra prep review {review}: every new or changed explanation block reviewed as teaching "
                            "material (ai ask astra, uncapped) and revised (owner, 2026-11-09)"))
    else:
        rtext = review.read_text(encoding="utf-8")
        if len(rtext) < 400 or not re.search(r"(?i)\brevis", rtext):
            out.append(("FAIL", f"{review.name} must hold Astra's verdict and what was revised as a result"))
        if page_path and page_path.exists():
            blocks = re.findall(r'data-explain="([^"]+)"', page_path.read_text(encoding="utf-8"))
            missing = [b for b in blocks if b not in rtext]
            if missing:
                out.append(("WARN", f"{review.name} does not mention explanation blocks {', '.join(missing)}: fine only if "
                                    "they are unchanged since their last review"))
    if RUN_PAGE_SCRIPTS and page_path and page_path.exists():
        code, text = run_script("check_page.py", str(page_path))
        if code != 0:
            out.append(("FAIL", f"check_page.py: {tail(text) if code is not None else text}"))
        code, text = run_script("check_explanations.py", str(page_path))
        if code is None or code not in (0, 1) or "Traceback" in text:
            out.append(("WARN", f"check_explanations.py did not run cleanly (skipped): {tail(text, 2)}"))
        elif code == 1:
            out.append(("FAIL", f"check_explanations.py: {tail(text)}"))
        code, text = run_script("render_check.py", str(page_path))
        if code != 0:
            out.append(("FAIL", f"render_check.py: {tail(text) if code is not None else text}"))
    return out, page_path


def print_findings(title: str, out: list[tuple[str, str]]) -> int:
    fails = sum(1 for level, _ in out if level == "FAIL")
    print(title)
    for level, msg in out:
        print(f"  {level} {msg}")
    print(f"  {'OK' if not fails else f'{fails} FAIL'}")
    return fails


def cmd_check(st: State, args, today: dt.date) -> None:
    day = parse_day(args.date, today)
    if args.cmd == "prep-check":
        out, key, page = prep_findings(st, args.slug, day, args.page)
        fails = print_findings(f"prep-check {args.slug} {day}: key {key or '-'}; page {page or '-'}", out)
    else:
        out, page = ready_findings(st, args.slug, day, args.page)
        fails = print_findings(f"ready-check {args.slug} {day}: page {page or '-'}", out)
    if fails:
        sys.exit(1)


# ---------- calendar plan ----------

def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def at(day: dt.date, minutes: int) -> str:
    return (dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def build_plan(st: State, now: dt.datetime, days: int) -> list[dict]:
    """One event per booked session, plus one for due reviews on a day without a session, packed into
    slots. A day's due reviews ride with that day's first session."""
    today = now.date()
    topics = {s: m for s, m in st.topics().items() if m["status"] == "active"}
    reviews = [r for r in read_jsonl(st.reviews_path) if r["status"] == "active" and r["topic"] in topics]
    slots_cfg = st.slots()
    horizon = [today + dt.timedelta(days=i) for i in range(days)]

    # Demand per (day, topic). Overdue items land on today.
    demand: dict[tuple[dt.date, str], dict] = {}
    for r in reviews:
        day = max(dt.date.fromisoformat(r["due"]), today)
        if day in horizon:
            demand.setdefault((day, r["topic"]), {"reviews": [], "sessions": []})["reviews"].append(r)
    for slug, m in topics.items():
        for ns in booked(st, m):
            day = max(dt.date.fromisoformat(ns["date"]), today)
            if day in horizon:
                demand.setdefault((day, slug), {"reviews": [], "sessions": []})["sessions"].append(ns)

    events = []
    carry: list[tuple[str, dict]] = []
    for day in horizon:
        weekend = day.weekday() >= 5
        slots = [dict(s, used=0) for s in slots_cfg["weekend" if weekend else "weekday"]]
        if day == today:  # a slot that has already started is gone
            now_min = now.hour * 60 + now.minute
            slots = [s for s in slots if hm(s["start"]) > now_min]
        units = []
        for (d_day, slug), dd in sorted(demand.items(), key=lambda kv: kv[0][1]):
            if d_day == day:
                sessions = dd["sessions"] or [None]
                units += [(slug, {"reviews": dd["reviews"] if i == 0 else [], "session": ns})
                          for i, ns in enumerate(sessions)]
        todays = carry + units
        carry = []
        count: dict[str, int] = {}
        for slug, d in todays:
            n = len(d["reviews"])
            review_min = 0 if n == 0 else min(5 + 3 * n, 30 if weekend else 20)
            minutes = review_min + (d["session"]["minutes"] if d["session"] else 0)
            if (d["session"] or {}).get("at"):  # a one-off pinned time bypasses the slots
                start = hm(d["session"]["at"])
                count[slug] = count.get(slug, 0) + 1
                events.append(make_event(day, slug, topics[slug], d, start, start + minutes, count[slug]))
                continue
            # Reviews alone prefer the morning; a session uses its requested slot, else the evening.
            want = (d["session"] or {}).get("slot") or ("evening" if d["session"] else "morning")
            order = sorted(slots, key=lambda s: s["name"] != want)
            slot = next((s for s in order if hm(s["start"]) + s["used"] + minutes <= hm(s["end"])), None)
            if slot is None:
                # Too big for any slot: a session that exceeds a slot still takes the emptiest one whole.
                free = [s for s in order if s["used"] == 0]
                if d["session"] and free:
                    slot, minutes = free[0], hm(free[0]["end"]) - hm(free[0]["start"])
                else:
                    carry.append((slug, d))
                    continue
            start = hm(slot["start"]) + slot["used"]
            slot["used"] += minutes
            count[slug] = count.get(slug, 0) + 1
            events.append(make_event(day, slug, topics[slug], d, start, start + minutes, count[slug]))
    return events


def make_event(day: dt.date, slug: str, meta: dict, d: dict, start: int, end: int, n: int = 1) -> dict:
    parts = []
    if d["reviews"]:
        parts.append(f"review {len(d['reviews'])}")
    if d["session"]:
        parts.append("session")
    lines = [f"Start: say \"learn {slug}\" to Claude, Codex or pi.", ""]
    if d["session"]:
        lines += [f"Session ({d['session']['minutes']} min): {d['session']['task']}"]
        prep = d["session"].get("prep") or {"status": "pending", "note": ""}
        if prep["status"] == "blocked":
            lines.append(f"BEFORE THIS SESSION YOU MUST: {prep['note']}")
        else:
            lines.append(f"Prep: {prep['status']}" + (f" ({prep['note']})" if prep["note"] else ""))
        lines.append("")
    if d["reviews"]:
        # Counts only (lea-1, Astra review learning/tutor-reviews/2026-11-08-astra-dutch.md): a prompt shown in the
        # event lets the owner pre-think the answer and spoils cold retrieval. Prompts appear at session start.
        n_rev = len(d["reviews"])
        lines.append(f"{n_rev} review{'s' if n_rev != 1 else ''} due ({slug}) — prompts appear when the session starts;"
                     " answer cold.")
        lines.append("")
    lines.append("Short on energy? " + ("Do the first due item only." if d["reviews"] else "Do a 10-minute version.")
                 + " It still counts.")
    # The day's first event keeps the plain key, so calendars recorded before multi-booking still match.
    ev = {"key": f"{slug}:{day.isoformat()}" + (f":{n}" if n > 1 else ""), "summary": f"learn · {slug}: {' + '.join(parts)}",
          "start": at(day, start), "end": at(day, end), "description": "\n".join(lines)}
    ev["hash"] = hashlib.sha256(json.dumps([ev["summary"], ev["start"], ev["end"], ev["description"]]).encode()).hexdigest()[:16]
    return ev


def diff_plan(st: State, events: list[dict], now: dt.datetime) -> list[dict]:
    cal = read_json(st.calendar_path, {})
    actions = []
    planned = {e["key"]: e for e in events}
    for key, ev in planned.items():
        rec = cal.get(key)
        if not rec:
            actions.append({"action": "create", **ev})
        elif rec["hash"] != ev["hash"]:
            actions.append({"action": "update", "event_id": rec["event_id"], **ev})
    for key, rec in cal.items():
        # Only events still in the future are ours to remove; past ones are history.
        if key not in planned and rec.get("start", "") > now.strftime("%Y-%m-%dT%H:%M:%S"):
            actions.append({"action": "delete", "key": key, "event_id": rec["event_id"]})
    return actions


def cmd_plan(st: State, args, now: dt.datetime) -> None:
    events = build_plan(st, now, args.days)
    actions = diff_plan(st, events, now)
    # The plan is cached so `cal record` stores exactly what was sent.
    write_json(st.home / ".plan.json", {e["key"]: e for e in events})
    print(json.dumps({"now": now.isoformat(timespec="minutes"), "actions": actions,
                      "unchanged": len(events) - sum(a["action"] != "delete" for a in actions)}, indent=2, ensure_ascii=False))


def cmd_cal(st: State, args) -> None:
    cal = read_json(st.calendar_path, {})
    if args.action == "record":
        plan = read_json(st.home / ".plan.json", {})
        ev = plan.get(args.key)
        if not ev:
            sys.exit(f"{args.key} is not in the last plan; run plan first")
        cal[args.key] = {"event_id": args.event_id, "hash": ev["hash"], "start": ev["start"]}
        print(f"recorded {args.key}")
    elif args.action == "forget":
        cal.pop(args.key, None)
        print(f"forgot {args.key}")
    write_json(st.calendar_path, cal)


# ---------- status ----------

# Rules that recur but can't be checked by a script (tone, judgement). `status` prints them every session so they
# are in front of the tutor, not buried in SKILL.md. Scope: "all", a topic type, or "slug:<slug>". Ids are in
# feedback.jsonl; the ledger is references/recurring-feedback.md.
SESSION_CHECKLIST = [
    ("all", "Before the first question: ready-check passed, page republished (auto-replies armed); every answer, due reviews too, goes in a page box (f047, f056)"),
    ("all", "Open with where-we-stopped from log.md; a bare file:/// URI (+ PDF pages) whenever a step sends the owner to a source (f004, f026, f039)"),
    ("all", "On every owner message: read the page threads first, record graded items, name the next box (f053)"),
    ("all", "Example or why-it-matters first, in chat too; reasoning in words, no factoid lists (f041, f042, f057, f058)"),
    ("all", "Verdict on the core idea: a correct answer is 'right'; sharpen only with a non-obvious, goal-relevant point; no wording grading (f001, f014, f015)"),
    ("all", "Judge against what the owner had been told; check technical claims before stating them, label estimates (f011, f013, f016, f018)"),
    ("all", "Owner sets the pace; spare time or 'do it now' = run the next prepared session with its key and page (f012, f035, f036)"),
    ("all", "Slot time is for learning: no tooling or page fixes mid-slot; process changes one line at the close (f025, f056)"),
    ("all", "Owner feedback: feedback add --rule <slug>; a REPEAT gets a check, not prose (f005, f050, f059)"),
    ("slug:dutch", "Correction: hint -> owner fixes -> corrected sentence (changes bold) + why + quick check; A2 task prompts, no whole-prompt translation (f019-f021, f029, f031)"),
    ("slug:communication", "No per-turn tags; owner writes the redos; no LLM-polished lines; debrief after 3-5 exchanges (f044, f046)"),
    ("paper", "Glossary before reading; review items only from material actually worked through (f007, f027)"),
]


def checklist_for(slug: str, meta: dict) -> list[str]:
    return [text for scope, text in SESSION_CHECKLIST if scope in (meta["type"], f"slug:{slug}")]


def cmd_status(st: State, args, now: dt.datetime) -> None:
    today = parse_day(args.date, now.date())
    topics = st.topics()
    reviews = [r for r in read_jsonl(st.reviews_path) if r["status"] == "active"]
    due = [r for r in reviews if r["due"] <= today.isoformat() and (not args.topic or r["topic"] == args.topic)]
    print(f"# learn status {today.isoformat()}  ({st.home})")
    if not topics:
        print("no topics yet")
    shown = []
    for slug, m in topics.items():
        if m["status"] != "active" or (args.topic and slug != args.topic):
            continue
        shown.append(slug)
        mine = [r for r in due if r["topic"] == slug]
        print(f"\n## {slug} [{m['type']}] {m['goal']}")
        rows = booked(st, m)
        if not rows:
            print("next session: not booked")
        for ns in rows:
            when = ns.get("at") or ns.get("slot") or "evening"
            print(f"session: {ns['date']} {when} {ns['minutes']} min - {ns['task']}")
            prep = ns.get("prep") or {"status": "pending", "note": ""}
            flag = {"pending": "  <- prepare before the slot", "blocked": "  <- owner action needed"}.get(prep["status"], "")
            gate = f" [{prep['gate']}]" if prep.get("gate") else (" [gate not run]" if prep["status"] == "ready" else "")
            print(f"  prep: {prep['status']}{gate}{' - ' + prep['note'] if prep['note'] else ''}{flag}")
            if ns["date"] >= today.isoformat():
                found, _, _ = prep_findings(st, slug, dt.date.fromisoformat(ns["date"]))
                fails = [msg for level, msg in found if level == "FAIL"]
                print(f"  prep-check: " + ("ok" if not fails else f"{len(fails)} FAIL - {fails[0]}")
                      + f"  (full gate: learn.py ready-check {slug} --date {ns['date']})")
        for r in mine:
            print(f"  due {r['id']} (since {r['due']}): {r['prompt']}" + (f"  [{LEECH_NOTE}]" if r.get("leech") else ""))
        for r in reviews:
            if r["topic"] == slug and r.get("leech") and r not in mine:
                print(f"  {LEECH_NOTE} - {r['id']} (due {r['due']}): {r['prompt']}")
        for r in reviews:
            if r["topic"] == slug and r["due"] and (dt.date.fromisoformat(r["due"]) - last_check(r)).days < MIN_GAP_DAYS:
                print(f"  too soon: {r['id']} due {r['due']}, last checked {last_check(r)} -> learn.py review defer {r['id']}")
    paused = [s for s, m in topics.items() if m["status"] != "active"]
    if paused:
        print(f"\ninactive: {', '.join(paused)}")
    fb = [r for r in read_jsonl(st.feedback_path) if r["status"] == "open"]
    print(f"\nopen process feedback: {len(fb)}" + (" - review and propose skill changes" if len(fb) >= 3 else ""))
    for r in fb[-3:]:
        print(f"  {r['id']}: {r['text']}")
    pending = diff_plan(st, build_plan(st, now, 7), now)
    print(f"calendar: {'in sync' if not pending else f'{len(pending)} pending change(s) - run plan and apply'}")
    if due:
        print(f"\nshort version: {', '.join(r['id'] for r in due[:3])}")
    if shown:
        print("\n## session-start checklist (judgement rules; checked ones are in ready-check)")
        for text in checklist_for("", {"type": "all"}):
            print(f"- {text}")
        for slug in shown:
            for text in checklist_for(slug, topics[slug]):
                print(f"- [{slug}] {text}")


# ---------- selftest ----------

def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        st = State(Path(tmp))
        p = build_parser()
        now = dt.datetime(2026, 10, 30, 7, 0)  # a Friday, before the morning slot

        def run(*argv):
            dispatch(st, p.parse_args(list(argv)), now)

        run("init")
        run("topic", "new", "tabpfn", "--type", "paper", "--goal", "judge TabPFN v2")
        run("review", "add", "--topic", "tabpfn", "--prompt", "Why does the prior matter?", "--criterion", "names SCM prior", "--due", "tomorrow")
        run("review", "add", "--topic", "tabpfn", "--prompt", "When does it fail?", "--criterion", "n>10k, many features", "--due", "today")
        run("topic", "next", "tabpfn", "--date", "today", "--minutes", "45", "--task", "pass 2")
        assert "Prep: pending" in build_plan(st, now, 7)[0]["description"]
        run("topic", "prep", "tabpfn", "--status", "blocked", "--note", "accept licence")
        assert "YOU MUST: accept licence" in build_plan(st, now, 7)[0]["description"]
        run("topic", "prep", "tabpfn", "--status", "ready", "--override", "selftest: the gate has its own test")
        events = build_plan(st, now, 7)
        assert [e["key"] for e in events] == ["tabpfn:2026-10-30", "tabpfn:2026-10-31"], events
        assert events[0]["start"].endswith("20:30:00"), "session prefers the evening slot"
        assert events[1]["start"].endswith("10:00:00"), "weekend review goes to the morning"
        # lea-1: the event carries a per-topic count, never a prompt or criterion (no spoiled cold retrieval).
        assert "1 review due (tabpfn)" in events[0]["description"], events[0]["description"]
        assert all("When does it fail?" not in e["description"] and "Why does the prior matter?" not in e["description"]
                   and "names SCM" not in e["description"] for e in events), [e["description"] for e in events]
        acts = diff_plan(st, events, now)
        assert [a["action"] for a in acts] == ["create", "create"]
        run("plan")
        for a in acts:
            run("cal", "record", a["key"], "evt-" + a["key"])
        assert diff_plan(st, build_plan(st, now, 7), now) == []
        run("review", "result", "r002", "pass")
        acts = diff_plan(st, build_plan(st, now, 7), now)
        # Passing r002 (first grading, good: S0 = w2 = 2.3 days) empties today's review part (update)
        # and books it on Sunday (create). The ladder put it on Monday (+3 days).
        assert [(a["action"], a["key"]) for a in acts] == [("update", "tabpfn:2026-10-30"), ("create", "tabpfn:2026-11-01")], acts
        assert acts[0]["event_id"] == "evt-tabpfn:2026-10-30"
        rows = read_jsonl(st.reviews_path)
        assert rows[1]["due"] == "2026-11-01" and rows[1]["reps"] == 1 and rows[1]["state"] == "review", rows[1]
        run("review", "result", "r002", "fail")
        assert read_jsonl(st.reviews_path)[1]["due"] == "2026-11-01"  # MIN_GAP_DAYS: never the next day
        run("topic", "next", "tabpfn", "--date", "2026-10-31", "--minutes", "45", "--task", "pass 1", "--at", "07:45")
        sat = [e for e in build_plan(st, now, 7) if e["key"] == "tabpfn:2026-10-31"][0]
        assert sat["start"].endswith("07:45:00"), sat  # due reviews extend the end
        run("topic", "next", "tabpfn", "--date", "2026-10-31", "--minutes", "30", "--task", "eve", "--slot", "evening")
        evs = {e["key"]: e for e in build_plan(st, now, 7)}
        assert evs["tabpfn:2026-10-31"]["start"].endswith("07:45:00"), evs  # first session keeps the reviews
        assert evs["tabpfn:2026-10-31:2"]["start"].endswith("19:30:00") and "eve" in evs["tabpfn:2026-10-31:2"]["description"]
        assert "Due" not in evs["tabpfn:2026-10-31:2"]["description"]
        assert len(booked(st, st.topic("tabpfn"))) == 3
        later = dt.datetime(2026, 10, 31, 9, 0)  # after the 07:45 session: closing it books Monday
        dispatch(st, p.parse_args(["topic", "next", "tabpfn", "--date", "2026-11-02", "--minutes", "45", "--task", "mon"]), later)
        assert [ns["date"] for ns in booked(st, st.topic("tabpfn"))] == ["2026-10-31", "2026-11-02"]
        run("topic", "prep", "tabpfn", "--status", "ready", "--date", "2026-11-02", "--override", "selftest")
        assert [ns["prep"]["status"] for ns in booked(st, st.topic("tabpfn"))] == ["pending", "ready"]
        run("topic", "set", "tabpfn", "--status", "paused")
        assert all(a["action"] == "delete" for a in diff_plan(st, build_plan(st, now, 7), now))
        run("feedback", "add", "too many traps", "--source", "owner")
        run("feedback", "resolve", "f001", "--change", "cap at one")
        assert read_jsonl(st.feedback_path)[0]["status"] == "resolved"
    selftest_fsrs(p)
    selftest_feedback(p)
    selftest_gate(p)
    print("selftest ok")


def _capture(st: State, p: argparse.ArgumentParser, now: dt.datetime, *argv) -> tuple[int, str]:
    import contextlib
    import io
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            dispatch(st, p.parse_args(list(argv)), now)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if not isinstance(e.code, int) and e.code:
                print(e.code)
    return code, out.getvalue()


def selftest_feedback(p: argparse.ArgumentParser) -> None:
    """Repeat detector (owner, 2026-11-09): a repeat is flagged on add and can't be resolved with prose alone."""
    with tempfile.TemporaryDirectory() as tmp:
        st = State(Path(tmp))
        now = dt.datetime(2026, 11, 9, 9, 0)
        run = lambda *a: _capture(st, p, now, *a)
        run("init")
        code, out = run("feedback", "add", "Worked example should come before the general facts, not after.", "--rule", "example-first")
        assert code == 0 and "REPEAT" not in out, out
        # Same rule tag: a repeat whatever the wording.
        code, out = run("feedback", "add", "Motivate theory with analogues first.", "--rule", "example-first")
        assert "REPEAT of f001 (rule example-first, given 2 times)" in out, out
        # No tag, close wording: detected from the text; the rule is inherited.
        code, out = run("feedback", "add", "Per-answer Submit to tutor button on every page box, one answer at a time.", "--rule", "page-submit")
        code, out = run("feedback", "add", "Every page box needs its own Submit to tutor button, not one per page.")
        assert "REPEAT of f003 (rule page-submit, given 2 times)" in out, out
        rows = read_jsonl(st.feedback_path)
        assert rows[3]["repeat_of"] == "f003" and rows[3]["rule"] == "page-submit", rows[3]
        # Unrelated text: no repeat, asked to tag.
        code, out = run("feedback", "add", "Weekends are two sessions a day.")
        assert "REPEAT" not in out and "untagged" in out and read_jsonl(st.feedback_path)[4].get("repeat_of") is None, out
        # Resolving a repeat needs a check that exists, or a reason no check is possible.
        code, out = run("feedback", "resolve", "f004", "--change", "SKILL.md rule")
        assert code != 0 and "--check" in out and read_jsonl(st.feedback_path)[3]["status"] == "open", out
        code, out = run("feedback", "resolve", "f004", "--change", "x", "--check", "no_such_checker_zz.py")
        assert code != 0 and "does not exist" in out, out
        code, out = run("feedback", "resolve", "f004", "--change", "x", "--check", "a sentence without a script")
        assert code != 0, out
        code, out = run("feedback", "resolve", "f004", "--change", "x", "--check", "learn.py ready-check (render_check.py)")
        assert code == 0 and read_jsonl(st.feedback_path)[3]["check"].startswith("learn.py"), out
        code, out = run("feedback", "resolve", "f002", "--change", "x", "--no-check-possible", "tone; on the checklist")
        assert code == 0 and read_jsonl(st.feedback_path)[1]["no_check_possible"], out
        code, out = run("feedback", "resolve", "f005", "--change", "booked twice")  # not a repeat: prose is fine
        assert code == 0, out
        # Tagging later links a row to the earliest row of its rule.
        code, out = run("feedback", "tag", "f005", "--rule", "example-first")
        assert read_jsonl(st.feedback_path)[4]["repeat_of"] == "f001" and "given 3 times" in out, out
        code, out = run("feedback", "rules")
        assert out.splitlines()[0].startswith("example-first") and "3x" in out.splitlines()[0], out


def selftest_gate(p: argparse.ArgumentParser) -> None:
    """prep-check / ready-check and the ready gate on `topic prep` (owner, 2026-11-09, f047-f049, f056)."""
    global RUN_PAGE_SCRIPTS
    saved, RUN_PAGE_SCRIPTS = RUN_PAGE_SCRIPTS, False  # node and Chrome are tested by check_page/render_check
    try:
        with tempfile.TemporaryDirectory() as tmp:
            st = State(Path(tmp))
            now = dt.datetime(2026, 11, 9, 7, 0)
            run = lambda *a, at=now: _capture(st, p, at, *a)
            run("init")
            run("topic", "new", "pfn", "--type", "paper", "--goal", "g")
            run("topic", "next", "pfn", "--date", "2026-11-12", "--minutes", "45", "--task", "t")
            code, out = run("prep-check", "pfn", "2026-11-12")
            assert code == 1 and "no prep key" in out and "no study page" in out, out
            code, out = run("topic", "prep", "pfn", "--status", "ready")
            assert code != 0 and "not marked ready" in out, out
            assert booked(st, st.topic("pfn"))[0]["prep"]["status"] == "pending"
            d = st.topics_dir / "pfn"
            # A review made on 11-08 (fine on 11-12) and one made on 11-11 (a next-day duplicate on 11-12).
            run("review", "add", "--topic", "pfn", "--prompt", "a", "--criterion", "c", at=dt.datetime(2026, 11, 8, 20))
            run("review", "add", "--topic", "pfn", "--prompt", "b", "--criterion", "c", "--due", "2026-11-12",
                at=dt.datetime(2026, 11, 11, 20))
            run("review", "add", "--topic", "pfn", "--prompt", "z", "--criterion", "c", "--due", "2026-11-20")
            write_text(d / "prep" / "2026-11-12.tutor-only.md",
                       "# key\n## Plan\n- r001 cold, in chat\n- r003 later\n## Likely mistakes\n- x\n")
            write_text(d / "page" / "pfn.html", '<textarea data-q="Q1"></textarea>')
            code, out = run("prep-check", "pfn", "2026-11-12")
            assert "no glossary" in out and "10-minute version" in out and "file:///" in out, out
            assert "r001 is routed to chat (key line 3)" in out, out
            assert "r002 is due on 2026-11-12 but neither the page" in out, out
            assert "r002 was last checked 2026-11-11, 1 day(s) before" in out, out
            assert "WARN key line 4 names r003" in out, out
            assert "r001 was last checked" not in out, out
            # Defer the duplicate; it may not land before last check + MIN_GAP_DAYS.
            code, out = run("review", "defer", "r002", "--to", "2026-11-12")
            assert code != 0 and "not before 2026-11-13" in out, out
            code, out = run("review", "defer", "r002")
            assert code == 0 and "2026-11-13" in out, out
            write_text(d / "prep" / "2026-11-12.tutor-only.md",
                       "# key\n## Plan\n- r001 on the page as its own box (no chat)\n- ~~r003 in chat~~\n"
                       "## Glossary\n- t\n## Likely mistakes\n- x\n## Exit\nq\n## 10-minute version\nr001 only\n"
                       "Paper: file:///x/p.pdf pp. 1-3\n")
            code, out = run("prep-check", "pfn", "2026-11-12")
            assert code == 0 and "OK" in out, out
            # A log.md written after the key means the key wasn't reconciled.
            key = d / "prep" / "2026-11-12.tutor-only.md"
            os.utime(key, (key.stat().st_mtime - 3600,) * 2)
            code, out = run("prep-check", "pfn", "2026-11-12")
            assert code == 1 and "log.md changed after the key" in out, out
            os.utime(key, None)
            # ready-check adds the Astra teaching review of the session's explanations.
            code, out = run("ready-check", "pfn", "--date", "2026-11-12")
            assert code == 1 and "no Astra prep review" in out, out
            review = st.home / "tutor-reviews" / "2026-11-12-astra-prep-pfn.md"
            write_text(review, "# Astra\nok\n")
            code, out = run("ready-check", "pfn", "--date", "2026-11-12")
            assert code == 1 and "must hold Astra's verdict" in out, out
            write_text(review, "# Astra prep review\n" + "Verdict on S1: motivation first, example runs through. " * 10
                       + "\n## Revised\n- S1 opening rewritten\n")
            code, out = run("ready-check", "pfn", "--date", "2026-11-12")
            assert code == 0, out
            code, out = run("topic", "prep", "pfn", "--status", "ready", "--note", "n")
            assert code == 0 and booked(st, st.topic("pfn"))[0]["prep"]["gate"].startswith("ready-check passed"), out
            code, out = run("status")
            assert "prep-check: ok" in out and "session-start checklist" in out and "Glossary before reading" in out, out
            # Override is recorded and shown.
            review.unlink()
            code, out = run("topic", "prep", "pfn", "--status", "ready", "--override", "astra down")
            assert code == 0 and "override: astra down" in run("status")[1]
    finally:
        RUN_PAGE_SCRIPTS = saved


def selftest_fsrs(p: argparse.ArgumentParser) -> None:
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as tmp:
        st = State(Path(tmp))
        day0 = dt.date(2026, 11, 2)

        def run(day: dt.date, *argv) -> str:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                dispatch(st, p.parse_args(list(argv)), dt.datetime.combine(day, dt.time(7, 0)))
            return out.getvalue()

        def row(rid: str) -> dict:
            return next(r for r in read_jsonl(st.reviews_path) if r["id"] == rid)

        def add(kind: str = "pattern") -> str:
            return run(day0, "review", "add", "--topic", "dutch", "--prompt", "p", "--criterion", "c",
                       "--due", "today", "--kind", kind).split()[0]

        run(day0, "init")
        run(day0, "topic", "new", "dutch", "--type", "practical", "--goal", "A2")
        # The formula reproduces the published parameters: at 90% retention the interval equals S.
        assert all(abs(fsrs_interval(fsrs_init_s(g)) - FSRS_W[g - 1]) < 1e-9 for g in range(1, 5))
        assert abs(fsrs_init_d(3) - (6.4133 - math.exp(0.8334 * 2) + 1)) < 1e-9

        # First due date of a new item: never tomorrow by default (owner, 2026-11-09: r011 duplicated S1,
        # answered the evening before). 3 days from a correct answer, 2 from an error; explicit flags win.
        def due_of(*extra) -> str:
            rid = run(day0, "review", "add", "--topic", "dutch", "--prompt", "q", "--criterion", "c", *extra).split()[0]
            return row(rid)["due"]
        assert due_of() == "2026-11-05"
        assert due_of("--error", "missed one") == "2026-11-04"
        assert due_of("--error", "minor", "--first-due-days", "4") == "2026-11-06"
        assert due_of("--due", "tomorrow") == "2026-11-03"
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                p.parse_args(["review", "add", "--topic", "dutch", "--prompt", "q", "--criterion", "c",
                              "--due", "today", "--first-due-days", "3"])
            raise AssertionError("--due and --first-due-days together must be refused")
        except SystemExit:
            pass
        rows = read_jsonl(st.reviews_path)
        write_jsonl(st.reviews_path, rows[:-4])  # keep the ids below as they were

        # First review, each grade: again and hard 2 (MIN_GAP_DAYS floor; FSRS alone gives 1), good 2 days;
        # easy 8.3 days fuzzed into [6, 10].
        first = {}
        for grade in GRADES:
            rid = add()
            run(day0, "review", "result", rid, grade)
            first[grade] = row(rid)["interval"]
            assert row(rid)["history"][-1]["grade"] == grade and row(rid)["history"][-1]["elapsed_days"] == 0
        assert first["again"] == 2 and first["hard"] == 2 and first["good"] == 2 and 6 <= first["easy"] <= 10, first
        assert row("r001")["lapses"] == 0, "a fail on the first grading is not a lapse"

        # Aliases: pass = good, fail = again, recorded with both the typed outcome and the grade.
        rid = add()
        run(day0, "review", "result", rid, "pass")
        h = row(rid)["history"][-1]
        assert (h["result"], h["grade"], row(rid)["interval"]) == ("pass", "good", first["good"]), h
        run(day0 + dt.timedelta(days=2), "review", "result", rid, "fail")
        h, r = row(rid)["history"][-1], row(rid)
        assert (h["result"], h["grade"], h["elapsed_days"], r["lapses"], r["state"]) == ("fail", "again", 2, 1, "relearning"), (h, r)

        # Repeated goods on the due day: intervals grow strictly until the item retires (> 120 days).
        rid, day, ivls = add(), day0, []
        while row(rid)["status"] == "active":
            run(day, "review", "result", rid, "good")
            if row(rid)["due"]:
                ivls.append(row(rid)["interval"])
                day = dt.date.fromisoformat(row(rid)["due"])
            assert len(ivls) < 12, ivls
        assert ivls == sorted(set(ivls)) and len(ivls) >= 3 and ivls[-1] <= RETIRE_AFTER_DAYS, ivls
        assert row(rid)["due"] is None and row(rid)["history"][-1]["interval"] is None
        assert row(rid)["stability"] > RETIRE_AFTER_DAYS, row(rid)

        # A lapse (again after goods) shortens the interval well below the last one.
        rid, day = add(), day0
        for _ in range(3):
            run(day, "review", "result", rid, "good")
            day = dt.date.fromisoformat(row(rid)["due"])
        before = row(rid)["interval"]
        run(day, "review", "result", rid, "again")
        assert row(rid)["interval"] < before / 2 and row(rid)["lapses"] == 1, (before, row(rid))

        # Leech: the fourth lapse flags the item; it stays active and status and list say so.
        rid, day = add("vocab"), day0
        run(day, "review", "result", rid, "good")
        for _ in range(4):
            day = dt.date.fromisoformat(row(rid)["due"])
            assert not row(rid).get("leech")
            run(day, "review", "result", rid, "again")
        r = row(rid)
        assert r["lapses"] == 4 and r["leech"] and r["status"] == "active", r
        listing = run(day, "review", "list")
        line = next(x for x in listing.splitlines() if x.startswith(rid))
        assert "vocab" in line and LEECH_NOTE in line, listing
        assert LEECH_NOTE in run(day, "status")
        lapses = row(rid)["lapses"]
        run(day, "review", "result", rid, "again")  # a same-day re-fail in relearning is the same lapse
        assert row(rid)["lapses"] == lapses and row(rid)["history"][-1]["elapsed_days"] == 0

        # Migration of ladder-era rows (`rung`, no `stability`), on first touch only.
        old = {"topic": "dutch", "criterion": "c", "error": "", "evidence": "", "due": "2026-11-02", "status": "active"}
        rows = read_jsonl(st.reviews_path) + [
            dict(old, id="r900", prompt="old", created="2026-10-20", rung=2,
                 history=[{"date": "2026-10-23", "result": "pass", "note": ""}, {"date": "2026-10-26", "result": "pass", "note": ""}]),
            dict(old, id="r901", prompt="old2", created="2026-11-01", rung=0, history=[]),
            dict(old, id="r902", prompt="old3", created="2026-10-20", rung=0,
                 history=[{"date": "2026-10-21", "result": "pass", "note": ""}, {"date": "2026-11-01", "result": "fail", "note": ""}])]
        write_jsonl(st.reviews_path, rows)
        assert "old2" in run(day0, "review", "list")  # old rows list without conversion
        assert "stability" not in row("r900") and row("r900")["rung"] == 2
        r900 = row("r900")
        fsrs_migrate(r900)
        assert (r900["stability"], r900["state"], r900["last_review"], r900["reps"], r900["lapses"]) == (7.0, "review", "2026-10-26", 2, 0), r900
        assert r900["difficulty"] == fsrs_init_d(3) and r900["migrated_from_rung"] == 2 and "rung" not in r900
        run(day0, "review", "result", "r900", "good")  # 7 days after the last pass: on time, S grows
        r = row("r900")
        assert r["history"][-1]["elapsed_days"] == 7 and r["stability"] > 7 and r["interval"] > 7 and r["reps"] == 3, r
        assert "rung" not in r and "stability" not in row("r902"), "only the touched row is converted"
        run(day0, "review", "result", "r901", "good")  # never graded: an FSRS new card
        assert row("r901")["interval"] == first["good"] and row("r901")["reps"] == 1 and row("r901")["state"] == "review"
        r902 = row("r902")
        fsrs_migrate(r902)  # rung 0 after a fail: S0 of the last grade (again), one lapse
        assert (r902["stability"], r902["state"], r902["lapses"]) == (fsrs_init_s(1), "relearning", 1), r902


# ---------- cli ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="learn skill state")
    p.add_argument("--home", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("selftest")
    s = sub.add_parser("status"); s.add_argument("--date"); s.add_argument("--topic")
    for name in ("prep-check", "ready-check"):
        x = sub.add_parser(name); x.add_argument("slug"); x.add_argument("date", nargs="?")
        x.add_argument("--date", dest="date_opt"); x.add_argument("--page", help="the study page (default: meta page, else newest .html)")

    t = sub.add_parser("topic").add_subparsers(dest="action", required=True)
    x = t.add_parser("new"); x.add_argument("slug"); x.add_argument("--type", choices=TYPES, required=True); x.add_argument("--goal")
    x = t.add_parser("next"); x.add_argument("slug"); x.add_argument("--date", required=True)
    x.add_argument("--minutes", type=int, required=True); x.add_argument("--task", required=True)
    x.add_argument("--slot", choices=("morning", "evening"))
    x.add_argument("--at", help="pin a one-off start time HH:MM, outside the slots")
    x = t.add_parser("prep"); x.add_argument("slug"); x.add_argument("--status", choices=("ready", "blocked"), required=True); x.add_argument("--note")
    x.add_argument("--date", help="which booked session (default: the earliest)"); x.add_argument("--slot", choices=("morning", "evening"))
    x.add_argument("--override", help="mark ready although ready-check fails; recorded on the session")
    x = t.add_parser("set"); x.add_argument("slug"); x.add_argument("--status", choices=("active", "paused", "done"), required=True)
    t.add_parser("list")

    r = sub.add_parser("review").add_subparsers(dest="action", required=True)
    x = r.add_parser("add"); x.add_argument("--topic", required=True); x.add_argument("--prompt", required=True)
    x.add_argument("--criterion", required=True); x.add_argument("--error"); x.add_argument("--evidence")
    g = x.add_mutually_exclusive_group(); g.add_argument("--due")
    g.add_argument("--first-due-days", type=int, choices=range(1, 31), metavar="N",
                   help=f"days until first due (default {FIRST_DUE_DAYS}, or {FIRST_DUE_DAYS_ERROR} with --error)")
    x.add_argument("--kind", choices=KINDS, default="pattern")
    x = r.add_parser("result"); x.add_argument("id"); x.add_argument("outcome", choices=(*GRADES, *GRADE_ALIASES)); x.add_argument("--note")
    x = r.add_parser("list"); x.add_argument("--due", action="store_true"); x.add_argument("--topic")
    x = r.add_parser("defer"); x.add_argument("id"); x.add_argument("--to", help=f"new due date (>= last check + {MIN_GAP_DAYS} days)")

    x = sub.add_parser("plan"); x.add_argument("--days", type=int, default=7); x.add_argument("--now")
    c = sub.add_parser("cal").add_subparsers(dest="action", required=True)
    x = c.add_parser("record"); x.add_argument("key"); x.add_argument("event_id")
    x = c.add_parser("forget"); x.add_argument("key")

    f = sub.add_parser("feedback").add_subparsers(dest="action", required=True)
    x = f.add_parser("add"); x.add_argument("text"); x.add_argument("--source", choices=("owner", "tutor"), default="owner"); x.add_argument("--topic")
    x.add_argument("--rule", help="cluster slug (see feedback rules / references/recurring-feedback.md)")
    x = f.add_parser("list"); x.add_argument("--all", action="store_true")
    x = f.add_parser("tag"); x.add_argument("id"); x.add_argument("--rule", required=True)
    f.add_parser("rules")
    x = f.add_parser("resolve"); x.add_argument("id"); x.add_argument("--change", required=True)
    g = x.add_mutually_exclusive_group()
    g.add_argument("--check", help="the script/check that now enforces it (must name an existing file)")
    g.add_argument("--no-check-possible", help="why no script can check it (it goes on the session-start checklist)")
    return p


def dispatch(st: State, args, now: dt.datetime) -> None:
    today = now.date()
    if args.cmd == "init":
        cmd_init(st, args)
    elif args.cmd == "status":
        cmd_status(st, args, now)
    elif args.cmd in ("prep-check", "ready-check"):
        args.date = args.date or args.date_opt
        cmd_check(st, args, today)
    elif args.cmd == "topic":
        cmd_topic(st, args, now)
    elif args.cmd == "review":
        cmd_review(st, args, today)
    elif args.cmd == "feedback":
        cmd_feedback(st, args, today)
    elif args.cmd == "plan":
        cmd_plan(st, args, dt.datetime.fromisoformat(args.now) if args.now else now)
    elif args.cmd == "cal":
        cmd_cal(st, args)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.cmd == "selftest":
        selftest()
        return
    dispatch(State(args.home or DEFAULT_HOME), args, dt.datetime.now())


if __name__ == "__main__":
    main()
