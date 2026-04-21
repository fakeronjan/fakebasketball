"""Rival League — data model, generation, and lightweight simulation.

This module handles the rival league narrative system (Phase 1: Type A external
investors). The rival league does not simulate possessions — it runs on a
lightweight strength score that evolves each offseason based on commissioner
decisions and passive growth.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# ── Name pools ────────────────────────────────────────────────────────────────

_ADJECTIVES = [
    "National", "Continental", "American", "United", "Independent",
    "Professional", "Premier", "Federal", "Pacific", "Atlantic",
    "Global", "Alliance", "Unified", "New", "International",
]

_NOUNS = [
    "Basketball League", "Basketball Association", "Basketball Union",
    "Hoops League", "Basketball Conference", "Basketball Circuit",
    "Basketball Federation", "Basketball Alliance",
]

# Cities for rival league teams — separate from the main franchise pool
_RIVAL_CITIES = [
    "Memphis", "Sacramento", "San Antonio", "Denver", "Salt Lake City",
    "Portland", "Oklahoma City", "Charlotte", "Cleveland", "Indianapolis",
    "Detroit", "Minneapolis", "New Orleans", "San Diego", "Columbus",
    "Pittsburgh", "Nashville", "Raleigh", "Austin", "Tampa",
    "Kansas City", "Cincinnati", "Milwaukee", "Buffalo", "Louisville",
    "Tulsa", "Richmond", "Hartford", "Omaha", "Boise",
    "Anchorage", "Honolulu", "Albuquerque", "El Paso", "Tucson",
    "Fresno", "Bakersfield", "Stockton", "Modesto", "Spokane",
]

_RIVAL_NICKNAMES = [
    "Generals", "Travelers", "Express", "Nationals", "Stars",
    "Rangers", "Eagles", "Hawks", "Jets", "Stallions",
    "Titans", "Wolves", "Thunder", "Fury", "Bandits",
    "Outlaws", "Rebels", "Pioneers", "Colonels", "Miners",
    "Navigators", "Prospectors", "Renegades", "Marshals", "Captains",
    "Admirals", "Dukes", "Barons", "Knights", "Lancers",
    "Monarchs", "Imperials", "Centurions", "Legions", "Raiders",
]

# ── Rival player name pool (distinct from main league) ───────────────────────

_FIRST_NAMES = [
    "Rex", "Colt", "Duke", "Hank", "Clyde", "Earl", "Boyd", "Les",
    "Buck", "Dale", "Hector", "Manny", "Tito", "Orlando", "Darnell",
    "Tyrell", "Lamar", "Tremaine", "Broderick", "Cornelius", "Booker",
    "Knox", "Leandro", "Gustavo", "Rodrigo", "Marcelo", "Dante",
    "Kristoffer", "Bjorn", "Sven", "Pekka", "Arvo", "Mikko",
    "Dimitri", "Alexei", "Vitaly", "Oleg", "Ruslan", "Bogdan",
    "Zhen", "Wei", "Bao", "Yong", "Jian", "Kwame", "Seun",
    "Olumide", "Chukwu", "Emeka", "Diallo", "Moussa", "Ibrahim",
]

_LAST_NAMES = [
    "Kearns", "Bellamy", "Morrow", "Slade", "Grady", "Fenton",
    "Stout", "Crisp", "Bolden", "Thatch", "Vane", "Croft",
    "Dukes", "Raines", "Cross", "Holt", "Stride", "Kell",
    "Vargas", "Delgado", "Reyes", "Montoya", "Fuentes", "Cardenas",
    "Lindqvist", "Eriksson", "Bergman", "Holmberg", "Sundqvist",
    "Volkov", "Sorokin", "Petrov", "Nikitin", "Zhukov",
    "Tanaka", "Yamamoto", "Hashimoto", "Nakamura", "Fujiwara",
    "Diallo", "Keita", "Toure", "Kouyate", "Sissoko", "Traore",
    "Mensah", "Asante", "Boateng", "Antwi", "Owusu",
]


def _rival_player_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RivalTeam:
    city:     str
    nickname: str
    strength: float   # 0.0–1.0 — talent/establishment level
    # For Type B: links back to the defected team's ID in the commissioner's league
    original_team_id: int | None = None

    @property
    def name(self) -> str:
        return f"{self.city} {self.nickname}"


@dataclass
class RivalSeasonRecord:
    season:          int
    champion:        str                             # winning team name
    standings:       list[tuple[str, int, int]]      # (team_name, wins, losses)
    notable_players: list[tuple[str, str, float]]    # (player_name, team_name, ppg)
    strength_delta:  float                           # net strength change this offseason


@dataclass
class RivalLeague:
    name:             str
    short_name:       str       # initials: "National Basketball League" → "NBL"
    formation_type:   str       # "external" | "defection" | "walkout"
    formed_season:    int
    active:           bool

    strength:         float     # 0.0–1.0 — current establishment level
    funding:          float     # 0.0–1.0 — financial backing (hidden until revealed)
    funding_revealed: bool      # True once an intel event has surfaced funding level

    teams:            list[RivalTeam]
    season_records:   list[RivalSeasonRecord] = field(default_factory=list)

    # Intel events fired so far: (season_num, message_text)
    intel_events:     list[tuple[int, str]] = field(default_factory=list)

    # Type B: ringleader owner name and list of defected team IDs
    ringleader_owner_name: str | None       = None
    defected_team_ids:     list[int]        = field(default_factory=list)
    # Type B: names of defected teams (for display after they may be removed)
    defected_team_names:   list[str]        = field(default_factory=list)
    # Type C: player IDs who crossed the picket line (scabs)
    scab_player_ids:       list[int]        = field(default_factory=list)
    # Type C: replacement roster used during walkout season
    # list of (team_id, slot_idx, replacement_player) for restoration tracking
    replacement_rosters:   list             = field(default_factory=list)
    # Walkout state: which season the walkout is in (used for Type C offer pressure)
    walkout_season:        int              = 0

    @property
    def rival_fa_pull(self) -> float:
        """Fraction of FA pool siphoned each offseason. Scales with strength."""
        if self.formation_type == "walkout":
            return 0.0   # Type C doesn't pull from FA — players are on strike, not signing elsewhere
        return 0.05 + self.strength * 0.25   # 5% at 0, 30% at full strength

    @property
    def seasons_active(self) -> int:
        return len(self.season_records)

    @property
    def formation_label(self) -> str:
        return {
            "external":  "External Investors",
            "defection": "Owner Defection",
            "walkout":   "Player Walkout",
        }.get(self.formation_type, self.formation_type)


# ── Generation ────────────────────────────────────────────────────────────────

def _short_name(full_name: str) -> str:
    """'National Basketball League' → 'NBL'."""
    return "".join(w[0].upper() for w in full_name.split() if w[0].isalpha())


def generate_rival_name(avoid: str = "") -> str:
    """Generate a rival league name that doesn't match the main league name."""
    for _ in range(30):
        adj  = random.choice(_ADJECTIVES)
        noun = random.choice(_NOUNS)
        name = f"{adj} {noun}"
        if name.lower() != avoid.lower():
            return name
    return "Continental Basketball League"


def generate_rival_league(
    formed_season:    int,
    formation_type:   str,
    funding:          float,
    main_league_name: str      = "",
    occupied_cities:  set[str] | None = None,
    n_teams:          int      = 6,
) -> RivalLeague:
    """Construct a new rival league with generated identity and teams."""
    occupied = occupied_cities or set()
    name  = generate_rival_name(avoid=main_league_name)
    short = _short_name(name)

    avail_cities = [c for c in _RIVAL_CITIES if c not in occupied]
    random.shuffle(avail_cities)
    used_nicks: set[str] = set()
    teams: list[RivalTeam] = []
    for city in avail_cities[:n_teams]:
        nick_pool = [n for n in _RIVAL_NICKNAMES if n not in used_nicks]
        if not nick_pool:
            nick_pool = list(_RIVAL_NICKNAMES)
        nick = random.choice(nick_pool)
        used_nicks.add(nick)
        # Spread team strengths around the funding level
        t_strength = max(0.10, min(0.90, funding + random.gauss(0, 0.15)))
        teams.append(RivalTeam(city=city, nickname=nick, strength=t_strength))

    return RivalLeague(
        name=name,
        short_name=short,
        formation_type=formation_type,
        formed_season=formed_season,
        active=True,
        strength=max(0.10, funding * 0.55),   # starts modest, grows
        funding=funding,
        funding_revealed=False,
        teams=teams,
    )


def generate_defection_league(
    formed_season:    int,
    ringleader_name:  str,
    defected_teams:   list,         # list of Team objects from the commissioner's league
    main_league_name: str = "",
) -> RivalLeague:
    """Construct a Type B rival league from defecting owners' teams.

    Defected teams keep their real cities/nicknames but are RivalTeam objects
    with strength derived from their current net rating.
    """
    name  = generate_rival_name(avoid=main_league_name)
    short = _short_name(name)

    rival_teams: list[RivalTeam] = []
    defected_ids: list[int] = []
    defected_names: list[str] = []
    for team in defected_teams:
        # Map net rating (roughly −10 to +10) to 0.25–0.75 strength
        net = getattr(team, 'ortg', 110.0) - getattr(team, 'drtg', 110.0)
        t_strength = max(0.20, min(0.85, 0.50 + net * 0.02))
        rival_teams.append(RivalTeam(
            city=team.franchise.city,
            nickname=team.franchise.nickname,
            strength=t_strength,
            original_team_id=team.team_id,
        ))
        defected_ids.append(team.team_id)
        defected_names.append(team.franchise.name)

    # Type B starts strong — real teams, real rosters
    avg_strength = sum(t.strength for t in rival_teams) / max(len(rival_teams), 1)
    league_strength = min(0.75, avg_strength + 0.10)

    return RivalLeague(
        name=name,
        short_name=short,
        formation_type="defection",
        formed_season=formed_season,
        active=True,
        strength=league_strength,
        funding=0.60,        # owner-funded — assumed moderately well-funded
        funding_revealed=True,
        teams=rival_teams,
        ringleader_owner_name=ringleader_name,
        defected_team_ids=defected_ids,
        defected_team_names=defected_names,
    )


def generate_walkout_league(
    formed_season:    int,
    main_league_name: str = "",
    n_teams:          int = 6,
) -> RivalLeague:
    """Construct a Type C player circuit (barnstorming league).

    Teams are loosely city-anchored, start with moderate strength.
    The circuit naturally degrades each season without infrastructure.
    """
    name  = generate_rival_name(avoid=main_league_name)
    short = _short_name(name)

    avail_cities = list(_RIVAL_CITIES)
    random.shuffle(avail_cities)
    used_nicks: set[str] = set()
    teams: list[RivalTeam] = []
    for city in avail_cities[:n_teams]:
        nick_pool = [n for n in _RIVAL_NICKNAMES if n not in used_nicks]
        if not nick_pool:
            nick_pool = list(_RIVAL_NICKNAMES)
        nick = random.choice(nick_pool)
        used_nicks.add(nick)
        t_strength = max(0.20, min(0.75, 0.45 + random.gauss(0, 0.12)))
        teams.append(RivalTeam(city=city, nickname=nick, strength=t_strength))

    return RivalLeague(
        name=name,
        short_name=short,
        formation_type="walkout",
        formed_season=formed_season,
        active=True,
        strength=0.50,       # starts meaningful — real players are involved
        funding=0.30,        # no TV deals, weak infrastructure
        funding_revealed=True,
        teams=teams,
        walkout_season=formed_season,
    )


# ── Lightweight season simulation ─────────────────────────────────────────────

def simulate_rival_season(rival: RivalLeague, season_num: int) -> RivalSeasonRecord:
    """Generate rival standings, champion, and notable players without play-by-play."""
    if not rival.teams:
        return RivalSeasonRecord(
            season=season_num, champion="—",
            standings=[], notable_players=[], strength_delta=0.0,
        )

    # Assign win% from team strength + noise
    results: list[tuple[RivalTeam, float]] = [
        (t, max(0.0, min(1.0, t.strength + random.gauss(0, 0.12))))
        for t in rival.teams
    ]
    results.sort(key=lambda x: -x[1])

    schedule_games = 40
    standings: list[tuple[str, int, int]] = []
    for team, wpct in results:
        w = round(wpct * schedule_games)
        standings.append((team.name, w, schedule_games - w))

    # Simple bracket: top 4 teams, higher-strength team favoured
    playoff_teams = [t for t, _ in results[:4]]

    def _winner(a: RivalTeam, b: RivalTeam) -> RivalTeam:
        prob = max(0.15, min(0.85, 0.5 + (a.strength - b.strength) * 0.4))
        return a if random.random() < prob else b

    if len(playoff_teams) >= 4:
        f1 = _winner(playoff_teams[0], playoff_teams[3])
        f2 = _winner(playoff_teams[1], playoff_teams[2])
        champ = _winner(f1, f2)
    elif len(playoff_teams) >= 2:
        champ = _winner(playoff_teams[0], playoff_teams[1])
    else:
        champ = playoff_teams[0]

    # Top scorer per team (strength-scaled PPG, no roster tracking)
    notable: list[tuple[str, str, float]] = []
    for team in rival.teams:
        ppg = round(max(10.0, 16.0 + team.strength * 14.0 + random.gauss(0, 2.5)), 1)
        notable.append((_rival_player_name(), team.name, ppg))
    notable.sort(key=lambda x: -x[2])

    return RivalSeasonRecord(
        season=season_num,
        champion=champ.name,
        standings=standings,
        notable_players=notable[:3],
        strength_delta=0.0,   # filled in by league.py after applying effects
    )


# ── Intel events ─────────────────────────────────────────────────────────────

def maybe_fire_intel_event(rival: RivalLeague, season_num: int) -> str | None:
    """Return an intel message for this season (or None). Also marks funding revealed."""
    seasons_since = season_num - rival.formed_season

    # Type B: funding is already revealed; fire narrative intel about the defection
    if rival.formation_type == "defection":
        if seasons_since == 1:
            rl = rival.ringleader_owner_name or "The ringleader"
            return (f"{rl}'s league has secured venue agreements in "
                    f"{len(rival.teams)} cities. Their rosters include real talent "
                    f"from the original franchises.")
        if rival.funding_revealed and random.random() < 0.30:
            options = [
                f"Reports suggest the {rival.short_name} is actively recruiting "
                f"free agents as an alternative destination.",
                f"Attendance at {rival.short_name} games is described as "
                f"{'strong' if rival.strength > 0.5 else 'modest but growing'}.",
                f"The {rival.short_name} ownership group has rejected overtures "
                f"from your league, according to sources.",
                f"Player agents are reportedly using {rival.short_name} interest "
                f"as leverage in contract talks.",
            ]
            return random.choice(options)
        return None

    # Type C: strength is player morale and circuit viability
    if rival.formation_type == "walkout":
        if seasons_since == 1:
            return (f"Striking players have organized barnstorming events in "
                    f"{len(rival.teams)} cities. Fan interest is real but unsustained.")
        if random.random() < 0.35:
            options = [
                f"Player representatives say the strike will continue "
                f"{'indefinitely' if rival.strength > 0.45 else 'but cracks are showing'}.",
                f"The barnstorming circuit drew {'large' if rival.strength > 0.45 else 'thin'} "
                f"crowds in several markets this week.",
                f"Several fringe players have reportedly signed replacement contracts "
                f"despite union pressure.",
                f"Union leadership says players are {'unified' if rival.strength > 0.40 else 'divided'} "
                f"on return-to-play conditions.",
            ]
            return random.choice(options)
        return None

    # Type A: original intel reveal logic
    if seasons_since == 1 and not rival.funding_revealed:
        # First season: partial signal
        if rival.funding >= 0.65:
            msg = (f"The {rival.name} has secured broadcast rights in multiple markets. "
                   f"Analysts suggest significant financial backing.")
        elif rival.funding >= 0.40:
            msg = (f"The {rival.name} has signed several mid-tier free agents. "
                   f"Their financial position remains unclear.")
        else:
            msg = (f"The {rival.name} is reportedly struggling to secure stadium leases "
                   f"in several target cities.")
        return msg

    if seasons_since == 2 and not rival.funding_revealed:
        # Full reveal
        rival.funding_revealed = True
        label = funding_label(rival.funding)
        if rival.funding >= 0.65:
            msg = (f"Sources confirm the {rival.name} is {label.lower()}. "
                   f"They pose a genuine long-term threat.")
        elif rival.funding >= 0.40:
            msg = (f"Financial disclosures confirm the {rival.name} is {label.lower()}. "
                   f"A credible but limited operation.")
        else:
            msg = (f"Internal documents show the {rival.name} is {label.lower()}. "
                   f"Their runway may be short.")
        return msg

    # Occasional random intel after reveal
    if rival.funding_revealed and random.random() < 0.25:
        options = [
            f"League sources report the {rival.short_name} is {strength_label(rival.strength).lower()} "
            f"in {random.choice(rival.teams).city if rival.teams else 'several markets'}.",
            f"The {rival.short_name} has reportedly approached several players about future contracts.",
            f"A memo circulating among {rival.short_name} ownership suggests expansion plans.",
            f"Fan attendance at {rival.short_name} games is reported as "
            f"{'strong' if rival.strength > 0.5 else 'modest'}.",
        ]
        return random.choice(options)

    return None


# ── Display helpers ───────────────────────────────────────────────────────────

def strength_label(strength: float) -> str:
    if strength >= 0.70: return "Dominant"
    if strength >= 0.50: return "Established"
    if strength >= 0.30: return "Growing"
    if strength >= 0.15: return "Struggling"
    return "Collapsing"


def funding_label(funding: float) -> str:
    if funding >= 0.75: return "Flush"
    if funding >= 0.55: return "Well-funded"
    if funding >= 0.35: return "Adequate"
    return "Modest"
