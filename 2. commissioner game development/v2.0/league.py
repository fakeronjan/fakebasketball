import math
import random
from collections import Counter
from typing import Optional

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from season import Season
from team import Team


class League:
    def __init__(self, cfg: Config, selected_franchises: Optional[list] = None):
        self.cfg = cfg
        self.reserve_pool: list[Franchise] = []
        self.teams = self._create_teams(selected_franchises)
        self.seasons: list[Season] = []
        self.relocation_log: list[tuple] = []  # (season_after, old_name, new_name, losing, bottom2, pop)
        self.expansion_log: list[tuple] = []   # (season_after, franchise_name, is_secondary)
        self.merger_log: list[tuple] = []      # (season_after, franchise_name, is_secondary)
        self.league_meta: float = 0.0
        self._meta_velocity: float = 0.0
        self._meta_extreme_seasons: int = 0
        # Grudge: cities that lost a franchise hold lasting negative sentiment.
        # market_grudges[city] = score 0–1; _grudge_metro[city] = metro weight.
        self.market_grudges: dict = {}
        self._grudge_metro: dict = {}
        # Relocation cooldown: cities that recently lost a team cannot receive
        # a relocated team for 3 seasons.  Maps city → first season relocation in is allowed.
        self._relocation_cooldowns: dict = {}
        # League popularity — starts from the founding teams' market-weighted avg
        self.league_popularity: float = self._initial_league_popularity()
        self._talent_boost_seasons_left: int = 0
        self._talent_boost_delta: float = 0.0
        self._expansion_eligible_seasons: int = 0
        self._last_expansion_season: int = 0
        self._merger_eligible_seasons: int = 0
        self._last_merger_season: int = 0
        self._next_team_id: int = len(self.teams) + 1
        self.legitimacy: float = 1.0   # 0–1; drops with G7 interventions, recovers passively

    # ── Initialisation ────────────────────────────────────────────────────────

    def _create_teams(self, selected: Optional[list] = None) -> list[Team]:
        """Select founding franchises; rest go to reserve."""
        primaries = sorted(
            [f for f in ALL_FRANCHISES if not f.secondary],
            key=lambda f: f.effective_metro,
            reverse=True,
        )
        secondaries = [f for f in ALL_FRANCHISES if f.secondary]

        if selected is not None:
            starters = selected
            self.reserve_pool = [f for f in primaries if f not in selected] + secondaries
        else:
            starters = primaries[:self.cfg.initial_teams]
            self.reserve_pool = primaries[self.cfg.initial_teams:] + secondaries

        # Pre-compute initial ratings based on spread mode
        cfg = self.cfg
        o_lo, o_hi = cfg.ortg_min, cfg.ortg_max
        d_lo, d_hi = cfg.drtg_min, cfg.drtg_max
        o_mid = (o_lo + o_hi) / 2.0
        d_mid = (d_lo + d_hi) / 2.0
        n = len(starters)
        mode = cfg.initial_rating_mode
        if mode == "uniform":
            initial_ortgs = [o_mid] * n
            initial_drtgs = [d_mid] * n
        elif mode == "haves_havenots":
            haves = n // 2
            have_o = [random.uniform(o_mid, o_hi) for _ in range(haves)]
            have_d = [random.uniform(d_lo, d_mid) for _ in range(haves)]
            not_o  = [random.uniform(o_lo, o_mid) for _ in range(n - haves)]
            not_d  = [random.uniform(d_mid, d_hi) for _ in range(n - haves)]
            initial_ortgs = have_o + not_o
            initial_drtgs = have_d + not_d
            random.shuffle(initial_ortgs)
            random.shuffle(initial_drtgs)
        else:  # moderate (default)
            initial_ortgs = [random.uniform(o_lo, o_hi) for _ in range(n)]
            initial_drtgs = [random.uniform(d_lo, d_hi) for _ in range(n)]

        def _rand_style():
            raw = [random.random() for _ in range(4)]
            s = sum(raw)
            return [r / s for r in raw]

        teams = []
        for i, (f, ortg, drtg) in enumerate(zip(starters, initial_ortgs, initial_drtgs), 1):
            pace = random.uniform(cfg.pace_min, cfg.pace_max)
            ft, paint, mid, three = _rand_style()
            team = Team(
                i, f,
                ortg=ortg, drtg=drtg, pace=pace,
                style_ft=ft, style_paint=paint, style_mid=mid, style_3pt=three,
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

        # Founding co-tenants split popularity 50/50 — no history gives either an edge
        city_teams = {}
        for team in teams:
            city_teams.setdefault(team.franchise.city, []).append(team)
        for city_group in city_teams.values():
            if len(city_group) == 2:
                shared = city_group[0].popularity  # both have same metro → same value
                city_group[0].popularity = shared * 0.50
                city_group[1].popularity = shared * 0.50

        return teams

    def _initial_league_popularity(self) -> float:
        return 0.0

    # ── Market helpers ────────────────────────────────────────────────────────

    def _market_popularity_baseline(self, team: Team) -> float:
        """Natural popularity equilibrium for a team, driven by relative market size.

        Larger cities have more potential fans so the brand naturally settles higher.
        Log-normalised across the current league: smallest market → 0.35, largest → 0.65.
        """
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        lo, hi = min(log_metros), max(log_metros)
        if hi > lo:
            norm = (math.log(team.franchise.effective_metro) - lo) / (hi - lo)
        else:
            norm = 0.5
        return 0.35 + norm * 0.30

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

    def _offseason_adjustments(self, season: Season) -> None:
        """Pure random walk for ORtg, DRtg, pace, and style — hard bounds only."""
        cfg = self.cfg
        for team in self.teams:
            team.ortg = max(cfg.ortg_min, min(cfg.ortg_max,
                team.ortg + random.gauss(0, cfg.ortg_sigma)))
            team.drtg = max(cfg.drtg_min, min(cfg.drtg_max,
                team.drtg + random.gauss(0, cfg.drtg_sigma)))
            team.pace = max(cfg.pace_min, min(cfg.pace_max,
                team.pace + random.gauss(0, cfg.pace_sigma)))

        self._evolve_styles(season)

    def start_talent_investment(self, delta: float, seasons: int) -> None:
        """Temporarily widen ORtg/DRtg walk sigma for non-playoff teams."""
        self._talent_boost_seasons_left += seasons
        self._talent_boost_delta = delta

    def _evolve_styles(self, season: Season) -> None:
        """Drift each team's style_3pt slightly based on league meta."""
        for team in self.teams:
            meta_nudge = self.league_meta * self.cfg.meta_style_nudge
            drift = random.gauss(meta_nudge, self.cfg.style_3pt_sigma)
            new_3pt = max(0.05, min(0.55, team.style_3pt + drift))
            # Renormalize: redistribute style change proportionally across other buckets
            delta = new_3pt - team.style_3pt
            other_sum = team.style_ft + team.style_paint + team.style_mid
            if other_sum > 0:
                scale = (other_sum - delta) / other_sum
                team.style_ft    = max(0.02, team.style_ft    * scale)
                team.style_paint = max(0.02, team.style_paint * scale)
                team.style_mid   = max(0.02, team.style_mid   * scale)
            team.style_3pt = new_3pt
            # Renormalize to sum to 1.0
            total = team.style_ft + team.style_paint + team.style_mid + team.style_3pt
            team.style_ft    /= total
            team.style_paint /= total
            team.style_mid   /= total
            team.style_3pt   /= total

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

            city_count = Counter(t.franchise.city for t in self.teams)

            eligible = [
                f for f in self.reserve_pool
                if not f.secondary
                and city_count.get(f.city, 0) == 0
            ]

            if eligible and random.random() < self.cfg.relocation_chance:
                new_franchise = random.choice(eligible)
                self.reserve_pool.remove(new_franchise)
                old_city      = team.franchise.city
                old_metro     = team.franchise.effective_metro
                losing_seasons = team._consecutive_losing_seasons
                bottom2_count  = team._bottom2_in_streak
                pop_at_move    = team.popularity
                old_franchise = team.relocate(new_franchise, season.number + 1)
                self.reserve_pool.append(old_franchise)
                self.relocation_log.append((
                    season.number, old_franchise.name, new_franchise.name,
                    losing_seasons, bottom2_count, pop_at_move,
                ))
                self.market_grudges[old_city] = 1.0
                self._grudge_metro[old_city]  = old_metro

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

    def _decay_grudges(self) -> None:
        """Decay active market grudges each season. Floor prevents full recovery
        unless the market is made whole with a new franchise."""
        cfg = self.cfg
        for city in list(self.market_grudges):
            self.market_grudges[city] = max(
                cfg.market_grudge_floor,
                self.market_grudges[city] * (1.0 - cfg.market_grudge_decay),
            )

    def _evolve_market_engagements(self, season: Season) -> None:
        """Update each market's engagement with the league based on team performance.

        Engagement rises with playoff success and falls with sustained losing.
        It also drifts slowly toward the market's natural basketball-interest baseline
        (franchise.market_interest), so culturally strong cities recover faster and
        culturally weak ones plateau sooner.
        """
        playoff_teams = {t for rnd in season.playoff_rounds for s in rnd
                         for t in (s.seed1, s.seed2)}
        finalist = self._runner_up(season)
        standings = season.regular_season_standings
        bottom2 = set(standings[-2:])

        for team in self.teams:
            delta = 0.0

            # Performance signals
            if team is season.champion:
                delta += 0.040
            elif team is finalist:
                delta += 0.025
            elif team in playoff_teams:
                delta += 0.012
            else:
                # Progressive penalty — fans disengage after repeated losing seasons
                misses = team._consecutive_playoff_misses
                delta -= min(0.025, 0.005 * misses)
                if team in bottom2:
                    delta -= 0.015

            # Slow mean-reversion toward a metro-size-based natural ceiling.
            # Larger cities can sustain higher engagement; smaller ones plateau sooner.
            log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
            lo_m, hi_m = min(log_metros), max(log_metros)
            if hi_m > lo_m:
                norm = (math.log(team.franchise.effective_metro) - lo_m) / (hi_m - lo_m)
            else:
                norm = 0.5
            ceiling = 0.20 + norm * 0.40   # 0.20 (smallest) to 0.60 (largest)
            delta += 0.008 * (ceiling - team.market_engagement)

            team.market_engagement = max(0.0, min(1.0, team.market_engagement + delta))

    def _evolve_league_popularity(self, season: Season) -> dict:
        """Shift league-wide popularity and return a {signal: delta} breakdown.

        The base anchor is the market-weighted average of team market_engagements.
        Narrative signals (drama, dynasty, balance, etc.) adjust around that anchor.
        Replaces the old team-pull and large-market signals, which are now implicit
        in the engagement average.
        """
        cfg = self.cfg
        signals: dict = {}
        delta = 0.0
        n_seasons = len(self.seasons)

        # ── Base: pull toward market-weighted engagement average ──────────────
        # De-duplicate shared markets so co-tenant cities count once at full weight.
        city_engs: dict = {}
        city_metro: dict = {}
        for team in self.teams:
            city = team.franchise.city
            city_engs.setdefault(city, []).append(team.market_engagement)
            city_metro[city] = max(city_metro.get(city, 0.0),
                                   team.franchise.effective_metro)
        total_w = sum(city_metro.values())
        avg_eng = sum(
            (sum(engs) / len(engs)) * city_metro[city]
            for city, engs in city_engs.items()
        ) / total_w

        eng_pull = cfg.league_pop_engagement_pull * (avg_eng - self.league_popularity)
        signals["Market engagement"] = eng_pull
        delta += eng_pull

        # ── Drama: did playoff series go the distance? ────────────────────────
        all_series = [sr for rnd in season.playoff_rounds for sr in rnd]
        drama_delta = 0.0
        if all_series:
            min_games = (cfg.series_length + 1) // 2
            span = cfg.series_length - min_games
            if span > 0:
                avg_drama = (
                    sum((len(sr.games) - min_games) / span for sr in all_series)
                    / len(all_series)
                )
                drama_delta = cfg.league_pop_drama_max * (avg_drama - 0.4)
        signals["Drama"] = drama_delta
        delta += drama_delta

        # ── Dynasty curve ─────────────────────────────────────────────────────
        consecutive = 0
        champ = season.champion
        for past in reversed(self.seasons[:-1]):
            if past.champion is champ:
                consecutive += 1
            else:
                break
        dynasty_delta = {0: 0.008, 1: 0.012, 2: 0.000,
                         3: -0.015, 4: -0.025}.get(consecutive, -0.035)
        signals["Dynasty"] = dynasty_delta
        delta += dynasty_delta

        # ── Entertainment: inverted-U on league_meta ──────────────────────────
        deviation = self.league_meta - 0.05   # optimal at slight offensive lean
        bandwidth = 0.08
        if abs(deviation) <= bandwidth:
            ent_delta = cfg.league_pop_entertainment_max * (1.0 - (deviation / bandwidth) ** 2)
        else:
            excess = abs(deviation) - bandwidth
            ent_delta = -cfg.league_pop_entertainment_max * min(1.5, excess / 0.05)
        signals["Entertainment"] = ent_delta
        delta += ent_delta

        # ── Competitive balance: champion variety ─────────────────────────────
        balance_delta = 0.0
        window = min(cfg.league_pop_balance_window, n_seasons)
        if window >= 3:
            recent_champs = [s.champion for s in self.seasons[-window:]]
            variety_ratio = len(set(recent_champs)) / window
            if variety_ratio < 0.25:
                balance_delta = -cfg.league_pop_balance_penalty * (0.25 - variety_ratio) / 0.25
            elif variety_ratio >= 0.45:
                balance_delta = (cfg.league_pop_balance_penalty * 0.3
                                 * min(1.0, (variety_ratio - 0.45) / 0.20))
        signals["Balance"] = balance_delta
        delta += balance_delta

        # ── Established rivalries ─────────────────────────────────────────────
        rivalry_delta = 0.0
        if n_seasons >= 4:
            rivalry_window = min(8, n_seasons)
            pair_counts: dict = {}
            for past in self.seasons[-rivalry_window:]:
                for rnd in past.playoff_rounds:
                    for sr in rnd:
                        key = tuple(sorted([sr.seed1.team_id, sr.seed2.team_id]))
                        pair_counts[key] = pair_counts.get(key, 0) + 1
            established = sum(1 for cnt in pair_counts.values() if cnt >= 3)
            rivalry_delta = cfg.league_pop_rivalry_bonus * min(3, established)
        signals["Rivalries"] = rivalry_delta
        delta += rivalry_delta

        # ── Geographic spread of playoff contenders ───────────────────────────
        geo_delta = 0.0
        playoff_set = {t for rnd in season.playoff_rounds for sr in rnd
                       for t in (sr.seed1, sr.seed2)}
        playoff_set.add(season.champion)
        geo_teams = [t for t in playoff_set if t.franchise.lat != 0.0]
        if len(geo_teams) >= 3:
            lats = [t.franchise.lat for t in geo_teams]
            lons = [t.franchise.lon for t in geo_teams]
            spread = min(1.0, ((max(lats) - min(lats)) / 25.0
                               + (max(lons) - min(lons)) / 55.0) / 2.0)
            geo_delta = cfg.league_pop_geo_spread_max * (spread - 0.5)
        signals["Geography"] = geo_delta
        delta += geo_delta

        # ── Finals matchup market interest ────────────────────────────────────
        finals_delta = 0.0
        if season.playoff_rounds:
            finals = season.playoff_rounds[-1][0]
            avg_engagement = (finals.seed1.market_engagement
                              + finals.seed2.market_engagement) / 2.0
            # Neutral at 0.30 engagement; above → positive buzz, below → muted
            finals_delta = cfg.league_pop_finals_interest_scale * (avg_engagement - 0.30) / 0.30
        signals["Finals buzz"] = finals_delta
        delta += finals_delta

        # ── Legacy matchup: prestige of playoff opponents ─────────────────────
        # Each series contributes legacy1 × legacy2, weighted by round depth.
        # Finals counts full (1.0), Semis half (0.5), QF quarter (0.25), etc.
        # A dynasty-vs-dynasty Finals (both near legacy_max) drives big interest;
        # two expansion teams meeting generates almost nothing.
        legacy_score = 0.0
        n_rounds = len(season.playoff_rounds)
        for round_idx, rnd in enumerate(season.playoff_rounds):
            rounds_from_finals = n_rounds - 1 - round_idx
            round_weight = 1.0 / (2 ** rounds_from_finals)
            for sr in rnd:
                legacy_score += sr.seed1.legacy * sr.seed2.legacy * round_weight
        legacy_delta = cfg.league_pop_legacy_matchup_scale * legacy_score
        signals["Legacy matchup"] = legacy_delta
        delta += legacy_delta

        # ── Market grudges: vacated cities actively hurt the league ──────────
        grudge_delta = 0.0
        if self.market_grudges:
            total_w = sum(self._grudge_metro.get(c, 1.0) for c in self.market_grudges)
            if total_w > 0:
                weighted = sum(
                    score * self._grudge_metro.get(city, 1.0)
                    for city, score in self.market_grudges.items()
                )
                grudge_delta = -cfg.league_pop_grudge_max * (weighted / total_w)
        signals["Grudge markets"] = grudge_delta
        delta += grudge_delta

        # ── Legitimacy: rigged games erode fan trust ──────────────────────────
        legit_delta = -cfg.legitimacy_pop_penalty * (1.0 - self.legitimacy)
        signals["Legitimacy"] = legit_delta
        delta += legit_delta

        # Passive legitimacy recovery each season
        self.legitimacy = min(1.0, self.legitimacy + cfg.legitimacy_recovery)

        self.league_popularity = max(0.0, min(1.0, self.league_popularity + delta))
        return signals

    def _evolve_meta(self) -> None:
        n = min(5, len(self.seasons))
        recent = self.seasons[-n:]
        weights = list(range(n, 0, -1))
        champ_3pts = [s._start_ratings[s.champion][3] for s in recent]
        weighted_3pt = sum(w * v for w, v in zip(weights, champ_3pts)) / sum(weights)

        # High-3pt champion → push toward offensive era; low-3pt → push defensive
        champion_signal = (weighted_3pt - 0.25) * self.cfg.meta_champion_style_influence

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
        cfg = self.cfg

        # Entering this city clears any lingering grudge
        if franchise.city in self.market_grudges:
            del self.market_grudges[franchise.city]
            del self._grudge_metro[franchise.city]

        raw = [random.random() for _ in range(4)]
        s = sum(raw)
        ft, paint, mid, three = [r / s for r in raw]
        new_team = Team(
            self._next_team_id, franchise,
            ortg=cfg.ortg_baseline, drtg=cfg.drtg_baseline, pace=cfg.pace_baseline,
            style_ft=ft, style_paint=paint, style_mid=mid, style_3pt=three,
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
        """Franchises eligible for merger — one per unoccupied or single-tenant city."""
        city_count = Counter(t.franchise.city for t in self.teams)
        seen_cities: set = set()
        eligible: list[Franchise] = []
        # Sort best market first so we always keep the primary (larger) franchise
        # when both primary and secondary for a city are in the reserve pool.
        for f in sorted(self.reserve_pool, key=lambda f: -f.effective_metro):
            if city_count.get(f.city, 0) >= 2:
                continue
            if f.city in seen_cities:
                continue
            eligible.append(f)
            seen_cities.add(f.city)
        return eligible

    def _add_merger_team(self, franchise: Franchise, joined_season: int) -> Team:
        """Create a merger team: varied quality, rival-league fan base, no 80/20 split."""
        # Entering this city also clears any lingering grudge
        if franchise.city in self.market_grudges:
            del self.market_grudges[franchise.city]
            del self._grudge_metro[franchise.city]
        cfg = self.cfg
        ortg = random.uniform(cfg.merger_ortg_min, cfg.merger_ortg_max)
        drtg = random.uniform(cfg.merger_drtg_min, cfg.merger_drtg_max)
        pace = random.uniform(cfg.pace_min, cfg.pace_max)
        raw = [random.random() for _ in range(4)]
        s = sum(raw)
        ft, paint, mid, three = [r / s for r in raw]

        # Compute market baseline BEFORE adding team to avoid self-reference
        log_metros = [math.log(t.franchise.effective_metro) for t in self.teams]
        lo, hi = min(log_metros), max(log_metros)
        if hi > lo:
            norm = (math.log(franchise.effective_metro) - lo) / (hi - lo)
            baseline = 0.25 + norm * 0.50
        else:
            baseline = 0.5
        pop_fraction = random.uniform(cfg.merger_pop_fraction_min, cfg.merger_pop_fraction_max)

        new_team = Team(
            self._next_team_id, franchise,
            ortg=ortg, drtg=drtg, pace=pace,
            style_ft=ft, style_paint=paint, style_mid=mid, style_3pt=three,
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
            self._decay_grudges()
            self._evolve_popularity(season)
            self._evolve_market_engagements(season)
            self._evolve_league_popularity(season)
            self._evolve_meta()
            # Snapshot BEFORE expansion/merger changes the roster
            season._popularity = {t: t.popularity for t in self.teams}
            season._market_engagement = {t: t.market_engagement for t in self.teams}
            season._league_popularity = self.league_popularity
            self._check_expansions(season)
            self._check_merger(season)
