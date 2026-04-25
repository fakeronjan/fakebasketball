"""Owner model — motivations, personalities, happiness, lifecycle events."""
from __future__ import annotations
import random
from dataclasses import dataclass, field

# ── Motivation constants ──────────────────────────────────────────────────────
MOT_MONEY      = "money"
MOT_WINNING    = "winning"
MOT_LOCAL_HERO = "local_hero"
OWNER_MOTIVATIONS = [MOT_MONEY, MOT_WINNING, MOT_LOCAL_HERO]

# ── Personality / loyalty constants ───────────────────────────────────────────
PERS_RENEGADE = "renegade"
PERS_STEADY   = "steady"
LOY_LOYAL     = "loyal"
LOY_LOW       = "low_loyalty"

# ── Threat levels ─────────────────────────────────────────────────────────────
THREAT_QUIET  = 0   # content; listed at room read, no action required
THREAT_LEAN   = 1   # unhappy; grievance surfaced at room read, no agenda item yet
THREAT_DEMAND = 2   # critical; on agenda, requires commissioner decision


def threat_label(level: int) -> str:
    return {0: "", 1: "Watching", 2: "Demanding"}[level]


def happiness_label(h: float) -> str:
    if h >= 0.75: return "Content"
    if h >= 0.55: return "Settled"
    if h >= 0.35: return "Restless"
    if h >= 0.20: return "Unhappy"
    return "Furious"


# ── Name generation ───────────────────────────────────────────────────────────

_FIRST_FEMALE = [
    "Muffy", "Blythe", "Bunny", "Constance", "Cordelia", "Daphne",
    "Eugenia", "Felicity", "Georgina", "Harriet", "Imogen", "Lavinia",
    "Millicent", "Pamela", "Penelope", "Portia", "Prudence", "Rosalind",
    "Sabrina", "Serena", "Theodora", "Vivienne", "Whitney", "Sloane",
    "Cecily", "Beatrix", "Adelaide", "Dorothea", "Winifred", "Arabella",
    "Clarissa", "Emmeline", "Fleur", "Hyacinth", "Isadora", "Josephine",
    # — added —
    "Allegra", "Anastasia", "Augusta", "Aurelia", "Belinda", "Camilla",
    "Cassandra", "Celestine", "Clementine", "Cornelia", "Elspeth", "Eustacia",
    "Evangeline", "Genevieve", "Guinevere", "Helena", "Hortensia", "Isolde",
    "Leonora", "Louisa", "Lucinda", "Madeleine", "Marguerite", "Matilda",
    "Millicent", "Minerva", "Octavia", "Ophelia", "Patience", "Philippa",
    "Rosamund", "Rowena", "Seraphina", "Thomasina", "Valentina", "Verity",
]
_FIRST_MALE = [
    "Alistair", "Archibald", "Bradford", "Brenton", "Brooks", "Chandler",
    "Chester", "Chip", "Clarence", "Clifford", "Dashiell", "Dexter",
    "Edmund", "Ellsworth", "Forbes", "Ford", "Franklin", "Frederick",
    "Garrison", "Geoffrey", "Gordon", "Graham", "Grant", "Hamilton",
    "Kip", "Montgomery", "Mortimer", "Peirce", "Prescott", "Preston",
    "Reginald", "Remington", "Rockwell", "Rutherford", "Sinclair",
    "Skip", "Spencer", "Sterling", "Thatcher", "Theodore", "Thornton",
    "Tucker", "Wellington", "Whitfield", "Winthrop", "Worth", "Barnaby",
    "Bertram", "Cabot", "Dunbar", "Fletcher", "Horace", "Jasper",
    # — added —
    "Amos", "Anson", "Aubrey", "Augustine", "Baxter", "Benedict",
    "Blaine", "Bowen", "Brewster", "Brock", "Buchanan", "Caldwell",
    "Carleton", "Clive", "Cornelius", "Crawford", "Crispin", "Dalton",
    "Deane", "Douglas", "Duncan", "Eaton", "Elliot", "Emerson",
    "Everett", "Fairfax", "Fielding", "Finley", "Gideon", "Greyson",
    "Hadley", "Hartford", "Hawthorne", "Heston", "Hollis", "Hudson",
    "Humphrey", "Huntley", "Irving", "Lawson", "Leighton", "Leland",
    "Lincoln", "Linwood", "Lloyd", "Loring", "Lowell", "Lysander",
    "Maxwell", "Merritt", "Monroe", "Munroe", "Norton", "Ogden",
    "Orson", "Oswald", "Pemberton", "Percival", "Phineas", "Porter",
    "Quincy", "Randolph", "Raymond", "Reeves", "Renfrew", "Roland",
    "Rupert", "Russell", "Sheridan", "Squire", "Stanford", "Stanton",
    "Stetson", "Stewart", "Stiles", "Taft", "Tremayne", "Vance",
    "Vickers", "Walcott", "Wallace", "Warden", "Warwick", "Webster",
    "Wellesley", "Wendell", "Whitaker", "Wilbur", "Willard", "Winchester",
]
_FIRST_SWING = [
    "Blair", "Avery", "Cameron", "Taylor", "Morgan", "Quinn",
    "Riley", "Devon", "Hayley", "Kendall", "Peyton", "Lesley",
    "Dana", "Jamie", "Lindsay", "Reese", "Sidney", "Harley",
    # — added —
    "Addison", "Ainsley", "Alex", "Ashton", "Bailey", "Berkeley",
    "Brett", "Cary", "Casey", "Dale", "Drew", "Ellery",
    "Emery", "Finley", "Hadley", "Harper", "Hollis", "Hunter",
    "Jordan", "Jules", "Lane", "Lee", "Logan", "Mackenzie",
    "Merritt", "Parker", "Piper", "Presley", "Remy", "Rowan",
    "Ryan", "Sawyer", "Skylar", "Sloane", "Stevie", "Tatum",
]
_LAST_WASP = [
    "Worthington", "Pemberton", "Ashford", "Cavendish", "Whitmore",
    "Harrington", "Aldridge", "Cromwell", "Dunmore", "Ellsworth",
    "Forsythe", "Goodwin", "Hadley", "Hartwell", "Haverford",
    "Huntington", "Lancaster", "Langford", "Merriweather", "Montague",
    "Northcott", "Radcliffe", "Remington", "Rutherford", "Sherwood",
    "Somerset", "Stanwick", "Thornton", "Vanderbilt", "Wakefield",
    "Wentworth", "Whitfield", "Wickham", "Willoughby", "Winslow",
    "Woodward", "Wyndham", "Kensington", "Blackwood", "Devereaux",
    "Collingsworth", "Fairchild", "Pennington", "Alderbrook", "Crestwood",
    # — added —
    "Abernathy", "Alcott", "Alderton", "Allenby", "Alsworth", "Amesbury",
    "Amherst", "Armitage", "Atherstone", "Atkinson", "Aylesworth", "Balfour",
    "Barrington", "Belmont", "Bexley", "Blythe", "Bostwick", "Bradshaw",
    "Bramwell", "Bridgewater", "Bromley", "Brooksfield", "Browning", "Burroughs",
    "Caldecott", "Cartwright", "Caswell", "Chatsworth", "Chilton", "Clarendon",
    "Clayborne", "Clifton", "Cliveden", "Coldwell", "Colston", "Compton",
    "Covington", "Cranston", "Cresswell", "Crofton", "Crossfield", "Dalrymple",
    "Danforth", "Davenport", "Devereux", "Dorchester", "Drayton", "Drummond",
    "Duncombe", "Dunstable", "Edgecombe", "Edgeworth", "Elmswood", "Elsworth",
    "Emsworth", "Everton", "Fairfax", "Fairweather", "Falconer", "Farnsworth",
    "Fenwick", "Fielding", "Finchley", "Fordham", "Foxcroft", "Galsworth",
    "Gatwick", "Gilmore", "Gladstone", "Glenmore", "Glenwood", "Grantham",
    "Greystone", "Grimshaw", "Grosvenor", "Halberton", "Haldane", "Halsworthy",
    "Halton", "Hampden", "Hampstead", "Hanford", "Harcourt", "Hargrave",
]
_LAST_SOUTHERN = [
    "Beaumont", "Delacroix", "Fontaine", "Landry", "Thibodaux",
    "Arceneaux", "Broussard", "Fairfax", "Beauchamp", "Chastain",
    "Belmont", "Haverhill", "Fontenot", "Robichaux", "Trosclair",
    # — added —
    "Allemand", "Ardoin", "Authement", "Badeaux", "Barrois", "Begnaud",
    "Bergeron", "Boudreaux", "Bourgeois", "Bourque", "Breaux", "Bulliard",
    "Caillouet", "Castille", "Champagne", "Chauvin", "Comeaux", "Coulon",
    "Daigle", "Dartez", "Desormeaux", "Domingue", "Doucet", "Dubois",
    "Dugas", "Duhon", "Duplechain", "Dupuis", "Falgout", "Gaspard",
    "Gautreaux", "Guidry", "Guillot", "Hebert", "Himel", "Judice",
    "LeBlanc", "Leger", "Leonards", "Louviere", "Melancon", "Menard",
    "Morvant", "Mouton", "Naquin", "Picard", "Plaisance", "Prejean",
    "Romero", "Sonnier", "Tregre", "Triche", "Troxclair", "Verret",
]
_LAST_HYPHEN = [
    "Ashford-Webb", "Cavendish-Moore", "Hartwell-Price",
    "Lancaster-Fox", "Merriweather-Chase", "Pemberton-Hall",
    "Whitmore-Banks", "Forsythe-Reed", "Rutherford-Cross",
    "Wyndham-Cole", "Langford-St. Claire", "Aldridge-Voss",
    "Somerset-Park", "Thornton-Blake", "Fairchild-Morse",
    # — added —
    "Alcott-Reeves", "Alderbrook-Grant", "Amherst-Fowler", "Armitage-Cross",
    "Balfour-Kent", "Barrington-Shaw", "Belmont-Chase", "Blackwood-Hale",
    "Blythe-Colton", "Bramwell-Price", "Bridgewater-Hunt", "Bromley-Stone",
    "Caldecott-Marsh", "Cartwright-Vane", "Chatsworth-Quinn", "Clarendon-Holt",
    "Clifton-Wren", "Compton-Drake", "Covington-Wells", "Cranston-Leigh",
    "Crofton-Miles", "Davenport-Fenn", "Devereaux-Ross", "Dorchester-Keane",
    "Drayton-Hall", "Drummond-Pell", "Edgeworth-Blaine", "Fairweather-Boyd",
    "Falconer-Greys", "Farnsworth-Lake", "Fenwick-Adair", "Fordham-Crest",
]
_SUFFIXES = ["", "", "", "", "", "Jr.", "III", "IV"]   # sparsely applied

_used_owner_names:  set[str] = set()
_used_owner_firsts: set[str] = set()   # no two active owners share a first name


def _make_owner_name() -> tuple[str, str]:
    """Return (full_name, gender). Gender is 50/50."""
    gender = random.choice(["female", "male"])
    # Fallback values in case all iterations are skipped
    first = random.choice(_FIRST_MALE if gender == "male" else _FIRST_FEMALE)
    last  = random.choice(_LAST_WASP)
    for _ in range(40):
        r = random.random()
        if r < 0.68:
            first = random.choice(_FIRST_FEMALE if gender == "female" else _FIRST_MALE)
        elif r < 0.84:
            first = random.choice(_FIRST_SWING)
        else:
            first = random.choice(_FIRST_MALE if gender == "female" else _FIRST_FEMALE)

        if first in _used_owner_firsts:
            continue

        r2 = random.random()
        if r2 < 0.62:
            last = random.choice(_LAST_WASP)
        elif r2 < 0.82:
            last = random.choice(_LAST_SOUTHERN)
        else:
            last = random.choice(_LAST_HYPHEN)

        suffix = random.choice(_SUFFIXES)
        name   = f"{first} {last}{(' ' + suffix) if suffix else ''}"
        if name not in _used_owner_names:
            _used_owner_names.add(name)
            _used_owner_firsts.add(first)
            return name, gender

    # Fallback: force a unique suffix (first name may collide in extreme cases)
    suffix = random.choice(["III", "IV", "V"])
    name = f"{first} {last} {suffix}"
    _used_owner_names.add(name)
    _used_owner_firsts.add(first)
    return name, gender


# ── Owner ─────────────────────────────────────────────────────────────────────

@dataclass
class Owner:
    name:        str
    gender:      str       # "female" | "male"
    motivation:  str       # money | winning | local_hero
    personality: str       # renegade | steady
    loyalty:     str       # loyal | low_loyalty
    competence:  float     # 0.0–1.0; hidden — affects revenue efficiency and reaction speed
    tenure_left: int       # seasons until natural ownership change event

    # Mutable state
    happiness:          float      = 0.60
    grievance:          str | None = None
    threat_level:       int        = THREAT_QUIET
    seasons_owned:      int        = 0
    relocation_blocked: int        = 0   # times commissioner denied a relocation request
    last_net_profit:    float      = 0.0
    cumulative_profit:  float      = 0.0

    # Internal escalation counter (not surfaced to player)
    _seasons_unhappy: int = field(default=0, repr=False)
    # Cooldown after an approved relocation — can't demand again until this season
    _relocation_cooldown_until: int = field(default=0, repr=False)
    # Seasons before this owner can generate another unsolicited action
    _action_cooldown: int = field(default=0, repr=False)

    # ── Display helpers ───────────────────────────────────────────────────────

    @property
    def pronoun(self) -> str:
        return "she" if self.gender == "female" else "he"

    @property
    def pronoun_pos(self) -> str:
        return "her" if self.gender == "female" else "his"

    @property
    def pronoun_cap(self) -> str:
        return "She" if self.gender == "female" else "He"

    def happiness_label(self) -> str:
        return happiness_label(self.happiness)

    def motivation_label(self) -> str:
        return {
            MOT_MONEY:      "money",
            MOT_WINNING:    "winning",
            MOT_LOCAL_HERO: "local hero",
        }.get(self.motivation, self.motivation)

    def threat_str(self) -> str:
        return threat_label(self.threat_level)

    # ── Derived stats ─────────────────────────────────────────────────────────

    @property
    def revenue_efficiency(self) -> float:
        """Fraction of gross revenue actually captured. Low competence = leakage."""
        return round(0.60 + 0.40 * self.competence, 3)   # 0.60 at floor → 1.00 at ceiling

    @property
    def lean_threshold(self) -> float:
        """Happiness below this → surface grievance (LEAN)."""
        return 0.48 if self.personality == PERS_RENEGADE else 0.40

    @property
    def demand_threshold(self) -> float:
        """Happiness below this → fast-track to DEMAND."""
        return 0.33 if self.personality == PERS_RENEGADE else 0.24

    @property
    def lean_patience(self) -> int:
        """Seasons stuck in LEAN before slow-escalating to DEMAND."""
        return 5 if self.personality == PERS_RENEGADE else 6   # was 8 — 8 seasons was nearly half a 20-season game

    # ── Threat escalation ─────────────────────────────────────────────────────

    def update_threat(self) -> None:
        """Escalate or de-escalate threat level based on happiness thresholds.

        Any season below lean_threshold increments _seasons_unhappy.
        Fast-track: drop below demand_threshold → DEMAND in 1–2 seasons.
        Slow-track: stay in lean zone → DEMAND after lean_patience seasons.
        Recovery de-escalates one level per season once happiness rises.
        """
        if self.happiness < self.lean_threshold:
            self._seasons_unhappy += 1

            if self.happiness < self.demand_threshold:
                # Fast escalation from the demand zone
                seasons_needed = 1 if self.personality == PERS_RENEGADE else 2
            else:
                # Slow escalation from the lean zone — patience runs out eventually
                seasons_needed = self.lean_patience

            if self._seasons_unhappy >= seasons_needed:
                self.threat_level = THREAT_DEMAND
            else:
                self.threat_level = max(self.threat_level, THREAT_LEAN)
        else:
            self._seasons_unhappy = max(0, self._seasons_unhappy - 1)
            # Full recovery: only clear grievance if comfortably above lean threshold
            if self.happiness >= self.lean_threshold + 0.10:
                if self.threat_level == THREAT_LEAN:
                    self.threat_level = THREAT_QUIET
                    self.grievance    = None
                elif self.threat_level == THREAT_DEMAND:
                    self.threat_level = THREAT_LEAN   # demand softens, doesn't fully resolve


# ── Generation ────────────────────────────────────────────────────────────────

def generate_owner(motivation: str | None = None,
                   small_market: bool = False) -> Owner:
    """Create a new Owner.

    small_market=True biases toward local_hero motivation.
    Large/mid markets lean money/winning.
    """
    name, gender = _make_owner_name()

    if motivation is None:
        if small_market:
            motivation = random.choices(
                [MOT_LOCAL_HERO, MOT_MONEY, MOT_WINNING],
                weights=[50, 25, 25],
            )[0]
        else:
            motivation = random.choices(
                [MOT_MONEY, MOT_WINNING, MOT_LOCAL_HERO],
                weights=[40, 40, 20],
            )[0]

    personality = random.choices([PERS_RENEGADE, PERS_STEADY], weights=[35, 65])[0]
    loyalty     = random.choices([LOY_LOYAL, LOY_LOW],         weights=[60, 40])[0]
    competence  = max(0.10, min(1.0, random.gauss(0.65, 0.20)))
    tenure_left = random.randint(15, 25)

    return Owner(
        name=name, gender=gender,
        motivation=motivation, personality=personality,
        loyalty=loyalty, competence=competence,
        tenure_left=tenure_left,
    )


def _extract_last_name(full_name: str) -> str:
    """Extract the family name from a full owner name, stripping first name and suffix."""
    parts = full_name.split()
    rest = parts[1:]   # drop first name
    if rest and rest[-1] in ("Jr.", "III", "IV", "V"):
        rest = rest[:-1]
    return " ".join(rest)


def _next_generational_suffix(name: str) -> str:
    """Return the next suffix in the generational chain."""
    parts = name.split()
    if "IV" in parts:  return "V"
    if "III" in parts: return "IV"
    return "III"


def generate_heir(parent: Owner) -> Owner:
    """Generate an heir to take over the franchise.

    Inheritance probability by motivation type:
      local_hero → 50% same type, 50% random
      money / winning → 60% same, 40% random

    Name: always inherits the parent's last name.
    35% chance of being named after the parent (same first name + escalated suffix).
    65% chance of a new first name; Jr. suffix possible but rare.

    Competence regresses toward the mean, skewed slightly negative.
    Heirs start a touch uncertain (happiness 0.55).
    """
    last_name = _extract_last_name(parent.name)
    named_after = random.random() < 0.35

    if named_after:
        parent_first = parent.name.split()[0]
        suffix = _next_generational_suffix(parent.name)
        name = f"{parent_first} {last_name} {suffix}"
        gender = parent.gender
        if name not in _used_owner_names:
            _used_owner_names.add(name)
    else:
        gender = random.choice(["female", "male"])
        name = None
        for _ in range(40):
            r = random.random()
            if r < 0.68:
                first = random.choice(_FIRST_FEMALE if gender == "female" else _FIRST_MALE)
            elif r < 0.84:
                first = random.choice(_FIRST_SWING)
            else:
                first = random.choice(_FIRST_MALE if gender == "female" else _FIRST_FEMALE)
            if first in _used_owner_firsts:
                continue
            sfx = "Jr." if random.random() < 0.15 else ""
            candidate = f"{first} {last_name}{(' ' + sfx) if sfx else ''}"
            if candidate not in _used_owner_names:
                _used_owner_names.add(candidate)
                _used_owner_firsts.add(first)
                name = candidate
                break
        if name is None:
            name = f"{first} {last_name} III"
            _used_owner_names.add(name)
            _used_owner_firsts.add(first)

    inherit_prob = 0.50 if parent.motivation == MOT_LOCAL_HERO else 0.60
    motivation   = (parent.motivation if random.random() < inherit_prob
                    else random.choice(OWNER_MOTIVATIONS))

    # Heirs are slightly more renegade (proving themselves)
    personality = random.choices([PERS_RENEGADE, PERS_STEADY], weights=[45, 55])[0]
    loyalty     = random.choices([LOY_LOYAL, LOY_LOW],         weights=[55, 45])[0]
    raw         = parent.competence + random.gauss(-0.10, 0.18)
    competence  = max(0.10, min(1.0, raw))
    tenure_left = random.randint(15, 25)

    return Owner(
        name=name, gender=gender,
        motivation=motivation, personality=personality,
        loyalty=loyalty, competence=competence,
        tenure_left=tenure_left,
        happiness=0.55,
    )


def generate_buyers(n: int = 3) -> list[Owner]:
    """Generate n candidate buyers for a franchise sale. Ensures motivation variety."""
    buyers: list[Owner] = []
    used_motivations: list[str] = []

    for _ in range(n):
        name, gender = _make_owner_name()
        # Guarantee at least one of each motivation type across the candidate pool
        if len(used_motivations) < len(OWNER_MOTIVATIONS):
            available  = [m for m in OWNER_MOTIVATIONS if m not in used_motivations]
            motivation = random.choice(available)
        else:
            motivation = random.choice(OWNER_MOTIVATIONS)
        used_motivations.append(motivation)

        personality = random.choices([PERS_RENEGADE, PERS_STEADY], weights=[35, 65])[0]
        loyalty     = random.choices([LOY_LOYAL, LOY_LOW],         weights=[60, 40])[0]
        competence  = max(0.10, min(1.0, random.gauss(0.65, 0.20)))
        tenure_left = random.randint(15, 25)

        buyers.append(Owner(
            name=name, gender=gender,
            motivation=motivation, personality=personality,
            loyalty=loyalty, competence=competence,
            tenure_left=tenure_left,
        ))
    return buyers
