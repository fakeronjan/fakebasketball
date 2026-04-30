from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import Config
from team import Team
from player import (ZONE_FT, ZONE_PAINT, ZONE_MID, ZONE_3PT, ZONES,
                    GUARD, WING, BIG, zone_dist, Player)

# Home court patterns (True = seed1/home team is home): standard playoff formats
_HOME_PATTERNS: dict[int, list[bool]] = {
    3: [True, False, True],
    5: [True, True, False, False, True],
    7: [True, True, False, False, True, False, True],
}

# ── Zone calibration ──────────────────────────────────────────────────────────
# Base make-% for a league-average shooter (ortg_contrib=0) vs league-average
# defender (drtg_contrib=0), chemistry=1.0, no bonuses.
#
# Calibrated so that a team at ortg_baseline (110 pts/100 poss) with the
# default zone mix produces ≈1.10 expected pts/possession:
#   0.10×FT(0.76×2) + 0.45×paint(0.57×2) + 0.20×mid(0.42×2) + 0.25×3pt(0.36×3)
#   = 0.152 + 0.513 + 0.168 + 0.270 = 1.103  ✓
_ZONE_BASE_PCT: dict[str, float] = {
    ZONE_FT:    0.76,   # per free-throw attempt (2 attempts per FT possession)
    ZONE_PAINT: 0.57,
    ZONE_MID:   0.42,
    ZONE_3PT:   0.36,
}

_ZONE_PTS: dict[str, int] = {
    ZONE_FT:    1,   # per FT attempt; 2 attempts per possession
    ZONE_PAINT: 2,
    ZONE_MID:   2,
    ZONE_3PT:   3,
}

# ── Turnover / steal / block / rebound rates ──────────────────────────────────
# Calibrated to NBA averages (~90 poss/team/game):
#   TOs  ~12–14/team/game  →  13% of possessions
#   STL  ~7–8/team/game    →  55% of TOs become steals
#   BLK  ~4–5/team/game    →  9% of paint FGA blocked
#   OREB ~10/team/game     →  23% of missed FGA → offensive rebound
_TO_RATE    = 0.130
_STEAL_RATE = 0.550
_BLOCK_RATE = 0.090   # paint shots only
_OREB_RATE  = 0.230   # on missed field goals (not FTs)

# Position weights for stat attribution — (Guard, Wing, Big)
_POS_TOV_WT  = {GUARD: 3, WING: 2, BIG: 2}   # guards handle the ball more
_POS_STL_WT  = {GUARD: 4, WING: 2, BIG: 1}   # guards/wings in passing lanes
_POS_BLK_WT  = {GUARD: 1, WING: 2, BIG: 5}   # bigs protect the rim
_POS_REB_WT  = {GUARD: 1, WING: 2, BIG: 4}   # bigs dominate glass

# Bench competitor weight for stat attribution — named players compete against
# a single "bench" entry so individual per-game lines reflect realistic NBA shares.
# Mirrors the offensive bench_wt = 1.75 in _pick_shooter, but scaled per stat
# category since rebounds are shared across all 10 players on the floor while
# ball-handling stays concentrated in named players.
# Targets (average-quality star): REB ~10-13, STL ~1.8, BLK ~1.5, TOV ~3.0
_BENCH_WT_TOV = 1.8    # ball handling concentrated in named players
_BENCH_WT_STL = 9.0    # steals spread across the full 5-man unit
_BENCH_WT_BLK = 7.0    # blocks spread across the full 5-man unit
_BENCH_WT_REB = 12.0   # rebounds shared across all 10 players on the floor


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class PossessionResult:
    """Outcome of one offensive possession, fully attributed to a shooter and defender."""
    shooter_id:  int | None   # player_id of the shooter  (None = empty roster)
    defender_id: int | None   # player_id of the primary defender
    zone:        str          # ZONE_FT | ZONE_PAINT | ZONE_MID | ZONE_3PT
    made:        bool
    points:      int          # 0, 1, 2, or 3
    fta:         int = 0      # free-throw attempts  (non-zero only for ZONE_FT)
    ftm:         int = 0      # free throws made
    # New: extended box-score events
    turnover:       bool     = False  # possession ended in TO before a shot
    tov_id:         int | None = None  # offensive player who turned it over
    stl_id:         int | None = None  # defensive player who stole it
    blk_id:         int | None = None  # defensive player who blocked the shot
    oreb_player_id: int | None = None  # offensive rebounder (None = defensive board)
    dreb_player_id: int | None = None  # defensive rebounder (None = offensive board)


@dataclass
class PlayerGameLog:
    """Per-player stats accumulated for one game. Mutated by _credit_* helpers."""
    points:        int = 0
    fga:           int = 0   # field-goal attempts (FTs excluded)
    fgm:           int = 0   # field goals made
    fga_3:         int = 0   # 3-point attempts
    fgm_3:         int = 0   # 3-pointers made
    fga_mid:       int = 0   # mid-range attempts
    fgm_mid:       int = 0   # mid-range makes
    fga_paint:     int = 0   # paint attempts
    fgm_paint:     int = 0   # paint makes
    fta:           int = 0
    ftm:           int = 0
    poss_defended: int = 0   # possessions as primary defender
    pts_allowed:   int = 0   # points yielded while defending
    reb:           int = 0   # total rebounds
    oreb:          int = 0   # offensive rebounds
    dreb:          int = 0   # defensive rebounds
    stl:           int = 0   # steals
    blk:           int = 0   # blocks
    tov:           int = 0   # turnovers committed


@dataclass
class GameResult:
    home:       Team
    away:       Team
    home_score: int
    away_score: int
    home_logs:  dict = field(default_factory=dict)  # player_id → PlayerGameLog
    away_logs:  dict = field(default_factory=dict)

    @property
    def winner(self) -> Team:
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> Team:
        return self.away if self.home_score > self.away_score else self.home


# ── Possession helpers ────────────────────────────────────────────────────────

# Bench players are inherently below league average (that's why they're bench players).
_BENCH_BASELINE = -0.010   # baseline make-% penalty before factor adjustments

def _bench_quality(team: Team) -> float:
    """Bench make-% modifier, in direct probability units (additive on top of zone base).

    Three factors:
      budget     — owner.last_net_profit: profitable teams invest in depth
      competence — owner.competence: smarter GMs find undervalued role players
      popularity — team.popularity: marquee programs attract quality depth;
                   crowd energy lifts bench performance

    Returns a value in roughly [−0.040, +0.020]:
      −0.040 = severely undermanned bench (broke + incompetent + unpopular)
        0.000 = neutral (avg budget, avg competence, avg popularity)
      +0.020 = elite bench depth (flush, smart GM, popular team)

    Applied as: p_make = base_zone_pct * (1 + def_adj) + bench_quality + home_bonus
    """
    owner = team.owner
    if owner is None:
        return _BENCH_BASELINE - 0.015   # no owner → minimal depth investment

    # Budget: normalize last_net_profit around break-even ($0 profit).
    # Typical range −$20M (struggling) to +$60M (thriving market).
    # Capped at ±$40M for normalization; contributes ±0.012 to make%.
    profit_norm   = max(-1.0, min(1.0, owner.last_net_profit / 40.0))
    budget_adj    = profit_norm * 0.012

    # Competence: centered at league-mean 0.65; contributes ±0.012 at extremes.
    competence_adj = (owner.competence - 0.65) * 0.040

    # Popularity: centered at 0.50; contributes ±0.006 at extremes.
    popularity_adj = (team.popularity - 0.50) * 0.012

    return _BENCH_BASELINE + budget_adj + competence_adj + popularity_adj


def _game_pace(home: Team, away: Team, cfg: Config, league_meta: float = 0.0) -> int:
    """Possessions per team: weighted toward home team's preference, shifted by era."""
    base = cfg.pace_home_weight * home.pace + (1.0 - cfg.pace_home_weight) * away.pace
    return max(50, round(base + league_meta * cfg.meta_pace_scale))


def _pick_shooter(
    team:        Team,
    cfg:         Config,
    out_players: frozenset[int] = frozenset(),
    defense:     Team | None    = None,
    out_def:     frozenset[int] = frozenset(),
    league_meta: float          = 0.0,
) -> tuple[Player | None, int]:
    """Select which player initiates this possession using dynamic usage weights.

    Weight = role_base × talent_factor × fatigue_factor × matchup_factor

    role_base: Star 1.12 / Co-Star 1.00 / Starter 0.86 (tighter spread than hard
      slots so balanced rosters stay balanced; coach mods applied multiplicatively).

    talent_factor = clamp(1.0 + 0.025 × ortg_contrib, 0.75, 1.35):
      Capped linear — elite star (+14) gets 1.35×, weak player (−10) floors at 0.75.
      Avoids exponential explosion while still creating natural heliocentric drift.

    fatigue_factor = 1 − fatigue × 0.25:
      Tired stars still play but usage bends toward fresher options.

    matchup_factor: capped at 18% suppression so elite defenders reduce usage
      without erasing stars (elite −10 defender → ×0.82 on star usage).

    bench_weight = 1.75 (coach-adjusted) — bench stays a real share of possessions.

    Returns (None, -1) for bench possessions (tracked under player_id=0).
    """
    from coach import ARCH_WHISPERER, ARCH_MOTIVATOR, ARCH_CHEMISTRY, ARCH_OFFENSIVE

    # ── Base role weights and bench ───────────────────────────────────────────
    # Index: 0=Star, 1=Co-Star, 2=Starter
    role_wts = [1.12, 1.00, 0.86]
    bench_wt = 1.75

    # ── Coach usage modifiers (multiplicative, gentle) ────────────────────────
    coach = getattr(team, 'coach', None)
    if coach is not None:
        arch = coach.archetype
        if arch == ARCH_WHISPERER:
            role_wts[0] *= 1.12   # amplify star
            role_wts[2] *= 0.94   # compress starter
            bench_wt    *= 0.92
        elif arch == ARCH_MOTIVATOR:
            role_wts[0] *= 0.96   # soften star
            role_wts[1] *= 1.06   # lift co-star
            role_wts[2] *= 1.10   # lift starter
            bench_wt    *= 1.12
        elif arch == ARCH_CHEMISTRY:
            # Smooth named-player weights 20% toward their mean
            mean = sum(role_wts) / 3
            role_wts = [0.80 * w + 0.20 * mean for w in role_wts]
        elif arch == ARCH_OFFENSIVE:
            role_wts[0] *= 1.05   # slight star/costar lift
            role_wts[1] *= 1.03
            bench_wt    *= 0.98

    # ── Likely-defender quality by position ───────────────────────────────────
    pos_def_drtg: dict[str, float] = {}
    if defense is not None:
        active_def = [p for p in defense.roster
                      if p is not None and p.player_id not in out_def]
        for pos in set(p.position for p in active_def):
            same = [p.drtg_contrib for p in active_def if p.position == pos]
            if same:
                pos_def_drtg[pos] = sum(same) / len(same)

    # ── Per-player weights ────────────────────────────────────────────────────
    filled = [(team.roster[i], i) for i in range(len(team.roster))
              if team.roster[i] is not None
              and team.roster[i].player_id not in out_players]

    wts: list[float] = []
    for player, slot_idx in filled:
        # Capped linear talent: +10 → 1.25×, +14+ caps at 1.35×, negative floors at 0.75
        talent    = max(0.75, min(1.35, 1.0 + 0.025 * player.ortg_contrib))
        # fatigue: heavy miles push usage toward fresher options
        fatigue_f = max(0.10, 1.0 - player.fatigue * 0.25)
        # matchup: elite defender (drtg_contrib ≈ −10) suppresses usage by ≤18%
        def_drtg  = pos_def_drtg.get(player.position, 0.0)
        suppression = min(0.18, max(0.0, -def_drtg) * 0.018)
        matchup_f = 1.0 - suppression

        w = role_wts[slot_idx] * talent * fatigue_f * matchup_f
        wts.append(max(0.05, w))

    choices = filled + [(None, -1)]
    wts     = wts + [max(0.10, bench_wt)]

    chosen = random.choices(choices, weights=wts)[0]
    return chosen   # (Player | None, slot_idx) — None signals a bench possession


def _pick_zone(shooter: Player | None) -> str:
    """Roll which zone this possession originates from.

    The shooter's preferred_zone biases the distribution via zone_dist().
    """
    dist = zone_dist(shooter.preferred_zone if shooter else None)  # (ft, paint, mid, 3pt)
    return random.choices(ZONES, weights=list(dist))[0]


def _pick_defender(defense: Team, shooter: Player | None,
                   out_players: frozenset[int] = frozenset()) -> Player | None:
    """Pick the primary defender, preferring a positional match to the shooter.
    Injured players (out_players) cannot defend.
    """
    defenders = [p for p in defense.roster
                 if p is not None and p.player_id not in out_players]
    if not defenders:
        return None
    if shooter is not None:
        same_pos = [p for p in defenders if p.position == shooter.position]
        if same_pos:
            return random.choice(same_pos)
    return random.choice(defenders)


def _pick_by_position(players: list[Player], weights: dict[str, int]) -> Player | None:
    """Choose a player weighted by their position. Returns None if list is empty."""
    if not players:
        return None
    wts = [weights.get(p.position, 1) for p in players]
    return random.choices(players, weights=wts)[0]


def _off_quality(player: Player) -> float:
    """Offensive quality factor — mirrors _pick_shooter's talent_factor."""
    return max(0.75, min(1.35, 1.0 + 0.025 * player.ortg_contrib))


def _def_quality(player: Player) -> float:
    """Defensive quality factor — negative drtg_contrib = elite defender = higher weight."""
    return max(0.75, min(1.35, 1.0 - 0.025 * player.drtg_contrib))


def _pick_with_bench(
    active: list[Player],
    pos_weights: dict[str, int],
    bench_weight: float,
    quality_fn,
) -> Player | None:
    """Pick from named players (position weight × quality) competing against bench.

    Returns None when the bench wins the draw — caller skips individual attribution.
    Mirrors _pick_shooter's bench_wt = 1.75 approach: quality-weighted named players
    compete against a single bench entry so per-game lines reflect realistic NBA shares.
    """
    if not active:
        return None
    wts = [pos_weights.get(p.position, 1) * quality_fn(p) for p in active]
    return random.choices(active + [None], weights=wts + [bench_weight])[0]


def _pick_ball_handler(team: Team, out_players: frozenset[int] = frozenset()) -> Player | None:
    """Pick the offensive player credited with a turnover. Guards more likely;
    quality scales with ortg_contrib (ball handlers who create more also turn it over more)."""
    active = [p for p in team.roster if p is not None and p.player_id not in out_players]
    return _pick_with_bench(active, _POS_TOV_WT, _BENCH_WT_TOV, _off_quality)


def _pick_steal_getter(team: Team, out_players: frozenset[int] = frozenset()) -> Player | None:
    """Pick the defensive player credited with a steal. Guards/wings more likely;
    quality scales with drtg_contrib (better defenders earn more steal credit)."""
    active = [p for p in team.roster if p is not None and p.player_id not in out_players]
    return _pick_with_bench(active, _POS_STL_WT, _BENCH_WT_STL, _def_quality)


def _pick_blocker(team: Team, out_players: frozenset[int] = frozenset()) -> Player | None:
    """Pick the defensive player credited with a block. Bigs dominate;
    quality scales with drtg_contrib."""
    active = [p for p in team.roster if p is not None and p.player_id not in out_players]
    return _pick_with_bench(active, _POS_BLK_WT, _BENCH_WT_BLK, _def_quality)


def _pick_rebounder(team: Team, out_players: frozenset[int] = frozenset()) -> Player | None:
    """Pick the player credited with a rebound. Bigs dominate;
    quality scales with drtg_contrib."""
    active = [p for p in team.roster if p is not None and p.player_id not in out_players]
    return _pick_with_bench(active, _POS_REB_WT, _BENCH_WT_REB, _def_quality)


def _compute_make_pct(
    shooter:      Player | None,
    defender:     Player | None,
    zone:         str,
    off_chemistry: float,
    def_chemistry: float,
    league_meta:  float = 0.0,
    prob_bonus:   float = 0.0,
    ortg_scale:   float = 110.0,
    meta_3pt_base_scale:   float = 0.0,
    meta_paint_base_scale: float = 0.0,
    coach_ortg_mod: float = 0.0,   # offensive coach system bonus (added to shooter's ortg_contrib)
    coach_drtg_mod: float = 0.0,   # defensive coach system bonus (added to defender's drtg_contrib)
) -> float:
    """Zone make-% adjusted for player quality, chemistry, era, coach system, and any bonus.

    Derivation mirrors team.compute_ratings_from_roster:
      off_adj = (ortg_contrib + coach_ortg_mod) × happiness_mult × chemistry × (1+meta) / ortg_scale
      def_adj = (drtg_contrib + coach_drtg_mod) × chemistry × (1−meta) / ortg_scale
              (negative for good defenders → reduces make%)
    FT shots are uncontested — def_adj is always 0 for ZONE_FT.
    prob_bonus is added after the multiplicative adjustments (home advantage, seed bonus).

    coach_ortg_mod / coach_drtg_mod: from coach.compute_modifiers(), in same pts/100 units
    as ortg_contrib. An Offensive Innovator adds ~+3 to every shooter's effective contrib;
    a Defensive Mastermind adds ~−3.5 to every defender's effective contrib.

    Era-driven base shift: in a 3pt era (positive meta) 3pt base% rises and paint base%
    falls; the reverse in a paint era. FT and mid remain stable.
    """
    base = _ZONE_BASE_PCT[zone]
    if zone == ZONE_3PT:
        base += league_meta * meta_3pt_base_scale
    elif zone == ZONE_PAINT:
        base -= league_meta * meta_paint_base_scale

    off_adj = 0.0
    if shooter:
        # Fatigue saps offensive effectiveness: max ~12% penalty at fatigue=1.0
        fatigue_off = 1.0 - shooter.fatigue * 0.12
        off_adj = ((shooter.ortg_contrib + coach_ortg_mod) * shooter.happiness_mult
                   * fatigue_off * off_chemistry * (1.0 + league_meta) / ortg_scale)

    def_adj = 0.0
    if defender and zone != ZONE_FT:
        # Fatigue weakens defense: tired defenders give up slightly more (penalty is smaller
        # than offensive — defense is more about positioning than explosiveness)
        fatigue_def = 1.0 - defender.fatigue * 0.07
        def_adj = ((defender.drtg_contrib + coach_drtg_mod)
                   * fatigue_def * def_chemistry * (1.0 - league_meta) / ortg_scale)

    return max(0.05, min(0.95, base * (1.0 + off_adj + def_adj) + prob_bonus))


def _sim_possession(
    offense:       Team,
    defense:       Team,
    cfg:           Config,
    off_chemistry: float,
    def_chemistry: float,
    league_meta:   float = 0.0,
    prob_bonus:    float = 0.0,
    out_off:       frozenset[int] = frozenset(),
    out_def:       frozenset[int] = frozenset(),
) -> PossessionResult:
    """Simulate one offensive possession.

    Flow:
      1. Turnover check — ~13% of possessions end before a shot.
         ~55% of TOs are steals; the rest are unforced (bad pass, travel, etc.).
      2. Shooter / zone / defender selection.
      3. Block check on paint shots (~9% of paint FGA blocked → forced miss).
      4. Shot roll.
      5. Rebound: on a miss, ~23% of FGA misses → offensive rebound flag
         (caller handles the extra possession); the rest → defensive rebound.

    Bench possessions (shooter=None) receive a dynamic quality bonus derived from
    owner budget, competence, and team popularity.
    Injured players (out_off, out_def) are excluded from all selections.
    """
    # ── Step 1: Turnover ──────────────────────────────────────────────────────
    if random.random() < _TO_RATE:
        tov_player = _pick_ball_handler(offense, out_off)
        stl_player = _pick_steal_getter(defense, out_def) if random.random() < _STEAL_RATE else None
        tov_id = tov_player.player_id if tov_player else None
        stl_id = stl_player.player_id if stl_player else None
        return PossessionResult(
            shooter_id=tov_id, defender_id=stl_id,
            zone=ZONE_PAINT, made=False, points=0,
            turnover=True, tov_id=tov_id, stl_id=stl_id,
        )

    # ── Step 2: Normal shot possession ───────────────────────────────────────
    shooter, _  = _pick_shooter(offense, cfg, out_off, defense, out_def, league_meta)
    zone        = _pick_zone(shooter)
    defender    = _pick_defender(defense, shooter, out_def)
    ortg_scale  = cfg.player_adj_scale

    shooter_id  = shooter.player_id  if shooter  else None
    defender_id = defender.player_id if defender else None

    off_coach_mod = 0.0
    def_coach_mod = 0.0
    if shooter is not None:
        off_coach = getattr(offense, 'coach', None)
        if off_coach is not None:
            off_coach_mod = off_coach.compute_modifiers()['ortg_mod']
    if defender is not None:
        def_coach = getattr(defense, 'coach', None)
        if def_coach is not None:
            def_coach_mod = def_coach.compute_modifiers()['drtg_mod']

    effective_bonus = prob_bonus + (_bench_quality(offense) if shooter is None else 0.0)
    s3 = cfg.meta_3pt_base_scale
    sp = cfg.meta_paint_base_scale

    # ── Step 2a: Free throws (no block / rebound) ─────────────────────────────
    if zone == ZONE_FT:
        pct = _compute_make_pct(shooter, None, ZONE_FT,
                                off_chemistry, def_chemistry,
                                league_meta, effective_bonus, ortg_scale, s3, sp,
                                off_coach_mod, 0.0)
        ft1 = random.random() < pct
        ft2 = random.random() < pct
        ftm = int(ft1) + int(ft2)
        return PossessionResult(
            shooter_id=shooter_id, defender_id=None,
            zone=zone, made=ftm > 0, points=ftm, fta=2, ftm=ftm,
        )

    # ── Step 3: Block check (paint shots only) ────────────────────────────────
    blk_id = None
    forced_miss = False
    if zone == ZONE_PAINT and random.random() < _BLOCK_RATE:
        blocker = _pick_blocker(defense, out_def)
        blk_id = blocker.player_id if blocker else None
        forced_miss = True

    # ── Step 4: Shot roll ────────────────────────────────────────────────────
    if forced_miss:
        made = False
    else:
        pct  = _compute_make_pct(shooter, defender, zone,
                                 off_chemistry, def_chemistry,
                                 league_meta, effective_bonus, ortg_scale, s3, sp,
                                 off_coach_mod, def_coach_mod)
        made = random.random() < pct
    pts = _ZONE_PTS[zone] if made else 0

    # ── Step 5: Rebound (on FGA misses only) ─────────────────────────────────
    oreb_id = None
    dreb_id = None
    if not made:
        if random.random() < _OREB_RATE:
            rebounder = _pick_rebounder(offense, out_off)
            oreb_id = rebounder.player_id if rebounder else None
        else:
            rebounder = _pick_rebounder(defense, out_def)
            dreb_id = rebounder.player_id if rebounder else None

    return PossessionResult(
        shooter_id=shooter_id, defender_id=defender_id,
        zone=zone, made=made, points=pts,
        blk_id=blk_id,
        oreb_player_id=oreb_id,
        dreb_player_id=dreb_id,
    )


# ── Log credit helpers ────────────────────────────────────────────────────────

_BENCH_ID = 0   # sentinel player_id for the aggregate "rest of team" slot


def _credit_offense(logs: dict, r: PossessionResult) -> None:
    """Attribute the possession outcome to the shooter's game log.

    Turnovers: credit the ball-handler with a TOV; no shot stats recorded.
    Bench possessions (shooter_id=None) are aggregated under player_id 0
    so the commissioner can display a 'Rest of team' line without
    individual player tracking.
    Offensive rebounds: credit the rebounder with OREB+REB on the same result.
    """
    if r.turnover:
        if r.tov_id is not None:
            log = logs.setdefault(r.tov_id, PlayerGameLog())
            log.tov += 1
        return   # no shot credited on a turnover

    pid = r.shooter_id if r.shooter_id is not None else _BENCH_ID
    log = logs.setdefault(pid, PlayerGameLog())
    log.points += r.points
    if r.zone == ZONE_FT:
        log.fta += r.fta
        log.ftm += r.ftm
    else:
        log.fga += 1
        if r.made:
            log.fgm += 1
        if r.zone == ZONE_3PT:
            log.fga_3 += 1
            if r.made:
                log.fgm_3 += 1
        elif r.zone == ZONE_MID:
            log.fga_mid += 1
            if r.made:
                log.fgm_mid += 1
        elif r.zone == ZONE_PAINT:
            log.fga_paint += 1
            if r.made:
                log.fgm_paint += 1

    # Offensive rebound on a miss
    if r.oreb_player_id is not None:
        oreb_log = logs.setdefault(r.oreb_player_id, PlayerGameLog())
        oreb_log.oreb += 1
        oreb_log.reb  += 1


def _credit_defense(logs: dict, r: PossessionResult) -> None:
    """Record the possession against the primary defender's game log.

    Turnovers: credit the steal to the defender if applicable; no poss/pts recorded.
    Blocks and defensive rebounds are credited from PossessionResult fields.
    """
    if r.turnover:
        if r.stl_id is not None:
            log = logs.setdefault(r.stl_id, PlayerGameLog())
            log.stl += 1
        return   # no shot defended on a turnover

    if r.defender_id is not None:
        log = logs.setdefault(r.defender_id, PlayerGameLog())
        log.poss_defended += 1
        log.pts_allowed   += r.points

    if r.blk_id is not None:
        blk_log = logs.setdefault(r.blk_id, PlayerGameLog())
        blk_log.blk += 1

    if r.dreb_player_id is not None:
        dreb_log = logs.setdefault(r.dreb_player_id, PlayerGameLog())
        dreb_log.dreb += 1
        dreb_log.reb  += 1


def _run_possessions(
    offense:       Team,
    defense:       Team,
    cfg:           Config,
    off_logs:      dict,
    def_logs:      dict,
    off_chemistry: float,
    def_chemistry: float,
    poss:          int,
    league_meta:   float,
    prob_bonus:    float,
    out_off:       frozenset[int] = frozenset(),
    out_def:       frozenset[int] = frozenset(),
) -> int:
    """Simulate `poss` possessions, updating logs in-place. Returns total points scored.

    Offensive rebounds grant one bonus possession (non-recursive — a second
    OREB on the bonus possession does not chain further).
    """
    total = 0
    for _ in range(poss):
        r = _sim_possession(offense, defense, cfg,
                            off_chemistry, def_chemistry, league_meta, prob_bonus,
                            out_off, out_def)
        total += r.points
        _credit_offense(off_logs, r)
        _credit_defense(def_logs, r)
        # Offensive rebound: grant one bonus possession without consuming the counter
        if r.oreb_player_id is not None:
            r2 = _sim_possession(offense, defense, cfg,
                                 off_chemistry, def_chemistry, league_meta, prob_bonus,
                                 out_off, out_def)
            total += r2.points
            _credit_offense(off_logs, r2)
            _credit_defense(def_logs, r2)
    return total


# ── Public game / series API ──────────────────────────────────────────────────

def play_game(home: Team, away: Team, cfg: Config,
              home_advantage: float | None = None,
              away_advantage: float = 0.0,
              league_meta: float = 0.0,
              out_home: frozenset[int] = frozenset(),
              out_away: frozenset[int] = frozenset()) -> GameResult:
    """Simulate one game. Returns a GameResult with per-player game logs.

    home_advantage: prob bonus for home-team possessions. When None, computed
                    dynamically: base + pop_scale × home.popularity, so popular
                    teams have a stronger home environment.
    away_advantage: prob bonus for away-team possessions (used for playoff seed bonuses).
    out_home / out_away: sets of player_ids who are injured/unavailable for this game.
                         Excluded from shooter selection and defender matching;
                         their possessions shift to bench and remaining rostered players.
    """
    ha = (home_advantage if home_advantage is not None
          else cfg.home_pscore_bonus_base + cfg.home_pscore_bonus_pop_scale * home.popularity)
    poss = _game_pace(home, away, cfg, league_meta)

    chem_home = home.compute_chemistry(cfg)
    chem_away = away.compute_chemistry(cfg)

    home_logs: dict = {}
    away_logs: dict = {}

    home_score = _run_possessions(home, away, cfg, home_logs, away_logs,
                                  chem_home, chem_away, poss, league_meta, ha,
                                  out_home, out_away)
    away_score = _run_possessions(away, home, cfg, away_logs, home_logs,
                                  chem_away, chem_home, poss, league_meta, away_advantage,
                                  out_away, out_home)

    # Overtime: alternate one possession each side until tie is broken
    while home_score == away_score:
        home_score += _run_possessions(home, away, cfg, home_logs, away_logs,
                                       chem_home, chem_away, 1, league_meta, ha,
                                       out_home, out_away)
        away_score += _run_possessions(away, home, cfg, away_logs, home_logs,
                                       chem_away, chem_home, 1, league_meta, away_advantage,
                                       out_away, out_home)

    return GameResult(home, away, home_score, away_score, home_logs, away_logs)


def play_series(seed1: Team, seed2: Team, cfg: Config,
                home_advantage: float | None = None,
                league_meta: float = 0.0,
                seed_bonus: float = 0.0) -> tuple[Team, list[GameResult]]:
    """Best-of-N series. seed1 has home-court advantage and an always-on seed bonus.

    seed_bonus applies to seed1's possessions regardless of home/away status.
    """
    wins_needed = cfg.series_length // 2 + 1
    ha_override = home_advantage   # None = compute dynamically per game from home team's popularity
    pattern = _HOME_PATTERNS.get(
        cfg.series_length,
        [i % 2 == 0 for i in range(cfg.series_length)],
    )

    wins:  dict[Team, int]   = {seed1: 0, seed2: 0}
    games: list[GameResult]  = []

    for game_num in range(cfg.series_length):
        if wins[seed1] >= wins_needed or wins[seed2] >= wins_needed:
            break

        seed1_is_home = pattern[game_num]
        home, away    = (seed1, seed2) if seed1_is_home else (seed2, seed1)

        # Dynamic home court: popular teams get a bigger home crowd bonus.
        # ha_override lets callers (e.g. rigged series) supply a fixed value.
        ha = (ha_override if ha_override is not None
              else cfg.home_pscore_bonus_base + cfg.home_pscore_bonus_pop_scale * home.popularity)

        # seed1 always gets seed_bonus on their possessions
        if seed1_is_home:
            home_adv = ha + seed_bonus
            away_adv = 0.0
        else:
            home_adv = ha            # seed2 gets home court
            away_adv = seed_bonus    # seed1 gets seed bonus as the away team

        result = play_game(home, away, cfg,
                           home_advantage=home_adv,
                           away_advantage=away_adv,
                           league_meta=league_meta)
        games.append(result)
        wins[result.winner] += 1

    winner = seed1 if wins[seed1] >= wins_needed else seed2
    return winner, games
