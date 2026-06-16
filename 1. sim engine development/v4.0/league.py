import math
import random
from collections import Counter

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from season import Season
from team import Team


class League:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.reserve_pool: list[Franchise] = []
        self.teams = self._create_teams()
        self.seasons: list[Season] = []
        self.relocation_log: list[tuple] = []  # (season_after, old_name, new_name, losing, bottom2, pop)
        self.expansion_log: list[tuple] = []   # (season_after, franchise_name, is_secondary)
        self.merger_log: list[tuple] = []      # (season_after, franchise_name, is_secondary)
        self.league_meta: float = 0.0
        self._meta_velocity: float = 0.0
        self._meta_extreme_seasons: int = 0
        # League popularity — starts from the founding teams' market-weighted avg
        self.league_popularity: float = self._initial_league_popularity()
        self._expansion_eligible_seasons: int = 0
        self._last_expansion_season: int = 0
        self._merger_eligible_seasons: int = 0
        self._last_merger_season: int = 0
        self._next_team_id: int = len(self.teams) + 1

    # ── Initialisation ────────────────────────────────────────────────────────

    def _create_teams(self) -> list[Team]:
        """Select the top initial_teams franchises by effective_metro; rest go to reserve."""
        # Sort all franchises: primaries first by effective_metro, then secondaries
        primaries = sorted(
            [f for f in ALL_FRANCHISES if not f.secondary],
            key=lambda f: f.effective_metro,
            reverse=True,
        )
        secondaries = [f for f in ALL_FRANCHISES if f.secondary]

        starters = primaries[:self.cfg.initial_teams]
        self.reserve_pool = primaries[self.cfg.initial_teams:] + secondaries

        teams = []
        for i, f in enumerate(starters, 1):
            team = Team(
                i,
                random.uniform(self.cfg.min_quality, self.cfg.max_quality),
                f,
                identity=random.uniform(0.2, 0.8),
                joined_season=1,
            )
            teams.append(team)

        # Seed initial popularity from market size
        log_metros = [math.log(t.franchise.effective_metro) for t in teams]
        lo, hi = min(log_metros), max(log_metros)
        for team in teams:
            if hi > lo:
                norm = (math.log(team.franchise.effective_metro) - lo) / (hi - lo)
                team.popularity = 0.25 + norm * 0.50
            else:
                team.popularity = 0.5

        return teams

    def _initial_league_popularity(self) -> float:
        if not self.teams:
            return 0.45
        weights = [t.franchise.effective_metro for t in self.teams]
        total = sum(weights)
        return sum(t.popularity * w for t, w in zip(self.teams, weights)) / total

    # ── Market helpers ────────────────────────────────────────────────────────

    def _market_popularity_baseline(self, team: Team) -> float:
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        lo, hi = min(log_metros), max(log_metros)
        if hi == lo:
            return 0.5
        norm = (math.log(team.franchise.effective_metro) - lo) / (hi - lo)
        return 0.25 + norm * 0.50

    def _market_bias(self, team: Team) -> float:
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        avg_log = sum(log_metros) / len(log_metros)
        max_dev = max(abs(lm - avg_log) for lm in log_metros)
        if max_dev == 0:
            return 0.0
        normalized = (math.log(team.franchise.effective_metro) - avg_log) / max_dev
        return self.cfg.market_bias * normalized

    # ── Offseason helpers ─────────────────────────────────────────────────────

    def _runner_up(self, season: Season) -> Team:
        finals = season.playoff_rounds[-1][0]
        return finals.seed2 if finals.winner is finals.seed1 else finals.seed1

    def _grant_protections(self, season: Season) -> None:
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

    # Quality reset for playoff teams by how far they went.
    # Key: (rounds_from_finals, series_length) where rounds_from_finals=0 = finals loser.
    _PLAYOFF_QUALITY = {
        (0, 4): 3.28, (0, 5): 3.28, (0, 6): 3.29, (0, 7): 3.29,
        (1, 4): 3.23, (1, 5): 3.24, (1, 6): 3.25, (1, 7): 3.26,
        (2, 4): 3.18, (2, 5): 3.19, (2, 6): 3.20, (2, 7): 3.22,
        (3, 4): 3.10, (3, 5): 3.11, (3, 6): 3.12, (3, 7): 3.13,
    }

    def _offseason_adjustments(self, season: Season) -> None:
        num_rounds = len(season.playoff_rounds)
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
                stab_delta = -0.06

            team._identity_stability = max(0.0, min(1.0, team._identity_stability + stab_delta))

            sigma = self.cfg.identity_drift_sigma * (1.0 - team._identity_stability * 0.8)
            mean_reversion = 0.015 * (0.5 - team.identity)
            meta_nudge = self.league_meta * self.cfg.meta_identity_nudge
            drift = random.gauss(mean_reversion + meta_nudge, sigma)
            team.identity = max(0.0, min(1.0, team.identity + drift))

    def _check_relocations(self, season: Season) -> None:
        self._grant_protections(season)
        standings = season.regular_season_standings
        # Bottom-2 relative to this season's field
        bottom2 = set(standings[-2:])

        for team in self.teams:
            if season.reg_win_pct(team) < 0.5:
                team._consecutive_losing_seasons += 1
                if team in bottom2:
                    team._bottom2_in_streak += 1
            else:
                team._consecutive_losing_seasons = 0
                team._bottom2_in_streak = 0

            if team._consecutive_losing_seasons < self.cfg.relocation_threshold:
                continue
            if team._bottom2_in_streak < self.cfg.relocation_bottom2_required:
                continue
            if season.number < team._protected_until:
                continue

            min_metro = team.franchise.effective_metro / 2
            city_count = Counter(t.franchise.city for t in self.teams)

            eligible = [
                f for f in self.reserve_pool
                if f.effective_metro >= min_metro
                and city_count.get(f.city, 0) < (1 if f.secondary else 1)
                and not f.secondary  # relocations go to new cities only
                and city_count.get(f.city, 0) == 0
            ]

            if eligible and random.random() < self.cfg.relocation_chance:
                new_franchise = random.choice(eligible)
                self.reserve_pool.remove(new_franchise)
                losing_seasons = team._consecutive_losing_seasons
                bottom2_count  = team._bottom2_in_streak
                pop_at_move    = team.popularity
                old_franchise = team.relocate(new_franchise, season.number + 1)
                self.reserve_pool.append(old_franchise)
                self.relocation_log.append((
                    season.number, old_franchise.name, new_franchise.name,
                    losing_seasons, bottom2_count, pop_at_move,
                ))

    def _evolve_popularity(self, season: Season) -> None:
        standings = season.regular_season_standings
        bottom2 = set(standings[-2:])
        playoff_teams = {t for rnd in season.playoff_rounds for s in rnd for t in (s.seed1, s.seed2)}
        finalist = self._runner_up(season)

        # Build co-tenant map: for cities with exactly 2 teams, map each to its partner
        city_teams: dict[str, list[Team]] = {}
        for team in self.teams:
            city_teams.setdefault(team.franchise.city, []).append(team)
        cotenant_of: dict[Team, Team] = {}
        for teams_in_city in city_teams.values():
            if len(teams_in_city) == 2:
                t1, t2 = teams_in_city
                cotenant_of[t1] = t2
                cotenant_of[t2] = t1

        steal_deltas: dict[Team, float] = {}

        for team in self.teams:
            # Decay legacy each season before using it
            team.legacy *= (1.0 - self.cfg.legacy_decay)

            cotenant = cotenant_of.get(team)
            baseline = self._market_popularity_baseline(team)

            # Co-tenants pull toward a reduced share of the market baseline
            if cotenant is not None:
                share = (self.cfg.cotenant_primary_share
                         if not team.franchise.secondary
                         else self.cfg.cotenant_secondary_share)
                effective_baseline = baseline * share
            else:
                effective_baseline = baseline

            # Legacy lifts the effective baseline — durable history raises the floor
            effective_baseline = min(1.0, effective_baseline + team.legacy)

            delta = self.cfg.popularity_market_weight * (effective_baseline - team.popularity) * 0.1

            if team is season.champion:
                team._consecutive_playoff_misses = 0
                delta += self.cfg.popularity_championship
                team.legacy = min(self.cfg.legacy_max, team.legacy + self.cfg.legacy_per_title)
                if cotenant is not None:
                    steal_deltas[cotenant] = steal_deltas.get(cotenant, 0.0) - (
                        self.cfg.popularity_championship * self.cfg.cotenant_steal_fraction
                    )
            elif team is finalist:
                team._consecutive_playoff_misses = 0
                delta += self.cfg.popularity_finals
                if cotenant is not None:
                    steal_deltas[cotenant] = steal_deltas.get(cotenant, 0.0) - (
                        self.cfg.popularity_finals * self.cfg.cotenant_steal_fraction
                    )
            elif team in playoff_teams:
                team._consecutive_playoff_misses = 0
                delta += self.cfg.popularity_playoff
            else:
                team._consecutive_playoff_misses += 1
                if team.popularity > effective_baseline:
                    penalty = min(
                        self.cfg.popularity_miss_playoffs * team._consecutive_playoff_misses,
                        self.cfg.popularity_miss_playoffs_max,
                    )
                    delta -= penalty
                if team in bottom2:
                    delta -= self.cfg.popularity_bottom2

            team.popularity = max(0.0, min(1.0, team.popularity + delta))

        # Apply co-tenant steal penalties (separate pass so order doesn't matter)
        for team, steal in steal_deltas.items():
            team.popularity = max(0.0, min(1.0, team.popularity + steal))

    def _evolve_league_popularity(self, season: Season) -> None:
        """Shift league-wide popularity based on team health, excitement, and era."""
        # Pull toward market-weighted average team popularity
        weights = [t.franchise.effective_metro for t in self.teams]
        total_w = sum(weights)
        avg_pop = sum(t.popularity * w for t, w in zip(self.teams, weights)) / total_w

        delta = self.cfg.league_pop_market_weight * (avg_pop - self.league_popularity)

        # Upset excitement: low-seeded champion drives interest
        champ_seed = season.regular_season_standings.index(season.champion) + 1
        if champ_seed >= 4:
            delta += self.cfg.league_pop_excitement_boost

        # Dynasty fatigue: same team winning again dampens interest
        if len(self.seasons) >= 2 and season.champion is self.seasons[-2].champion:
            delta -= self.cfg.league_pop_dynasty_penalty

        # Offensive era is more entertaining
        delta += max(0.0, self.league_meta) * self.cfg.league_pop_offensive_boost

        self.league_popularity = max(0.0, min(1.0, self.league_popularity + delta))

    def _evolve_meta(self) -> None:
        n = min(5, len(self.seasons))
        recent = self.seasons[-n:]
        weights = list(range(n, 0, -1))
        champ_ids = [s._start_ratings[s.champion][1] for s in recent]
        weighted_id = sum(w * i for w, i in zip(weights, champ_ids)) / sum(weights)

        champion_signal = (weighted_id - 0.5) * self.cfg.meta_champion_influence

        self._meta_velocity = (
            self._meta_velocity * self.cfg.meta_velocity_damping
            + random.gauss(0, self.cfg.meta_sigma)
            - self.league_meta * self.cfg.meta_reversion
            + champion_signal
        )
        self.league_meta = max(
            -self.cfg.meta_max,
            min(self.cfg.meta_max, self.league_meta + self._meta_velocity)
        )

        if abs(self.league_meta) > self.cfg.meta_shock_threshold:
            self._meta_extreme_seasons += 1
        else:
            self._meta_extreme_seasons = 0

        if self._meta_extreme_seasons >= self.cfg.meta_shock_min_seasons:
            excess = self._meta_extreme_seasons - self.cfg.meta_shock_min_seasons
            shock_prob = self.cfg.meta_shock_base_prob + self.cfg.meta_shock_prob_growth * excess
            if random.random() < shock_prob:
                self.league_meta = random.gauss(0, self.cfg.meta_shock_spread)
                self._meta_velocity = 0.0
                self._meta_extreme_seasons = 0
                self.seasons[-1].meta_shock = True

    # ── Expansion ─────────────────────────────────────────────────────────────

    def _expansion_candidates(self, season_num: int) -> list[Franchise]:
        """Return reserve franchises eligible for expansion, sorted best-first."""
        city_count = Counter(t.franchise.city for t in self.teams)

        eligible = []
        for f in self.reserve_pool:
            if f.secondary:
                # City must have exactly 1 team and the incumbent must be established
                if city_count.get(f.city, 0) != 1:
                    continue
                incumbent = next(t for t in self.teams if t.franchise.city == f.city)
                if season_num - incumbent.joined_season < self.cfg.expansion_secondary_min_seasons:
                    continue
            else:
                # New market — city must have 0 teams
                if city_count.get(f.city, 0) != 0:
                    continue
            eligible.append(f)

        eligible.sort(key=lambda f: f.effective_metro, reverse=True)
        return eligible

    def _add_expansion_team(self, franchise: Franchise, joined_season: int) -> Team:
        """Create a new expansion team and add it to the league."""
        is_secondary = franchise.secondary

        new_team = Team(
            self._next_team_id,
            self.cfg.min_quality,     # expansion teams start at rock bottom
            franchise,
            identity=0.5,             # balanced — mediocre at everything
            joined_season=joined_season,
        )
        self._next_team_id += 1

        # Set grace period: can't relocate for expansion_grace_seasons
        new_team._protected_until = joined_season + self.cfg.expansion_grace_seasons

        # Popularity seeding
        if is_secondary:
            # Split with incumbent: incumbent keeps 80%, new team gets 20%
            incumbent = next(t for t in self.teams if t.franchise.city == franchise.city)
            new_team.popularity = incumbent.popularity * 0.20
            incumbent.popularity *= 0.80
        else:
            # New market: seed from relative market size
            log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
            lo, hi = min(log_metros), max(log_metros)
            if hi > lo:
                norm = (math.log(franchise.effective_metro) - lo) / (hi - lo)
                new_team.popularity = 0.25 + norm * 0.50
            else:
                new_team.popularity = 0.5

        self.teams.append(new_team)
        self.reserve_pool.remove(franchise)
        return new_team

    def _check_expansions(self, season: Season) -> None:
        if len(self.teams) >= self.cfg.max_teams:
            return
        if season.number - self._last_expansion_season < self.cfg.expansion_min_seasons:
            return

        if self.league_popularity >= self.cfg.expansion_trigger_popularity:
            self._expansion_eligible_seasons += 1
        else:
            self._expansion_eligible_seasons = 0
            return

        if self._expansion_eligible_seasons < self.cfg.expansion_consecutive_seasons:
            return

        candidates = self._expansion_candidates(season.number)
        if not candidates:
            return

        # Boom expansion when league is thriving
        wave_size = (
            self.cfg.expansion_boom_teams
            if self.league_popularity >= self.cfg.expansion_boom_popularity
            else self.cfg.expansion_teams_per_wave
        )
        n_add = min(wave_size, self.cfg.max_teams - len(self.teams), len(candidates))

        joined = season.number + 1
        for franchise in candidates[:n_add]:
            self._add_expansion_team(franchise, joined)
            self.expansion_log.append((season.number, franchise.name, franchise.secondary))

        self.league_popularity = min(
            1.0, self.league_popularity + self.cfg.league_pop_expansion_boost
        )
        self._last_expansion_season = season.number
        self._expansion_eligible_seasons = 0

    # ── Rival merger ──────────────────────────────────────────────────────────

    def _merger_candidates(self) -> list[Franchise]:
        """Franchises eligible for merger — any city with fewer than 2 current teams."""
        city_count = Counter(t.franchise.city for t in self.teams)
        eligible = [
            f for f in self.reserve_pool
            if city_count.get(f.city, 0) < 2
        ]
        eligible.sort(key=lambda f: f.effective_metro, reverse=True)
        return eligible

    def _add_merger_team(self, franchise: Franchise, joined_season: int) -> Team:
        """Create a merger team: varied quality, rival-league fan base, no 80/20 split."""
        quality = random.uniform(self.cfg.merger_quality_min, self.cfg.merger_quality_max)
        identity = random.uniform(0.2, 0.8)

        # Compute market baseline BEFORE adding team to avoid self-reference
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        lo, hi = min(log_metros), max(log_metros)
        if hi > lo:
            norm = (math.log(franchise.effective_metro) - lo) / (hi - lo)
            baseline = 0.25 + norm * 0.50
        else:
            baseline = 0.5
        pop_fraction = random.uniform(self.cfg.merger_pop_fraction_min, self.cfg.merger_pop_fraction_max)

        new_team = Team(
            self._next_team_id,
            quality,
            franchise,
            identity=identity,
            popularity=baseline * pop_fraction,
            joined_season=joined_season,
        )
        self._next_team_id += 1
        new_team._protected_until = joined_season + self.cfg.expansion_grace_seasons

        self.teams.append(new_team)
        self.reserve_pool.remove(franchise)
        return new_team

    def _check_merger(self, season: Season) -> None:
        if len(self.teams) >= self.cfg.max_teams:
            return
        if len(self.teams) < self.cfg.merger_min_teams:
            return
        if len(self.teams) >= self.cfg.merger_max_teams:
            return  # mergers are a growth-phase event; use expansion once established
        if season.number < self.cfg.merger_min_season:
            return
        if season.number - self._last_merger_season < self.cfg.merger_cooldown_seasons:
            return

        if self.league_popularity < self.cfg.merger_trigger_popularity:
            self._merger_eligible_seasons += 1
        else:
            self._merger_eligible_seasons = 0
            return

        if self._merger_eligible_seasons < self.cfg.merger_consecutive_seasons:
            return

        candidates = self._merger_candidates()
        if not candidates:
            return

        n_add = random.randint(
            min(self.cfg.merger_size_min, len(candidates)),
            min(self.cfg.merger_size_max, self.cfg.max_teams - len(self.teams), len(candidates)),
        )
        if n_add <= 0:
            return

        joined = season.number + 1
        for franchise in candidates[:n_add]:
            self._add_merger_team(franchise, joined)
            self.merger_log.append((season.number, franchise.name, franchise.secondary))

        # Merger generates consolidation excitement
        self.league_popularity = min(
            1.0, self.league_popularity + self.cfg.merger_league_pop_boost
        )
        self._last_merger_season = season.number
        self._merger_eligible_seasons = 0

    # ── Main simulation loop ──────────────────────────────────────────────────

    def simulate(self) -> None:
        for season_num in range(1, self.cfg.num_seasons + 1):
            season = Season(season_num, list(self.teams), self.cfg, self.league_meta)
            season.run()
            self.seasons.append(season)
            self._offseason_adjustments(season)
            self._check_relocations(season)
            self._evolve_popularity(season)
            self._evolve_league_popularity(season)
            self._evolve_meta()
            # Snapshot BEFORE expansion/merger changes the roster
            season._popularity = {t: t.popularity for t in self.teams}
            season._league_popularity = self.league_popularity
            self._check_expansions(season)
            self._check_merger(season)
