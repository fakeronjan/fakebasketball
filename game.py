import random
from dataclasses import dataclass

from config import Config
from team import Team

# Home court patterns (True = seed1/home team is home): standard playoff formats
_HOME_PATTERNS: dict[int, list[bool]] = {
    3: [True, False, True],
    5: [True, True, False, False, True],
    7: [True, True, False, False, True, False, True],
}


@dataclass
class GameResult:
    home: Team
    away: Team
    home_score: int
    away_score: int

    @property
    def winner(self) -> Team:
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> Team:
        return self.away if self.home_score > self.away_score else self.home


def _game_pace(home: Team, away: Team, cfg: Config, league_meta: float = 0.0) -> int:
    """Possessions per team: weighted toward home team's preference, shifted by era."""
    base = cfg.pace_home_weight * home.pace + (1.0 - cfg.pace_home_weight) * away.pace
    return max(50, round(base + league_meta * cfg.meta_pace_scale))


def _p_score(attacker: Team, defender: Team, cfg: Config,
             bonus: float = 0.0, league_meta: float = 0.0) -> float:
    """Probability of scoring on a given possession.

    Meta reweights how much offense vs defense matters:
    - Offensive era (meta > 0): attacker's ORtg contribution amplified,
      defender's DRtg suppression reduced. High-ORtg teams gain edge.
    - Defensive era (meta < 0): defense suppresses more, offense matters less.
    """
    e_scored    = 2.0 + attacker.style_3pt
    ortg_delta  = (1.0 + league_meta) * (attacker.ortg - cfg.ortg_baseline)
    drtg_delta  = (1.0 - league_meta) * (defender.drtg - cfg.ortg_baseline)
    raw = (cfg.ortg_baseline + ortg_delta + drtg_delta) / (100.0 * e_scored) + bonus
    return max(0.10, min(0.90, raw))


def _sim_possession(p_score: float, style_3pt: float) -> int:
    """Simulate one possession. Returns 0, 2, or 3 points."""
    if random.random() < p_score:
        return 3 if random.random() < style_3pt else 2
    return 0


def play_game(home: Team, away: Team, cfg: Config, home_advantage=None,
              league_meta: float = 0.0) -> GameResult:
    """Simulate one game. Ratings are fixed — no within-season quality drift."""
    ha   = home_advantage if home_advantage is not None else cfg.home_pscore_bonus
    ph   = _p_score(home, away, cfg, bonus=ha, league_meta=league_meta)
    pa   = _p_score(away, home, cfg, league_meta=league_meta)
    poss = _game_pace(home, away, cfg, league_meta)

    home_score = sum(_sim_possession(ph, home.style_3pt) for _ in range(poss))
    away_score = sum(_sim_possession(pa, away.style_3pt) for _ in range(poss))

    while home_score == away_score:
        home_score += _sim_possession(ph, home.style_3pt)
        away_score += _sim_possession(pa, away.style_3pt)

    return GameResult(home, away, home_score, away_score)


def play_series(seed1: Team, seed2: Team, cfg: Config, home_advantage=None,
                league_meta: float = 0.0, seed_bonus: float = 0.0) -> tuple[Team, list[GameResult]]:
    """Best-of-N series. seed1 has home court advantage and an always-on seed bonus."""
    wins_needed = cfg.series_length // 2 + 1
    ha = home_advantage if home_advantage is not None else cfg.playoff_home_pscore_bonus
    pattern = _HOME_PATTERNS.get(
        cfg.series_length,
        [i % 2 == 0 for i in range(cfg.series_length)],
    )

    wins: dict[Team, int] = {seed1: 0, seed2: 0}
    games: list[GameResult] = []

    for game_num in range(cfg.series_length):
        if wins[seed1] >= wins_needed or wins[seed2] >= wins_needed:
            break
        seed1_is_home = pattern[game_num]
        home, away = (seed1, seed2) if seed1_is_home else (seed2, seed1)

        home_bonus = ha + (seed_bonus if home is seed1 else 0)
        away_bonus = seed_bonus if away is seed1 else 0

        ph   = _p_score(home, away, cfg, bonus=home_bonus, league_meta=league_meta)
        pa   = _p_score(away, home, cfg, bonus=away_bonus, league_meta=league_meta)
        poss = _game_pace(home, away, cfg, league_meta)

        home_score = sum(_sim_possession(ph, home.style_3pt) for _ in range(poss))
        away_score = sum(_sim_possession(pa, away.style_3pt) for _ in range(poss))
        while home_score == away_score:
            home_score += _sim_possession(ph, home.style_3pt)
            away_score += _sim_possession(pa, away.style_3pt)

        result = GameResult(home, away, home_score, away_score)
        games.append(result)
        wins[result.winner] += 1

    winner = seed1 if wins[seed1] >= wins_needed else seed2
    return winner, games
