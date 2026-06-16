import math
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


def _sim_possession(strength: float) -> int:
    return math.floor(random.random() * strength)


def _eff(attacker: Team, defender: Team, cfg: Config, bonus: float = 0.0) -> float:
    """Compute effective scoring strength: attacker's offense minus defender's defense."""
    atk_excess = max(0.0, attacker.quality - cfg.min_quality)
    def_excess = max(0.0, defender.quality - cfg.min_quality)
    offense = cfg.min_quality + attacker.identity * atk_excess * cfg.O_scale
    defense = (1.0 - defender.identity) * def_excess * cfg.D_scale
    return max(cfg.min_quality, min(cfg.max_quality, offense - defense + bonus))


def play_game(home: Team, away: Team, cfg: Config, home_advantage=None) -> GameResult:
    """Simulate one game. Updates team qualities; does NOT track win/loss records."""
    ha = home_advantage if home_advantage is not None else cfg.home_advantage
    eff_home = _eff(home, away, cfg, bonus=ha)
    eff_away = _eff(away, home, cfg)

    home_score = sum(_sim_possession(eff_home) for _ in range(cfg.possessions))
    away_score = sum(_sim_possession(eff_away) for _ in range(cfg.possessions))

    # No ties — keep simulating extra possessions until decided
    while home_score == away_score:
        home_score += _sim_possession(eff_home)
        away_score += _sim_possession(eff_away)

    result = GameResult(home, away, home_score, away_score)

    result.winner.quality = min(result.winner.quality + cfg.quality_delta, cfg.max_quality)
    result.loser.quality = max(result.loser.quality - cfg.quality_delta, cfg.min_quality)

    return result


def play_series(seed1: Team, seed2: Team, cfg: Config, home_advantage=None) -> tuple[Team, list[GameResult]]:
    """Best-of-N series. seed1 has home court advantage."""
    wins_needed = cfg.series_length // 2 + 1
    pattern = _HOME_PATTERNS.get(
        cfg.series_length,
        [i % 2 == 0 for i in range(cfg.series_length)],  # alternating fallback
    )

    wins: dict[Team, int] = {seed1: 0, seed2: 0}
    games: list[GameResult] = []

    for game_num in range(cfg.series_length):
        if wins[seed1] >= wins_needed or wins[seed2] >= wins_needed:
            break
        seed1_is_home = pattern[game_num]
        home, away = (seed1, seed2) if seed1_is_home else (seed2, seed1)
        result = play_game(home, away, cfg, home_advantage=home_advantage)
        games.append(result)
        wins[result.winner] += 1

    winner = seed1 if wins[seed1] >= wins_needed else seed2
    return winner, games
