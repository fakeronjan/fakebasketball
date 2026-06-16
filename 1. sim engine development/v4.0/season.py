import random
from dataclasses import dataclass

from config import Config
from game import GameResult, play_game, play_series
from team import Team


def _playoff_count(n_teams: int) -> int:
    """Dynamic playoff bracket size based on league size."""
    if n_teams >= 24:
        return 16
    elif n_teams >= 14:
        return 8
    else:
        return 4


def _games_per_pair(n_teams: int, target: int = 40) -> int:
    """Number of times each unordered pair plays (always even, min 2).

    Chooses the even number closest to target / (n_teams - 1).
    With 8 teams → 6 (42 games), 12 → 4 (44), 16 → 2 (30), 20 → 2 (38), 32 → 2 (62).
    """
    opponents = n_teams - 1
    raw = target / opponents
    x = max(2, round(raw / 2) * 2)
    return x


def _generate_schedule(teams: list[Team]) -> list[tuple[Team, Team]]:
    """Each pair plays _games_per_pair times, split evenly home/away."""
    reps = _games_per_pair(len(teams)) // 2   # times each ordered pair appears
    matchups = [
        (home, away)
        for _ in range(reps)
        for home in teams
        for away in teams
        if home is not away
    ]
    random.shuffle(matchups)
    return matchups


def _round_name(n_remaining: int) -> str:
    return {2: "Finals", 4: "Semifinals", 8: "Quarterfinals", 16: "Round of 16"}.get(
        n_remaining, f"Round of {n_remaining}"
    )


def _round_labels(n_rounds: int) -> list[str]:
    """Short labels for each round, earliest first."""
    if n_rounds == 2:
        return ["SF", "Finals"]
    elif n_rounds == 3:
        return ["QF", "SF", "Finals"]
    elif n_rounds == 4:
        return ["R16", "QF", "SF", "Finals"]
    else:
        return [f"R{2 ** (n_rounds - i)}" for i in range(n_rounds - 1)] + ["Finals"]


@dataclass
class PlayoffSeries:
    seed1: Team
    seed2: Team
    winner: Team
    games: list[GameResult]

    @property
    def seed1_wins(self) -> int:
        return sum(1 for g in self.games if g.winner is self.seed1)

    @property
    def seed2_wins(self) -> int:
        return sum(1 for g in self.games if g.winner is self.seed2)


class Season:
    def __init__(self, number: int, teams: list[Team], cfg: Config, league_meta: float = 0.0):
        self.number = number
        self.teams = teams
        self.cfg = cfg
        self.league_meta = league_meta
        self.playoff_teams: int = _playoff_count(len(teams))
        self.meta_shock: bool = False   # set True if a rule-change shock fires this offseason

        self._wins: dict[Team, int] = {t: 0 for t in teams}
        self._losses: dict[Team, int] = {t: 0 for t in teams}
        # Snapshot quality + identity before any games drift them
        self._start_ratings: dict[Team, tuple[float, float]] = {
            t: (t.quality, t.identity) for t in teams
        }

        self.regular_season_games: list[GameResult] = []
        self.regular_season_standings: list[Team] = []  # snapshot after regular season
        self.playoff_rounds: list[list[PlayoffSeries]] = []
        self.champion: Team | None = None

    # -- Record helpers -------------------------------------------------------

    def wins(self, team: Team) -> int:
        return self._wins[team]

    def losses(self, team: Team) -> int:
        return self._losses[team]

    def win_pct(self, team: Team) -> float:
        total = self._wins[team] + self._losses[team]
        return self._wins[team] / total if total > 0 else 0.5

    def _record(self, result: GameResult) -> None:
        self._wins[result.winner] += 1
        self._losses[result.loser] += 1

    def standings(self) -> list[Team]:
        return sorted(
            self.teams,
            key=lambda t: (self.win_pct(t), t.quality),
            reverse=True,
        )

    # -- Simulation -----------------------------------------------------------

    def reg_wins(self, team: Team) -> int:
        return self._reg_wins.get(team, 0)

    def reg_losses(self, team: Team) -> int:
        return self._reg_losses.get(team, 0)

    def reg_win_pct(self, team: Team) -> float:
        total = self.reg_wins(team) + self.reg_losses(team)
        return self.reg_wins(team) / total if total > 0 else 0.5

    def team_ppg(self, team: Team) -> float:
        """Average points scored per regular season game."""
        points = sum(
            g.home_score if g.home is team else g.away_score
            for g in self.regular_season_games
            if g.home is team or g.away is team
        )
        games = self.reg_wins(team) + self.reg_losses(team)
        return points / games if games > 0 else 0.0

    def league_avg_ppg(self) -> float:
        """League-wide average points per team per game."""
        if not self.regular_season_games:
            return 0.0
        total = sum(g.home_score + g.away_score for g in self.regular_season_games)
        return total / (2 * len(self.regular_season_games))

    def play_regular_season(self) -> None:
        for home, away in _generate_schedule(self.teams):
            result = play_game(home, away, self.cfg, league_meta=self.league_meta)
            self.regular_season_games.append(result)
            self._record(result)
        self.regular_season_standings = self.standings()
        # Snapshot records before playoffs inflate the counts
        self._reg_wins = dict(self._wins)
        self._reg_losses = dict(self._losses)

    def play_playoffs(self) -> None:
        bracket = self.regular_season_standings[:self.playoff_teams]

        while len(bracket) > 1:
            round_series: list[PlayoffSeries] = []
            next_bracket: list[Team] = []
            for i in range(len(bracket) // 2):
                s1 = bracket[i]
                s2 = bracket[len(bracket) - 1 - i]
                winner, games = play_series(
                    s1, s2, self.cfg,
                    home_advantage=self.cfg.playoff_home_advantage,
                    league_meta=self.league_meta,
                    seed_bonus=self.cfg.playoff_seed_bonus,
                )
                for g in games:
                    self._record(g)
                round_series.append(PlayoffSeries(s1, s2, winner, games))
                next_bracket.append(winner)
            self.playoff_rounds.append(round_series)
            bracket = next_bracket

        self.champion = bracket[0]
        self.champion.championships += 1

    def run(self) -> None:
        self.play_regular_season()
        self.play_playoffs()
