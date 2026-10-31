"""Heat racing: which kind of race a session is, and which of the league's
rounds each race of a heat event is.

A heat event in iRacing runs practice and qualifying, then heats, a
consolation (last chance) race and the feature. On the day of such an event
the league's rounds dated that day are matched to its races in order (a
round whose name says "Heat", "Consolation" or "Feature" goes with that kind
of race first), so the overlays can name each race after its round and its
results go to that round.
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


def match_rounds(races, rounds, today):
    """{session number: index into ``rounds``} for a heat event's races.

    ``races``: [{"num", "kind"}] in order; ``rounds``: the championship's rounds
    (``date`` "YYYY-MM-DD"). Nothing unless it's a heat event and some rounds
    are dated today (or yesterday, for an event that runs past midnight)."""
    if not any(r["kind"] in HEAT_KINDS for r in races):
        return {}
    dated = []
    for day in (today, today - timedelta(days=1)):
        dated = [i for i, rd in enumerate(rounds) if rd.get("date") == day.isoformat()]
        if dated:
            break
    out, free = {}, list(dated)
    for race in races:
        if not free:
            break
        same = next((i for i in free if _kind_of_name(f"{rounds[i].get('name')} {rounds[i].get('event')}") == race["kind"]), None)
        pick = same if same is not None else next((i for i in free if _kind_of_name(rounds[i].get("name")) is None), free[0])
        free.remove(pick)
        out[race["num"]] = pick
    return out


def round_title(number, name):
    """A race's name from its round: the round's own name (Round 2 if it has none)."""
    return str(name or "").strip() or f"Round {number}"
