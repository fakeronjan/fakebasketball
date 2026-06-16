import math
import random

from config import Config
from franchises import ACTIVE_FRANCHISES, RESERVE_FRANCHISES, Franchise
from season import Season
from team import Team


class League:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.reserve_pool: list[Franchise] = list(RESERVE_FRANCHISES)
        self.teams = self._create_teams()
        self.seasons: list[Season] = []
        self.relocation_log: list[tuple[int, str, str]] = []  # (season_after, old_name, new_name)

    def _create_teams(self) -> list[Team]:
        franchises = random.sample(ACTIVE_FRANCHISES, len(ACTIVE_FRANCHISES))
        return [
            Team(i, random.uniform(self.cfg.min_quality, self.cfg.max_quality), f,
                 identity=random.uniform(0.2, 0.8))
            for i, f in enumerate(franchises, 1)
        ]

    def _runner_up(self, season: Season) -> Team:
        finals = season.playoff_rounds[-1][0]
        return finals.seed2 if finals.winner is finals.seed1 else finals.seed1

    def _grant_protections(self, season: Season) -> None:
        """Grant relocation immunity to the champion and finalist."""
        champ = season.champion
        champ._protected_until = max(
            champ._protected_until,
            season.number + self.cfg.championship_protection,
        )
        finalist = self._runner_up(season)
        finalist._protected_until = max(
            finalist._protected_until,
            season.number + self.cfg.finals_protection,
        )

    # Quality table: (rounds_from_finals, series_length) -> starting quality next season
    # rounds_from_finals: 0 = finals loser, 1 = semis loser, 2 = quarters loser
    _PLAYOFF_QUALITY = {
        (0, 4): 3.28, (0, 5): 3.28, (0, 6): 3.29, (0, 7): 3.29,
        (1, 4): 3.23, (1, 5): 3.24, (1, 6): 3.25, (1, 7): 3.26,
        (2, 4): 3.18, (2, 5): 3.19, (2, 6): 3.20, (2, 7): 3.22,
    }

    def _market_bias(self, team: Team) -> float:
        """Return a mean shift in [-market_bias, +market_bias] based on log-scaled metro size.

        Teams above the log-average metro get a positive mu (talent magnet);
        teams below get a negative mu (talent drain). The team furthest from
        the log-average anchors the scale at ±cfg.market_bias.
        """
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        avg_log = sum(log_metros) / len(log_metros)
        max_dev = max(abs(lm - avg_log) for lm in log_metros)
        if max_dev == 0:
            return 0.0
        normalized = (math.log(team.franchise.effective_metro) - avg_log) / max_dev
        return self.cfg.market_bias * normalized

    def _offseason_adjustments(self, season: Season) -> None:
        """Reset team qualities based on playoff finish; randomise non-playoff teams."""
        num_rounds = len(season.playoff_rounds)

        # Build a map of team -> (rounds_from_finals, series_length) for every loser
        playoff_exit: dict = {}
        for round_idx, round_series in enumerate(season.playoff_rounds):
            rounds_from_finals = num_rounds - 1 - round_idx
            for series in round_series:
                loser = series.seed2 if series.winner is series.seed1 else series.seed1
                playoff_exit[loser] = (rounds_from_finals, len(series.games))

        for team in self.teams:
            if team is season.champion:
                team.quality = self.cfg.max_quality
            elif team in playoff_exit:
                key = playoff_exit[team]
                team.quality = self._PLAYOFF_QUALITY.get(key, self.cfg.max_quality - 0.20)
            else:
                mu = self._market_bias(team)
                adjustment = random.gauss(mu, self.cfg.offseason_sigma)
                team.quality = max(
                    self.cfg.min_quality,
                    min(self.cfg.max_quality, team.quality + adjustment),
                )

        self._evolve_identities(season)

    def _evolve_identities(self, season: Season) -> None:
        """Shift each team's identity based on playoff success — winners double down, losers search."""
        finalist = self._runner_up(season)
        playoff_teams = set()
        for rnd in season.playoff_rounds:
            for series in rnd:
                playoff_teams.add(series.seed1)
                playoff_teams.add(series.seed2)

        for team in self.teams:
            if team is season.champion:
                stab_delta = +0.12
            elif team is finalist:
                stab_delta = +0.07
            elif team in playoff_teams:
                stab_delta = +0.04
            else:
                stab_delta = -0.06  # searching — identity becomes more fluid

            team._identity_stability = max(0.0, min(1.0, team._identity_stability + stab_delta))

            # Stable teams resist change; unstable teams drift more.
            # A weak mean-reversion toward 0.5 prevents the whole league drifting to one style.
            sigma = self.cfg.identity_drift_sigma * (1.0 - team._identity_stability * 0.8)
            mean_reversion = 0.015 * (0.5 - team.identity)
            drift = random.gauss(mean_reversion, sigma)
            team.identity = max(0.0, min(1.0, team.identity + drift))

    def _check_relocations(self, season: Season) -> None:
        self._grant_protections(season)

        standings = season.regular_season_standings
        bottom2 = set(standings[-2:])

        for team in self.teams:
            # Update streak counters
            if season.reg_win_pct(team) < 0.5:
                team._consecutive_losing_seasons += 1
                if team in bottom2:
                    team._bottom2_in_streak += 1
            else:
                team._consecutive_losing_seasons = 0
                team._bottom2_in_streak = 0

            # Eligibility checks
            if team._consecutive_losing_seasons < self.cfg.relocation_threshold:
                continue
            if team._bottom2_in_streak < self.cfg.relocation_bottom2_required:
                continue
            if season.number < team._protected_until:
                continue

            # Destination must have metro >= half of current market
            min_metro = team.franchise.effective_metro / 2
            eligible = [f for f in self.reserve_pool if f.metro >= min_metro]

            if eligible and random.random() < self.cfg.relocation_chance:
                new_franchise = random.choice(eligible)
                self.reserve_pool.remove(new_franchise)
                losing_seasons = team._consecutive_losing_seasons
                bottom2_count  = team._bottom2_in_streak
                old_franchise = team.relocate(new_franchise, season.number + 1)
                self.reserve_pool.append(old_franchise)
                self.relocation_log.append((season.number, old_franchise.name, new_franchise.name,
                                            losing_seasons, bottom2_count))

    def simulate(self) -> None:
        for season_num in range(1, self.cfg.num_seasons + 1):
            season = Season(season_num, self.teams, self.cfg)
            season.run()
            self.seasons.append(season)
            self._offseason_adjustments(season)
            self._check_relocations(season)
