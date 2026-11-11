"""Heat racing: which kind of race a session is, and which of the league's
rounds each race of a heat event is.

A heat event in iRacing runs practice and qualifying, then heats, a
consolation (last chance) race and the feature; other events have two or more
races of their own. The league's rounds for such an event (dated that day, or
the race meeting still to be run) are matched to its races in order (a round
whose name says "Heat", "Consolation" or "Feature" goes with that kind of
race first), so the overlays and boards name each race after its round and
its results go to that round.
"""

from datetime import timedelta

HEAT_KINDS = ("heat", "consolation", "feature")
# Words in a session's name or type for each kind (the consolation first:
# "last chance heat" is a consolation).
WORDS = (("consolation", ("consolation", "consi", "last chance", "lcq")), ("heat", ("heat",)),
         ("feature", ("feature", "main event")))
NOT_RACES = ("qual", "practice", "warm", "testing")


def race_kind(session):
    """"heat", "consolation" or "feature" for a heat event's races, "race" for
    any other race, "" for everything else (practice, qualifying...)."""
    stype = str((session or {}).get("SessionType", "")).lower()
    if any(w in stype for w in NOT_RACES):
        return ""
    text = f"{stype} {str(session.get('SessionName', '')).lower()}"
    for kind, words in WORDS:
        if any(w in text for w in words):
            return kind
    return "race" if "race" in stype else ""


def _kind_of_name(text):
    text = str(text or "").lower()
    return next((kind for kind, words in WORDS if any(w in text for w in words)), None)


def match_rounds(races, rounds, today, live_id="", event_key=None):
    """{session number: index into ``rounds``} for an event's races.

    ``races``: [{"num", "kind"}] in order; ``rounds``: the championship's rounds
    (``date`` "YYYY-MM-DD", ``event`` the race meeting, ``session`` the
    "subsession:session" its results came from, ``results``). Only for an
    event of several races (two or more, or heats / a consolation / a
    feature): a single race is just the season's next round.

    A race whose results went into a round (this event's) keeps that round.
    The rest are matched in order to the rounds dated today (or yesterday,
    for an event that runs past midnight); without any, to the race meeting
    of the round marked Live (``live_id``), else the first meeting with a
    round still to be run (a round of its own: it and the ones after it)."""
    if not races or (len(races) < 2 and not any(r["kind"] in HEAT_KINDS for r in races)):
        return {}
    linked = {}
    if event_key is not None:
        for i, rd in enumerate(rounds):
            num = str(rd.get("session") or "").rpartition(":")
            if num[0] == str(event_key) and num[2].isdigit():
                linked[int(num[2])] = i
    pool = _dated(rounds, today) or _meeting_of(rounds, live_id, len(races), set(linked.values()))
    out, free = {}, [i for i in pool if i not in linked.values()]

    def kind_of(i):
        return _kind_of_name(f"{rounds[i].get('name')} {rounds[i].get('event')}")

    todo = [r for r in races if r["num"] not in linked]
    kinds = list(dict.fromkeys(r["kind"] for r in races))
    if 0 < len(free) < len(todo) and len(kinds) > 1:
        # Fewer rounds than races (iRacing splits a big field into more heats,
        # and may add a consolation): a round for each kind of race. Every
        # heat in the heat round; the feature the meeting's last round; a
        # consolation the one between, if there is one. A round named for a
        # kind ("Feature") goes with it.
        # A kind with a race already in a round (heat 1's results saved): that round.
        slot = {}
        for r in races:
            if r["num"] in linked:
                slot.setdefault(r["kind"], linked[r["num"]])
        for k in kinds:
            if k not in slot:
                slot[k] = next((i for i in free if kind_of(i) == k and i not in slot.values()), None)
        rest = [i for i in free if i not in slot.values()]
        open_kinds = [k for k in kinds if slot[k] is None]
        if open_kinds and rest:
            # The race the meeting ends with gets its last round; the first kind
            # its first round; the ones between, the rounds between (if any left).
            picks = [None] * len(open_kinds)
            picks[-1] = rest[-1]
            if len(open_kinds) > 1 and len(rest) > 1:
                picks[0] = rest[0]
                middle = rest[1:-1]
                for j in range(1, len(open_kinds) - 1):
                    picks[j] = middle[j - 1] if j - 1 < len(middle) else None
            for k, i in zip(open_kinds, picks):
                slot[k] = i
        for race in races:
            if race["num"] in linked:
                out[race["num"]] = linked[race["num"]]
            elif slot.get(race["kind"]) is not None:
                out[race["num"]] = slot[race["kind"]]
        return out

    for k, race in enumerate(races):
        if race["num"] in linked:
            out[race["num"]] = linked[race["num"]]
            continue
        if not free:
            continue
        # Its own kind's round; else a round that's no kind's (Race 2); else any
        # round, but never one named for a race still to come (a second heat
        # mustn't take the Feature round: the feature would have none left).
        later = {r["kind"] for r in races[k + 1:] if r["num"] not in linked}
        same = next((i for i in free if kind_of(i) == race["kind"]), None)
        plain = next((i for i in free if _kind_of_name(rounds[i].get("name")) is None), None)
        spare = next((i for i in free if kind_of(i) not in later), None)
        pick = same if same is not None else plain if plain is not None else spare
        if pick is None:
            continue
        free.remove(pick)
        out[race["num"]] = pick
    return out


def _dated(rounds, today):
    """The rounds dated today (else yesterday)."""
    for day in (today, today - timedelta(days=1)):
        dated = [i for i, rd in enumerate(rounds) if rd.get("date") == day.isoformat()]
        if dated:
            return dated
    return []


def _meeting_of(rounds, live_id, count, linked):
    """The rounds an event is (none of them dated today): the race meeting of
    the round marked Live, else of the first round still to be run (or
    already holding one of this event's races). A round that's no meeting:
    it and the ``count`` - 1 after it."""
    start = next((i for i, rd in enumerate(rounds) if live_id and rd.get("id") == live_id), None)
    if start is None:
        start = next((i for i, rd in enumerate(rounds) if not rd.get("results") or i in linked), None)
    if start is None:
        return []
    event = rounds[start].get("event")
    if not event:
        return list(range(start, min(len(rounds), start + count)))
    first = start
    while first > 0 and rounds[first - 1].get("event") == event:
        first -= 1
    last = start
    while last + 1 < len(rounds) and rounds[last + 1].get("event") == event:
        last += 1
    return list(range(first, last + 1))


def round_title(number, name):
    """A race's name from its round: the round's own name (Round 2 if it has none)."""
    return str(name or "").strip() or f"Round {number}"
