"""Coach model — archetypes, modifiers, lifecycle, and generation."""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from player import (
    _used_names,           # shared global — coaches and players never share a name
    _FIRST_MALE as _P_FIRST_MALE,
    _FIRST_FEMALE as _P_FIRST_FEMALE,
    _FIRST_SWING as _P_FIRST_SWING,
    _LAST_REAL, _LAST_STEMS, _LAST_SUFFIXES,
    MOT_WINNING, MOT_MARKET, MOT_LOYALTY,
)
from owner import (
    MOT_MONEY, MOT_WINNING as OWNER_MOT_WINNING, MOT_LOCAL_HERO,
)

# ── Archetype constants ───────────────────────────────────────────────────────

ARCH_CHEMISTRY   = "chemistry"    # culture coach — elevates team cohesion
ARCH_WHISPERER   = "star_whisperer"  # player whisperer — maximises star happiness & FA draw
ARCH_DEFENSIVE   = "defensive"    # D-first — suppresses opponent scoring
ARCH_OFFENSIVE   = "offensive"    # pace-and-space — drives run-and-gun output
ARCH_MOTIVATOR   = "motivator"    # bench / depth specialist — lifts role players

ARCHETYPES = [ARCH_CHEMISTRY, ARCH_WHISPERER, ARCH_DEFENSIVE, ARCH_OFFENSIVE, ARCH_MOTIVATOR]

ARCHETYPE_LABELS = {
    ARCH_CHEMISTRY: "Culture Coach",
    ARCH_WHISPERER: "Star Whisperer",
    ARCH_DEFENSIVE: "Defensive Mastermind",
    ARCH_OFFENSIVE: "Offensive Innovator",
    ARCH_MOTIVATOR: "Motivator",
}

# Base modifier values at rating=1.0, flexibility=0.5 (neutral)
# ortg_mod  : added to team ortg  (positive = bonus)
# drtg_mod  : added to team drtg  (negative = bonus — lower drtg is better)
# chem_scale: multiplier on chemistry bonus (1.0 = no change)
# star_hap  : flat happiness bump for elite/high players each season
# depth_hap : flat happiness bump for mid/low players each season
# fa_draw   : added to star_fa_attraction roll (0.0–0.10 range)

ARCHETYPE_MODS: dict[str, dict] = {
    ARCH_CHEMISTRY: {
        "ortg_mod":   1.0,
        "drtg_mod":  -1.0,
        "chem_scale": 1.40,
        "star_hap":   0.03,
        "depth_hap":  0.05,
        "fa_draw":    0.03,
    },
    ARCH_WHISPERER: {
        "ortg_mod":   2.0,
        "drtg_mod":   0.5,   # slight defensive indifference
        "chem_scale": 1.10,
        "star_hap":   0.08,
        "depth_hap":  0.00,
        "fa_draw":    0.06,  # trimmed from 0.08 — still best at star retention, not dominant
    },
    ARCH_DEFENSIVE: {
        "ortg_mod":  -1.0,   # sacrifice some offense
        "drtg_mod":  -3.5,
        "chem_scale": 1.10,
        "star_hap":  -0.02,  # stars chafe under rigid D schemes
        "depth_hap":  0.03,
        "fa_draw":   -0.02,
    },
    ARCH_OFFENSIVE: {
        "ortg_mod":   3.0,
        "drtg_mod":   1.0,   # defense suffers
        "chem_scale": 1.00,
        "star_hap":   0.04,
        "depth_hap":  0.01,
        "fa_draw":    0.06,  # bumped from 0.04 — stars want to play in an exciting system
    },
    ARCH_MOTIVATOR: {
        "ortg_mod":   1.0,
        "drtg_mod":  -1.0,
        "chem_scale": 1.20,
        "star_hap":   0.02,
        "depth_hap":  0.07,
        "fa_draw":    0.02,
    },
}


# ── Coach dataclass ───────────────────────────────────────────────────────────

@dataclass
class Coach:
    coach_id:            str
    name:                str
    gender:              str            # "male" | "female"
    archetype:           str
    flexibility:         float          # 0=rigid (effects amplified), 1=flexible (dampened)
    horizon:             float          # 0=win-now, 1=development-focused
    rating:              float          # hidden coaching quality 0–1
    happiness:           float = 0.70
    tenure:              int   = 0      # seasons with current team
    seasons_coached:     int   = 0      # career total
    coy_wins:            int   = 0      # career Coach of the Year awards
    hot_seat:            bool  = False
    immunity_seasons:    int   = 0      # seasons remaining where hot seat cannot be set (COY or champ win)
    championships:       int   = 0      # career championship wins
    career_wins:         int   = 0      # career regular-season wins
    career_losses:       int   = 0      # career regular-season losses
    hof_inducted:        bool  = False
    former_player:       bool  = False
    former_player_id:    str | None = None  # player_id of the playing career
    former_team_name:    str | None = None  # last team name as a player
    prev_net_rating:     float | None = None  # for COY delta computation

    # ── Pronouns ─────────────────────────────────────────────────────────────

    @property
    def pronoun(self) -> str:
        return "she" if self.gender == "female" else "he"

    @property
    def pronoun_pos(self) -> str:
        return "her" if self.gender == "female" else "his"

    @property
    def pronoun_cap(self) -> str:
        return "She" if self.gender == "female" else "He"

    @property
    def career_win_pct(self) -> float:
        total = self.career_wins + self.career_losses
        return self.career_wins / total if total else 0.0

    # ── Modifier computation ──────────────────────────────────────────────────

    def compute_modifiers(self) -> dict[str, float]:
        """Return scaled modifiers for this coach.

        Scaling axes:
          - rating   (0–1): poor coach → half effect; great coach → 1.5× effect
          - flexibility (0–1): rigid (0) amplifies archetype; flexible (1) dampens it
        """
        base = ARCHETYPE_MODS[self.archetype]
        flex_scale   = 1.35 - 0.70 * self.flexibility   # 1.35 rigid → 0.65 flexible
        rating_scale = 0.50 + self.rating                # 0.50 poor  → 1.50 great
        scale = flex_scale * rating_scale

        # COY reputation bonus: each win adds +0.02 fa_draw, capped at 3 wins
        coy_bonus = min(3, self.coy_wins) * 0.02

        return {
            "ortg_mod":   base["ortg_mod"]   * scale,
            "drtg_mod":   base["drtg_mod"]   * scale,
            "chem_scale": 1.0 + (base["chem_scale"] - 1.0) * scale,
            "star_hap":   base["star_hap"]   * scale,
            "depth_hap":  base["depth_hap"]  * scale,
            "fa_draw":    base["fa_draw"]    * scale + coy_bonus,
        }

    # ── Fit scores ────────────────────────────────────────────────────────────

    def player_fit(self, player_peak: int, player_motivation: str,
                   player_happiness: float) -> float:
        """0–1 fit score between this coach and a player profile."""
        score = 0.50
        is_star = player_peak >= 12

        if self.archetype == ARCH_WHISPERER:
            score += 0.25 if is_star else -0.10
        elif self.archetype == ARCH_DEFENSIVE:
            score -= 0.10 if is_star else 0.05   # stars chafe, role players adapt
        elif self.archetype == ARCH_OFFENSIVE:
            score += 0.15 if is_star else 0.05
        elif self.archetype == ARCH_CHEMISTRY:
            if player_motivation == MOT_LOYALTY:
                score += 0.20
            score += 0.10 if player_happiness >= 0.60 else -0.05
        elif self.archetype == ARCH_MOTIVATOR:
            score += 0.20 if player_happiness < 0.50 else 0.05   # great with unhappy players
            score += 0.15 if not is_star else 0.00

        return max(0.0, min(1.0, score))

    def owner_fit(self, owner_motivation: str, owner_patience: int) -> float:
        """0–1 fit score between this coach and an owner profile."""
        score = 0.50

        if owner_motivation == OWNER_MOT_WINNING:
            if self.archetype in (ARCH_OFFENSIVE, ARCH_WHISPERER):
                score += 0.20
            elif self.archetype == ARCH_DEFENSIVE:
                score += 0.10
            # impatient winning owners want win-now horizon
            score += 0.15 * (1.0 - self.horizon)
        elif owner_motivation == MOT_MONEY:
            if self.archetype == ARCH_CHEMISTRY:
                score += 0.15   # stable locker room = predictable revenue
            elif self.archetype == ARCH_MOTIVATOR:
                score += 0.10
        elif owner_motivation == MOT_LOCAL_HERO:
            if self.archetype in (ARCH_CHEMISTRY, ARCH_MOTIVATOR):
                score += 0.20   # community-minded coaches resonate
            score += 0.10 * self.horizon  # development-focused = building something

        # rigid coaches and impatient owners clash
        if owner_patience <= 2 and self.flexibility < 0.35:
            score -= 0.10

        return max(0.0, min(1.0, score))


# ── Name generation ───────────────────────────────────────────────────────────
# Lifer coaches draw from the player name pool (diverse basketball names) with
# a small overlay of classic/old-school coaching first names (the Van Gundys,
# Sloan types who never had notable playing careers).

_COACH_FIRST_CLASSIC = [
    # Classic coaching surnames repurposed as first names / old-school types
    "Van", "Stan", "Larry", "Lenny", "Doc", "Flip", "Del", "Nate",
    "Doug", "Mike", "Jeff", "Rick", "Phil", "Pat", "George", "Red",
    "Hubie", "Chet", "Cotton", "Tex", "Butch", "Pop", "Lloyd", "Fitch",
    "Jerry", "Don", "Eddie", "Gar", "Mo", "Wes", "Sid", "Art",
]


def _make_coach_name() -> tuple[str, str]:
    """Return (full_name, gender) for a lifer coach.

    70% draw from the player first-name pool (diverse), 30% from the classic
    coaching overlay.  Last names use the same player last-name logic.
    Guarantees uniqueness against the shared _used_names set.
    """
    gender = random.choice(["female", "male"])
    for _ in range(40):
        r_style = random.random()
        if r_style < 0.30:
            # Classic coaching type — skew male (they exist but are rare for women)
            first = random.choice(_COACH_FIRST_CLASSIC)
            if gender == "female" and random.random() < 0.70:
                first = random.choice(_P_FIRST_FEMALE)
        elif r_style < 0.80:
            first = random.choice(_P_FIRST_FEMALE if gender == "female" else _P_FIRST_MALE)
        else:
            first = random.choice(_P_FIRST_SWING)

        r2 = random.random()
        if r2 < 0.35:
            last = random.choice(_LAST_REAL)
        elif r2 < 0.80:
            last = random.choice(_LAST_STEMS) + random.choice(_LAST_SUFFIXES)
        else:
            last = (random.choice(_LAST_REAL) + "-"
                    + random.choice(_LAST_STEMS) + random.choice(_LAST_SUFFIXES))

        name = f"{first} {last}"
        if name not in _used_names:
            _used_names.add(name)
            return name, gender

    # Fallback — append a roman numeral to guarantee uniqueness
    suffix = random.choice(["II", "III", "Jr."])
    name = f"{first} {last} {suffix}"
    _used_names.add(name)
    return name, gender


_coach_id_counter = 0

def _next_coach_id() -> str:
    global _coach_id_counter
    _coach_id_counter += 1
    return f"coach_{_coach_id_counter:04d}"


def generate_coach() -> Coach:
    """Generate a lifer coach who never had a notable playing career."""
    name, gender = _make_coach_name()
    archetype    = random.choice(ARCHETYPES)
    return Coach(
        coach_id     = _next_coach_id(),
        name         = name,
        gender       = gender,
        archetype    = archetype,
        flexibility  = random.betavariate(2, 2),     # peaks near 0.5, rarely extreme
        horizon      = random.betavariate(2, 2),
        rating       = random.betavariate(2, 3),     # skews toward 0.40 (most coaches mediocre)
        happiness    = random.uniform(0.60, 0.85),
        former_player= False,
    )


def coach_from_retired_player(player_id: str, name: str, gender: str,
                               last_team_name: str) -> Coach:
    """Create a coach from a retiring player.

    The coach keeps the player's name (already in _used_names from player
    generation, so we do NOT re-add it).  Former players skew toward
    star-whisperer and chemistry archetypes — they know the locker room.
    """
    archetype = random.choices(
        ARCHETYPES,
        weights=[25, 35, 10, 15, 15],  # whisperer > chemistry > motivator > offensive > defensive
    )[0]
    return Coach(
        coach_id      = _next_coach_id(),
        name          = name,
        gender        = gender,
        archetype     = archetype,
        flexibility   = random.betavariate(2.5, 2),   # slightly less rigid than lifers
        horizon       = random.betavariate(1.5, 2.5), # former players skew win-now early
        rating        = random.betavariate(2, 2.5),   # slightly higher floor than lifers
        happiness     = random.uniform(0.65, 0.90),
        former_player = True,
        former_player_id  = player_id,
        former_team_name  = last_team_name,
    )


def generate_coaching_pool(n: int) -> list[Coach]:
    """Generate a pool of n lifer coaches for league initialization."""
    return [generate_coach() for _ in range(n)]


def generate_coaches_balanced(n: int) -> list[Coach]:
    """Generate n coaches with near-equal archetype distribution.

    Ensures no archetype exceeds ~35% or falls below ~10% of the batch,
    preventing the league from drifting into a single tactical meta at init.
    Each archetype gets a base floor of n // len(ARCHETYPES) slots; the
    remainder is distributed randomly across all archetypes.
    """
    base = n // len(ARCHETYPES)
    remainder = n % len(ARCHETYPES)
    arch_list: list[str] = []
    for arch in ARCHETYPES:
        arch_list.extend([arch] * base)
    # Distribute remainder randomly (without repeating archetypes in the tail)
    extra = random.sample(ARCHETYPES, min(remainder, len(ARCHETYPES)))
    arch_list.extend(extra)
    random.shuffle(arch_list)

    coaches: list[Coach] = []
    for arch in arch_list:
        name, gender = _make_coach_name()
        coaches.append(Coach(
            coach_id     = _next_coach_id(),
            name         = name,
            gender       = gender,
            archetype    = arch,
            flexibility  = random.betavariate(2, 2),
            horizon      = random.betavariate(2, 2),
            rating       = random.betavariate(2, 3),
            happiness    = random.uniform(0.60, 0.85),
            former_player= False,
        ))
    return coaches
