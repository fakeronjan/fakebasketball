from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import Config
from team import Team
from player import (ZONE_FT, ZONE_PAINT, ZONE_MID, ZONE_3PT, ZONES,
                    zone_dist, Player)

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


@dataclass
class PlayerGameLog:
    """Per-player stats accumulated for one game. Mutated by _credit_* helpers."""
    points:        int = 0
    fga:           int = 0   # field-goal attempts (FTs excluded)
    fgm:           int = 0   # field goals made
    fga_3:         int = 0   # 3-point attempts
    fgm_3:         int = 0   # 3-pointers made
    fta:           int = 0
    ftm:           int = 0
    poss_defended: int = 0   # possessions as primary defender
    pts_allowed:   int = 0   # points yielded while defending


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


def _pick_shooter(team: Team, cfg: Config,
                  out_players: frozenset[int] = frozenset()) -> tuple[Player | None, int]:
    """Select which player initiates this possession.

    Named-player shot weights (28/22/16%) + bench slot (34%) ensure the top-3
    account for ~66% of possessions, matching historical norms. Returns
    (None, -1) for bench possessions; bench scoring is tracked under player_id=0.
    Injured players (out_players) are excluded; their weight shifts to others naturally
    via random.choices normalization.
    """
    shot_weights = [cfg.slot_shot_star, cfg.slot_shot_costar, cfg.slot_shot_starter]
    filled = [(team.roster[i], i) for i in range(len(team.roster))
              if team.roster[i] is not None
              and team.roster[i].player_id not in out_players]

    # Choices: each named player + the bench aggregate slot
    choices = filled + [(None, -1)]
    wts     = [shot_weights[idx] for _, idx in filled] + [cfg.slot_shot_bench]

    chosen = random.choices(choices, weights=wts)[0]
    return chosen   # (Player | None, slot_idx)  — None signals a bench possession


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
) -> float:
    """Zone make-% adjusted for player quality, chemistry, era, and any bonus.

    Derivation mirrors team.compute_ratings_from_roster:
      off_adj = ortg_contrib × happiness_mult × chemistry × (1+meta) / ortg_baseline
      def_adj = drtg_contrib × chemistry × (1−meta) / drtg_baseline
              (negative for good defenders → reduces make%)
    FT shots are uncontested — def_adj is always 0 for ZONE_FT.
    prob_bonus is added after the multiplicative adjustments (home advantage, seed bonus).

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
        off_adj = (shooter.ortg_contrib * shooter.happiness_mult
                   * fatigue_off * off_chemistry * (1.0 + league_meta) / ortg_scale)

    def_adj = 0.0
    if defender and zone != ZONE_FT:
        # Fatigue weakens defense: tired defenders give up slightly more (penalty is smaller
        # than offensive — defense is more about positioning than explosiveness)
        fatigue_def = 1.0 - defender.fatigue * 0.07
        def_adj = (defender.drtg_contrib
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

    Flow: pick shooter → pick zone → match defender → roll make% → return result.

    Bench possessions (shooter=None) receive a dynamic quality bonus derived from
    owner budget, competence, and team popularity — added into prob_bonus so the
    rest of the make% computation is unchanged.
    Injured players (out_off, out_def) are excluded from shooter and defender selection.
    """
    shooter, _  = _pick_shooter(offense, cfg, out_off)
    zone        = _pick_zone(shooter)
    defender    = _pick_defender(defense, shooter, out_def)
    ortg_scale  = cfg.ortg_baseline

    shooter_id  = shooter.player_id  if shooter  else None
    defender_id = defender.player_id if defender else None

    # For bench possessions, fold team-level depth quality into the probability bonus.
    effective_bonus = prob_bonus + (_bench_quality(offense) if shooter is None else 0.0)

    s3   = cfg.meta_3pt_base_scale
    sp   = cfg.meta_paint_base_scale

    if zone == ZONE_FT:
        pct = _compute_make_pct(shooter, None, ZONE_FT,
                                off_chemistry, def_chemistry,
                                league_meta, effective_bonus, ortg_scale, s3, sp)
        ft1 = random.random() < pct
        ft2 = random.random() < pct
        ftm = int(ft1) + int(ft2)
        return PossessionResult(
            shooter_id=shooter_id, defender_id=None,
            zone=zone, made=ftm > 0, points=ftm, fta=2, ftm=ftm,
        )

    pct  = _compute_make_pct(shooter, defender, zone,
                             off_chemistry, def_chemistry,
                             league_meta, effective_bonus, ortg_scale, s3, sp)
    made = random.random() < pct
    pts  = _ZONE_PTS[zone] if made else 0
    return PossessionResult(
        shooter_id=shooter_id, defender_id=defender_id,
        zone=zone, made=made, points=pts,
    )


# ── Log credit helpers ────────────────────────────────────────────────────────

_BENCH_ID = 0   # sentinel player_id for the aggregate "rest of team" slot


def _credit_offense(logs: dict, r: PossessionResult) -> None:
    """Attribute the possession outcome to the shooter's game log.

    Bench possessions (shooter_id=None) are aggregated under player_id 0
    so the commissioner can display a 'Rest of team' line without
    individual player tracking.
    """
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


def _credit_defense(logs: dict, r: PossessionResult) -> None:
    """Record the possession against the primary defender's game log."""
    if r.defender_id is None:
        return
    log = logs.setdefault(r.defender_id, PlayerGameLog())
    log.poss_defended += 1
    log.pts_allowed   += r.points


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
    """Simulate `poss` possessions, updating logs in-place. Returns total points scored."""
    total = 0
    for _ in range(poss):
        r = _sim_possession(offense, defense, cfg,
                            off_chemistry, def_chemistry, league_meta, prob_bonus,
                            out_off, out_def)
        total += r.points
        _credit_offense(off_logs, r)
        _credit_defense(def_logs, r)
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
