import random
from dataclasses import dataclass

from config import Config
from game import GameResult, play_game, play_series
from team import Team


def _generate_schedule(teams: list[Team]) -> list[tuple[Team, Team]]:
    """Home/away round robin: each pair plays once at each venue (38 games per team for 20 teams)."""
    matchups = [
        (home, away)
        for i, home in enumerate(teams)
        for j, away in enumerate(teams)
        if i != j
    ]
    random.shuffle(matchups)
    return matchups


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


def _round_name(num_teams: int) -> str:
    return {2: "Finals", 4: "Semifinals", 8: "Quarterfinals"}.get(
        num_teams, f"Round of {num_teams}"
    )


class Season:
    def __init__(self, number: int, teams: list[Team], cfg: Config):
        self.number = number
        self.teams = teams
        self.cfg = cfg

        self._wins: dict[Team, int] = {t: 0 for t in teams}
        self._losses: dict[Team, int] = {t: 0 for t in teams}

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
            key=lambda t: (self.win_pct(t), t.strength),
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
            result = play_game(home, away, self.cfg)
            self.regular_season_games.append(result)
            self._record(result)
        self.regular_season_standings = self.standings()
        # Snapshot records before playoffs inflate the counts
        self._reg_wins = dict(self._wins)
        self._reg_losses = dict(self._losses)

    def play_playoffs(self) -> None:
        bracket = self.regular_season_standings[: self.cfg.playoff_teams]

        while len(bracket) > 1:
            round_series: list[PlayoffSeries] = []
            next_bracket: list[Team] = []
            for i in range(len(bracket) // 2):
                s1 = bracket[i]
                s2 = bracket[len(bracket) - 1 - i]
                winner, games = play_series(s1, s2, self.cfg, home_advantage=self.cfg.playoff_home_advantage)
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
