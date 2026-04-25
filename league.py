from __future__ import annotations

import dataclasses
import math
import random
from collections import Counter
from typing import Optional

from config import Config
from franchises import ALL_FRANCHISES, Franchise
from owner import (Owner, generate_owner, generate_heir, generate_buyers,
                   MOT_MONEY, MOT_WINNING as OWNER_MOT_WINNING, MOT_LOCAL_HERO,
                   THREAT_QUIET, THREAT_LEAN, THREAT_DEMAND)
from player import (Player, generate_player, generate_draft_class,
                    POSITIONS, MOT_LOYALTY, MOT_WINNING, MOT_MARKET)
from rival import (RivalLeague, generate_rival_league, generate_defection_league,
                   generate_walkout_league, simulate_rival_season, maybe_fire_intel_event)
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
        self.free_agent_pool: list[Player] = []
        self.draft_pool: list[Player] = []
        # Owner system
        self.departed_teams: list[Team] = []   # teams whose owners walked out
        self._assign_owners()
        # CBA state — reset each negotiation round (every 5 seasons from season 5)
        self.cba_player_happiness_mod: float = 0.0     # flat bonus/penalty for all players
        self.cba_winning_happiness_mod: float = 0.0    # winning-motivated players only
        self.cba_market_happiness_mod: float = 0.0     # market-motivated players only
        self.cba_loyalty_happiness_mod: float = 0.0    # loyalty-motivated players only
        self.cba_reloc_protection: bool = False        # halves relocation threat penalty
        self.cba_veteran_protection: bool = False      # aging stars past peak get bonus
        self.cba_revenue_share_mod: float = 0.0        # reduces commissioner treasury fraction
        self._work_stoppages: int = 0                  # lifetime work stoppages
        self._cba_log: list = []                       # history of CBA rounds
        self.work_stoppage_this_season: bool = False   # set by CBA; cleared next offseason
        self._stoppage_hangover: int = 0               # seasons of lingering fan resentment remaining
        # Rival league
        self.rival_league: RivalLeague | None = None
        self.rival_league_history: list[RivalLeague] = []
        self._rival_a_eligible_seasons: int = 0       # consecutive seasons above pop threshold
        self._last_rival_resolved: int = 0            # season number when last rival ended
        # Type B ringleader tracking
        self._ringleader_team_id: int | None = None   # team_id of the ringleader owner
        self._ringleader_demand_seasons: int = 0      # consecutive THREAT_DEMAND seasons
        self._defection_warning_season: int | None = None  # season warning was shown
        self._last_rival_b_resolved: int = 0
        # Type C walkout tracking
        self._last_rival_c_resolved: int = 0
        self._walkout_replacement_rosters: dict = {}  # team_id → list of (slot_idx, original_player | None)
        # Championship entropy: used in _recompute_all_ratings to apply regression pressure
        self._defending_champion_id: int | None = None
        self._consecutive_championships: int = 0   # how many back-to-back titles the defender has won
        # Generate founding players and compute initial team ratings from roster
        self._generate_all_founding_players()

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
            if f.nickname_options:
                f = dataclasses.replace(f, nickname=random.choice(f.nickname_options), nickname_options=[])
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
        """Seed league popularity from the market-weighted average of founding teams."""
        if not self.teams:
            return 0.35
        total_metro = sum(t.franchise.effective_metro for t in self.teams)
        if total_metro == 0:
            return 0.35
        return sum(t.popularity * t.franchise.effective_metro for t in self.teams) / total_metro

    # ── Owner assignment ──────────────────────────────────────────────────────

    def _assign_owners(self) -> None:
        """Generate and assign a founding owner for each team."""
        for team in self.teams:
            small = team.franchise.effective_metro < 3.0
            team.owner = generate_owner(small_market=small)

    # ── Revenue distribution ──────────────────────────────────────────────────

    def distribute_revenue(self) -> float:
        """Compute season revenue split. Returns commissioner share (20% of gross).

        Each team's gross = market_engagement × effective_metro × revenue_per_fan_million.
        Commissioner takes owner_treasury_share (20%); teams keep 80%.
        Owner net = team share × revenue_efficiency − operating costs.
        Net profit is stored on owner.last_net_profit for happiness computation.
        """
        cfg = self.cfg
        commissioner_take = 0.0
        max_metro = max((t.franchise.effective_metro for t in self.teams), default=1.0)
        # CBA revenue share: accepted demand reduces commissioner's treasury cut
        eff_treasury_share = max(0.05, cfg.owner_treasury_share - self.cba_revenue_share_mod)
        for team in self.teams:
            # Engagement sets the fan base; popularity scales how much revenue that base generates.
            # At average popularity (0.5) the multiplier is 1.0 — no change vs. baseline.
            pop_mult = 0.80 + 0.40 * team.popularity
            gross = team.market_engagement * pop_mult * team.franchise.effective_metro * cfg.revenue_per_fan_million
            commissioner_take += gross * eff_treasury_share
            owner_share = gross * (1.0 - eff_treasury_share)
            if team.owner is not None:
                net_revenue = owner_share * team.owner.revenue_efficiency
                # Progressive cost curve: small markets cheaper, large markets costlier.
                # Scale factor runs 0.85 (smallest) → 1.00 (largest), protecting
                # small markets from structural losses while keeping big-market advantage real.
                metro = team.franchise.effective_metro
                cost_scale = 0.85 + 0.15 * (metro / max_metro)
                op_cost = (cfg.team_cost_base
                           + metro * cfg.team_cost_per_metro * cost_scale)
                net_profit = net_revenue - op_cost
                team.owner.last_net_profit     = round(net_profit, 2)
                team.owner.cumulative_profit   += net_profit
        return round(commissioner_take, 2)

    # ── Owner happiness ───────────────────────────────────────────────────────

    def _roster_happiness_modifier(self, owner: Owner, team: Team) -> float:
        """Roster-context modifier added on top of the motivation-based happiness base.

        Owners now sense impending roster instability — not just last season's results.
        Winning owners are the most sensitive; all owners notice acute risks.

        Signals checked:
          • Franchise player (slot 0) is expiring and a likely flight risk
          • Franchise player is past prime (age ≥ 33)
          • Two or more contracts expiring at once
          • Roster has no player above replacement level
        """
        roster = [p for p in team.roster if p is not None]
        if not roster:
            return -0.12   # empty roster is a crisis for anyone

        delta = 0.0
        star = team.roster[0]   # slot 0 is the franchise star

        # Expiring franchise player who looks like a flight risk
        if star is not None and star.contract_years_remaining <= 1:
            flight_risk = star.happiness < 0.55 and star.motivation != MOT_LOYALTY
            if flight_risk:
                delta -= 0.12 if owner.motivation == OWNER_MOT_WINNING else 0.06
            else:
                delta -= 0.04   # uncertainty even without clear flight risk

        # Aging franchise player — window is closing
        if star is not None and star.age >= 33:
            delta -= 0.07 if owner.motivation == OWNER_MOT_WINNING else 0.03

        # Mass contract expiration: 2+ players coming off the books at once
        expiring = sum(1 for p in roster if p.contract_years_remaining <= 1)
        if expiring >= 2:
            delta -= 0.05 * (expiring - 1)   # -0.05 for 2, -0.10 for all 3

        # Talent desert: no player above replacement level anywhere on the roster
        if not any(p.overall >= 6 for p in roster):
            delta -= 0.08 if owner.motivation == OWNER_MOT_WINNING else 0.04

        return max(-0.25, delta)

    def _compute_owner_happiness(self, owner: Owner, team: Team, season: Season) -> float:
        """Return 0.0–1.0 season happiness score based on motivation and result."""
        if owner.motivation == MOT_MONEY:
            base = max(0.05, min(0.95, 0.50 + owner.last_net_profit * 0.008))  # was 0.06 — old scale hit ceiling at $7.5M profit

        elif owner.motivation == OWNER_MOT_WINNING:
            if season.champion is team:
                base = 0.95
            elif (season.playoff_rounds and any(
                    team in (sr.seed1, sr.seed2)
                    for sr in season.playoff_rounds[-1])):
                base = 0.82   # Finals appearance
            elif any(team in (sr.seed1, sr.seed2)
                     for rnd in season.playoff_rounds for sr in rnd):
                base = 0.65   # Playoff appearance
            else:
                # Progressive penalty for missing playoffs
                streak = team._consecutive_losing_seasons
                base = max(0.10, 0.42 - 0.04 * min(8, streak))

        else:  # MOT_LOCAL_HERO
            local_score = 0.5 * team.popularity + 0.5 * team.market_engagement
            base = max(0.10, min(0.90, 0.10 + local_score * 1.00))  # was 0.15 + score*1.40 — average team read as 0.85 (nearly maxed)

        # Roster context: owners now sense roster risk, not just last season's results
        base += self._roster_happiness_modifier(owner, team)

        return round(max(0.0, min(1.0, base)), 3)

    def _build_owner_grievance(self, owner: Owner, team: Team, season: Season) -> str:
        """Return a short grievance string for a troubled owner.

        Roster-aware: checks expiring stars, aging cores, and talent deserts before
        falling back to the standard motivation-based text.
        """
        p = owner.pronoun_cap
        pp = owner.pronoun_pos
        star = team.roster[0] if team.roster else None
        roster = [pl for pl in team.roster if pl is not None]

        # ── Roster-driven grievances (checked first; most visceral concern) ────
        if star is not None and star.contract_years_remaining <= 1:
            flight_risk = star.happiness < 0.55 and star.motivation != MOT_LOYALTY
            if flight_risk and owner.motivation == OWNER_MOT_WINNING:
                return (f"{p} is alarmed. {pp.capitalize()} franchise player is in the final year of their deal "
                        f"and does not look happy. Losing them would mean starting over.")
            elif flight_risk:
                return (f"{p} is nervous about the roster. The best player on this team could walk "
                        f"at the end of the year and {owner.pronoun} has no clear plan.")
            elif owner.motivation == OWNER_MOT_WINNING:
                return (f"{p} is watching {pp} star's contract situation closely. "
                        f"The front office needs to show it can build around them.")

        if star is not None and star.age >= 33 and owner.motivation == OWNER_MOT_WINNING:
            return (f"{p} knows the window is closing. {pp.capitalize()} best player won't be "
                    f"at this level much longer, and the pipeline behind them looks thin.")

        expiring = sum(1 for pl in roster if pl.contract_years_remaining <= 1)
        if expiring >= 2:
            return (f"{p} is looking at a roster that is almost entirely up for renewal. "
                    f"The uncertainty is making it hard to plan anything.")

        if roster and not any(pl.overall >= 6 for pl in roster):
            if owner.motivation == OWNER_MOT_WINNING:
                return (f"{p} does not see a player on this roster capable of carrying a game. "
                        f"This team needs real talent, not just bodies filling slots.")
            else:
                return (f"The product on the floor is not good enough. "
                        f"{p} expects a more watchable team.")

        # ── Standard motivation-based grievances ──────────────────────────────
        if owner.motivation == MOT_MONEY:
            if owner.last_net_profit < 0:
                return (f"{p} lost ${abs(owner.last_net_profit):.1f}M this season. "
                        f"{p} needs a bigger market or a leaner operation.")
            else:
                return f"{p} is watching {pp} margins shrink. The economics of this market concern {owner.pronoun}."

        elif owner.motivation == OWNER_MOT_WINNING:
            streak = team._consecutive_losing_seasons
            if streak >= 3:
                return (f"{p} has watched this team miss the playoffs for {streak} straight seasons. "
                        f"A contender is the only acceptable path forward.")
            return f"{p} expects more. This team isn't competing at the level {p} signed up for."

        else:  # local_hero
            return (f"The community isn't buying in. With {team.popularity:.0%} popularity "
                    f"and {team.market_engagement:.0%} market engagement, "
                    f"{owner.pronoun} feels {pp} investment isn't paying off.")

    def update_all_owner_happiness(self, season: Season) -> None:
        """Compute owner happiness from season results, update threat levels.

        Call this AFTER distribute_revenue() so last_net_profit is current.
        """
        for team in self.teams:
            if team.owner is None:
                continue
            owner = team.owner
            new_h = self._compute_owner_happiness(owner, team, season)
            # Blend: prior happiness lingers (40%), new season drives change (60%)
            owner.happiness = round(0.40 * owner.happiness + 0.60 * new_h, 3)
            owner.seasons_owned += 1
            owner.tenure_left = max(0, owner.tenure_left - 1)

            # Grievance text — set when dropping into LEAN range, clear on full recovery
            if owner.happiness < owner.lean_threshold:
                if owner.grievance is None:
                    owner.grievance = self._build_owner_grievance(owner, team, season)
            elif owner.happiness >= owner.lean_threshold + 0.10:
                owner.grievance = None

            owner.update_threat()

    # ── Losing-streak tracker ─────────────────────────────────────────────────

    def _update_losing_streaks(self, season: Season) -> None:
        """Grant championship/finals protections and update consecutive losing streaks.

        Called once per season in both headless and interactive modes.
        Does NOT prompt for relocation — that is handled by the owner meeting.
        """
        self._grant_protections(season)
        standings = season.regular_season_standings
        bottom2 = set(standings[-2:])
        for team in self.teams:
            if season.reg_win_pct(team) < 0.5:
                team._consecutive_losing_seasons += 1
                if team in bottom2:
                    team._bottom2_in_streak += 1
            else:
                team._consecutive_losing_seasons = 0
                team._bottom2_in_streak = 0

    # ── Founding player generation ────────────────────────────────────────────

    def _generate_founding_players(self, team: Team) -> None:
        """Assign one founding player per slot to a team and compute its ratings."""
        positions = list(POSITIONS)  # [Guard, Wing, Big]
        random.shuffle(positions)    # randomise which position fills which slot
        # Tier weights per slot: Star leans high, Starter leans low
        tier_weights = {
            0: [10, 30, 45, 15],   # Star:    10% elite, 30% high, 45% mid, 15% low
            1: [5,  20, 50, 25],   # Co-Star:  5% elite, 20% high, 50% mid, 25% low
            2: [2,  10, 45, 43],   # Starter:  2% elite, 10% high, 45% mid, 43% low
        }
        tiers = ["elite", "high", "mid", "low"]
        for i, pos in enumerate(positions):
            tier = random.choices(tiers, weights=tier_weights[i])[0]
            player = generate_player(position=pos, tier=tier, founding=True,
                                     contract_length=self.cfg.player_founding_contract)
            player.team_id = team.team_id
            team.roster[i] = player
        team.compute_ratings_from_roster(self.cfg)

    def _generate_all_founding_players(self) -> None:
        for team in self.teams:
            self._generate_founding_players(team)

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

    def offseason_phase1(self, season: Season) -> tuple[list[Player], list[Player]]:
        """Advance player careers and process retirements/contract expirations.

        Returns (retiring_players, new_free_agents).
        Does NOT run the draft or FA signing — call offseason_phase2() for that.
        """
        # 0a. Record defending champion for entropy regression; track consecutive title streak
        if season.champion:
            champ_id = season.champion.team_id
            if champ_id == self._defending_champion_id:
                self._consecutive_championships += 1
            else:
                self._consecutive_championships = 1
            self._defending_champion_id = champ_id
        else:
            self._defending_champion_id = None
            self._consecutive_championships = 0

        # 0b. Fatigue: accumulate from playoff exposure, then decay for all players
        team_playoff_games: dict[int, int] = {}   # team_id → playoff games played
        for round_series in season.playoff_rounds:
            for series in round_series:
                n = len(series.games)
                team_playoff_games[series.seed1.team_id] = (
                    team_playoff_games.get(series.seed1.team_id, 0) + n
                )
                team_playoff_games[series.seed2.team_id] = (
                    team_playoff_games.get(series.seed2.team_id, 0) + n
                )
        for team in self.teams:
            pg = team_playoff_games.get(team.team_id, 0)
            if pg > 0:
                for player in team.roster:
                    if player is not None:
                        player.fatigue = min(
                            1.0,
                            player.fatigue + pg * self.cfg.player_fatigue_per_playoff_game,
                        )
        # Decay fatigue for everyone (partial offseason recovery)
        all_for_decay = ([p for t in self.teams for p in t.roster if p is not None]
                         + self.free_agent_pool)
        for player in all_for_decay:
            player.fatigue *= self.cfg.player_fatigue_decay

        # 1. Record continuity before any roster changes
        for team in self.teams:
            team.update_pair_seasons()

        # 2. Advance all rostered and pool players one season
        all_players = ([p for t in self.teams for p in t.roster if p is not None]
                       + self.free_agent_pool)
        retiring: list[Player] = []
        expiring: list[Player] = []
        for player in all_players:
            player.advance_season()
            if player.retiring:
                retiring.append(player)
            elif player.contract_years_remaining == 0:
                expiring.append(player)

        # 3. Retirements — vacate roster slots
        for player in retiring:
            player.retired = True
            player.team_id = None
            for team in self.teams:
                for i, p in enumerate(team.roster):
                    if p is player:
                        team.roster[i] = None
            if player in self.free_agent_pool:
                self.free_agent_pool.remove(player)

        # 4. Compute happiness and popularity for all rostered players
        for team in self.teams:
            for player in team.roster:
                if player is not None:
                    player.happiness   = self._compute_player_happiness(player, team, season)
                    player.popularity  = self._compute_player_popularity(player, season)

        # 5. Contract expirations — re-sign or enter FA pool
        new_fas: list[Player] = []
        for player in expiring:
            if player in self.free_agent_pool:
                continue
            team = next((t for t in self.teams if player in t.roster), None)
            if team is None:
                continue
            slot_idx = team.roster.index(player)
            if self._player_re_sign_decision(player, team, season):
                cl = self._new_contract_length(player.age)
                player.contract_length           = cl
                player.contract_years_remaining  = cl
                player.seasons_with_team        += 1
            else:
                team.roster[slot_idx]  = None
                player.team_id         = None
                player.seasons_with_team = 0
                self.free_agent_pool.append(player)
                new_fas.append(player)

        # 6. Increment seasons_with_team for players still on roster (not expiring)
        expiring_set = set(id(p) for p in expiring)
        for team in self.teams:
            for player in team.roster:
                if player is not None and id(player) not in expiring_set:
                    player.seasons_with_team += 1

        # 7. Clean up FA pool
        self.free_agent_pool = [p for p in self.free_agent_pool
                                 if not p.retired and not p.retiring]

        # 8. Generate draft class (held in self.draft_pool for interactive draft)
        n_draft = max(self.cfg.draft_class_base, len(self.teams) // 4)
        talent_boost = min(1.0, self._talent_boost_delta) if self._talent_boost_seasons_left > 0 else 0.0
        self.draft_pool = generate_draft_class(n_draft, talent_boost=talent_boost)
        if self._talent_boost_seasons_left > 0:
            self._talent_boost_seasons_left -= 1

        return retiring, new_fas

    def offseason_phase2(self) -> None:
        """Auto-fill remaining empty slots via draft and FA, then recompute ratings.

        Called after the interactive draft/FA screens have had their turn.
        """
        self._run_auto_draft()
        self._run_auto_fa()
        max_fa = len(self.teams) * self.cfg.fa_pool_per_team
        self.free_agent_pool = sorted(self.free_agent_pool,
                                      key=lambda p: -p.overall)[:max_fa]
        self._recompute_all_ratings()

    def _offseason_adjustments(self, season: Season) -> None:
        """Full auto offseason — used by the headless simulator (main.py)."""
        self.offseason_phase1(season)
        self.offseason_phase2()

    def start_talent_investment(self, delta: float, seasons: int) -> None:
        """Boost draft class quality for the given number of seasons.

        delta (0–1): talent_boost passed to generate_draft_class — shifts weights
        toward elite/high tiers. Takes the max of any existing boost.
        """
        self._talent_boost_seasons_left += seasons
        self._talent_boost_delta = max(self._talent_boost_delta, delta)

    # ── Player movement helpers ───────────────────────────────────────────────

    def _compute_player_happiness(self, player: Player, team: Team,
                                   season: Season) -> float:
        """Return 0.0–1.0 happiness based on player motivation and situation."""
        if player.motivation == MOT_WINNING:
            # Did the team make the playoffs? Win the title?
            if season.champion is team:
                base = 1.0
            elif any(team in (sr.seed1, sr.seed2)
                     for rnd in season.playoff_rounds for sr in rnd
                     if rnd is season.playoff_rounds[-1]):
                base = 0.85   # Finals appearance
            elif any(team in (sr.seed1, sr.seed2)
                     for rnd in season.playoff_rounds for sr in rnd):
                base = 0.68   # Playoff appearance
            else:
                base = 0.28   # Missed playoffs
            # Net rating bonus/penalty (±0.08)
            avg_net = (sum(t.ortg - t.drtg for t in season.teams) / len(season.teams)
                       if season.teams else 0)
            net_delta = (team.ortg - team.drtg) - avg_net
            base += max(-0.08, min(0.08, net_delta * 0.01))

        elif player.motivation == MOT_MARKET:
            avg_draw = (sum(t.franchise.draw_factor * t.franchise.effective_metro
                            for t in self.teams) / len(self.teams)) if self.teams else 1.0
            team_draw = team.franchise.draw_factor * team.franchise.effective_metro
            ratio = team_draw / avg_draw if avg_draw > 0 else 1.0
            # ratio 1.5+ → ~0.90, ratio 0.5 → ~0.35
            base = max(0.10, min(0.95, 0.35 + (ratio - 0.5) * 0.55))

        else:  # MOT_LOYALTY
            swt = player.seasons_with_team
            if   swt >= 5: base = 0.88
            elif swt >= 3: base = 0.75
            elif swt >= 1: base = 0.62
            else:          base = 0.50
            # Very bad team dampens even loyal players
            net = team.ortg - team.drtg
            if net < -5:
                base = max(0.30, base - 0.12)

        # Owner context: management quality and stability affect the locker room
        owner = team.owner
        if owner is not None:
            # Competence: effective management makes players more comfortable
            # Range: roughly −0.135 (floor competence) to +0.053 (ceiling)
            base += (owner.competence - 0.65) * 0.15
            # Active talent investment signals commitment to winning
            if self._talent_boost_seasons_left > 0:
                base += 0.05
            # Relocation threat creates instability and uncertainty
            if owner.threat_level == THREAT_DEMAND:
                penalty = 0.04 if self.cba_reloc_protection else 0.08
                base -= penalty
            elif owner.threat_level == THREAT_LEAN:
                base -= 0.03

        # CBA terms — apply motivation-specific and universal modifiers
        base += self.cba_player_happiness_mod
        if player.motivation == MOT_WINNING:
            base += self.cba_winning_happiness_mod
        elif player.motivation == MOT_MARKET:
            base += self.cba_market_happiness_mod
        else:  # MOT_LOYALTY
            base += self.cba_loyalty_happiness_mod
        # Veteran protection: aging players past their peak feel more secure
        if self.cba_veteran_protection and player.seasons_played > player.peak_season:
            base += 0.04

        return round(max(0.0, min(1.0, base)), 3)

    def _compute_player_popularity(self, player: Player, season: Season) -> float:
        """Return 0.0–1.0 popularity. Blends prior reputation with current season."""
        # Quality component (0–0.35)
        ov = player.overall
        if   ov >= 16: quality = 0.35
        elif ov >= 12: quality = 0.25
        elif ov >= 8:  quality = 0.15
        elif ov >= 4:  quality = 0.07
        else:          quality = 0.02

        # Wins component (0–0.15)
        team = next((t for t in self.teams if player in t.roster), None)
        if team and season.teams:
            win_pct = season.reg_win_pct(team) if team in season.teams else 0.5
            wins_comp = win_pct * 0.15
        else:
            wins_comp = 0.0

        # Awards (additive, capped)
        awards = 0.0
        if season.mvp is player or season.finals_mvp is player:
            awards += 0.22
        elif season.dpoy is player:
            awards += 0.15

        # Championships (0–0.20)
        champ_comp = min(0.20, player.seasons_played * 0.0
                         + sum(0.08 for s in self.seasons if s.champion is team) * 0.0)
        # Simpler: count championships on current team object
        champ_comp = min(0.20, (team.championships if team else 0) * 0.07)

        # Loyalty bonus (0–0.06)
        loyalty_comp = min(0.06, player.seasons_with_team * 0.012)

        new_pop = min(1.0, quality + wins_comp + awards + champ_comp + loyalty_comp)

        # Blend with prior popularity (reputation lingers)
        blended = 0.40 * player.popularity + 0.60 * new_pop
        return round(max(0.0, min(1.0, blended)), 3)

    def _player_re_sign_decision(self, player: Player, team: Team,
                                  season: Season) -> bool:
        """Return True if the player re-signs. Driven by motivation and situation."""
        if player.motivation == MOT_LOYALTY:
            # Loyal players lean strongly toward staying with familiar teams
            base_prob = 0.40 + player.happiness * 0.55
        elif player.motivation == MOT_WINNING:
            # Winning players leave bad teams even when otherwise happy
            standings = season.regular_season_standings if season.teams else []
            n = len(standings)
            if n > 1 and team in standings:
                rank_frac = standings.index(team) / (n - 1)  # 0.0 = best, 1.0 = worst
            else:
                rank_frac = 0.5
            base_prob = max(0.10, 0.75 - rank_frac * 0.60)   # best ~0.75, worst ~0.15
        else:  # MOT_MARKET
            # Market players stay when their market is above average
            avg_draw = (sum(t.franchise.draw_factor * t.franchise.effective_metro
                            for t in self.teams) / len(self.teams)) if self.teams else 1.0
            team_draw = team.franchise.draw_factor * team.franchise.effective_metro
            ratio = team_draw / avg_draw if avg_draw > 0 else 1.0
            base_prob = max(0.15, min(0.80, 0.20 + ratio * 0.45))
        # Universal market pull: all players are somewhat swayed by market size
        # (a big market can nudge a winning player to stay; a tiny one nudges departure)
        avg_metro = (sum(t.franchise.effective_metro for t in self.teams) / len(self.teams)
                     ) if self.teams else 1.0
        market_ratio = team.franchise.effective_metro / avg_metro if avg_metro > 0 else 1.0
        base_prob = max(0.08, min(0.85, base_prob + (market_ratio - 1.0) * 0.06))
        # Popular players are sticky — local legend effect
        pop_bonus = player.popularity * 0.10
        return random.random() < min(0.92, base_prob + pop_bonus)

    @staticmethod
    def _new_contract_length(age: int) -> int:
        if age <= 25:   return random.randint(3, 5)
        elif age <= 30: return random.randint(2, 4)
        else:           return random.randint(2, 3)

    def _run_auto_draft(self) -> None:
        """Assign draft prospects to empty roster slots, worst teams first."""
        if not self.seasons or not self.draft_pool:
            return
        standings = self.seasons[-1].regular_season_standings
        draft_order = list(reversed(standings))  # worst record picks first
        # Also include any teams not in standings (newly added this offseason)
        in_standings = set(standings)
        draft_order += [t for t in self.teams if t not in in_standings]

        idx = 0
        for team in draft_order:
            if idx >= len(self.draft_pool):
                break
            for i, slot in enumerate(team.roster):
                if slot is None and idx < len(self.draft_pool):
                    p = self.draft_pool[idx]
                    p.team_id = team.team_id
                    p.seasons_with_team = 0
                    team.roster[i] = p
                    idx += 1
                    break  # one pick per team per round

        # Undrafted prospects enter the FA pool
        self.free_agent_pool.extend(self.draft_pool[idx:])
        self.draft_pool = []

    def _run_auto_fa(self) -> None:
        """Fill remaining empty slots from the free agent pool.

        Players choose teams based on motivation:
          MOT_WINNING → prefers teams with the best net rating (contenders)
          MOT_MARKET  → prefers teams by draw_factor × effective_metro
          MOT_LOYALTY → no strong preference; takes any open slot
        Stars (higher overall) choose first, giving them destination leverage.
        """
        available = sorted(self.free_agent_pool, key=lambda p: -p.overall)
        signed: list[Player] = []

        for player in available:
            open_teams = [t for t in self.teams if any(s is None for s in t.roster)]
            if not open_teams:
                break

            if player.motivation == MOT_WINNING:
                scored = sorted(open_teams, key=lambda t: -(t.ortg - t.drtg))
            elif player.motivation == MOT_MARKET:
                scored = sorted(open_teams,
                                key=lambda t: -(t.franchise.draw_factor
                                                * t.franchise.effective_metro))
            else:  # MOT_LOYALTY — no strong directional preference
                scored = open_teams

            target = scored[0]
            slot_idx = next(i for i, s in enumerate(target.roster) if s is None)
            cl = self._new_contract_length(player.age)
            player.contract_length          = cl
            player.contract_years_remaining = cl
            player.team_id                  = target.team_id
            player.seasons_with_team        = 0
            target.roster[slot_idx]         = player
            signed.append(player)

        for p in signed:
            if p in self.free_agent_pool:
                self.free_agent_pool.remove(p)

    def _recompute_all_ratings(self) -> None:
        for team in self.teams:
            team.compute_ratings_from_roster(self.cfg)
        # Championship entropy: defending champion's ratings regress toward baseline.
        # Simulates opponents studying more tape, harder-to-maintain peak motivation,
        # and the general difficulty of repeating at the highest level.
        # Compounding: each consecutive title applies the factor one more time (up to 3x),
        # so dynasties face escalating — but never crushing — regression pressure.
        if self._defending_champion_id is not None and self._consecutive_championships > 0:
            champ = next((t for t in self.teams if t.team_id == self._defending_champion_id), None)
            if champ is not None:
                times = min(self._consecutive_championships, 3)
                f = self.cfg.champion_entropy_factor ** times
                baseline_o = self.cfg.ortg_baseline
                baseline_d = self.cfg.drtg_baseline
                champ.ortg = baseline_o + (champ.ortg - baseline_o) * f
                champ.drtg = baseline_d + (champ.drtg - baseline_d) * f
                champ.ortg = max(self.cfg.ortg_min, min(self.cfg.ortg_max, champ.ortg))
                champ.drtg = max(self.cfg.drtg_min, min(self.cfg.drtg_max, champ.drtg))

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

            # Star power: elite players lift team popularity each season
            for player in team.roster:
                if player is not None:
                    ov = player.overall
                    if   ov >= 16: delta += 0.020   # elite star
                    elif ov >= 12: delta += 0.010   # all-star caliber
                    elif ov >= 8:  delta += 0.004   # solid starter

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

            # Performance signals — muted to 30%; the other 70% flows through team.popularity.
            # Market engagement tracks city affinity with the league, not team-specific heat.
            if team is season.champion:
                delta += 0.012
            elif team is finalist:
                delta += 0.008
            elif team in playoff_teams:
                delta += 0.004
            else:
                # Progressive penalty — city interest cools after repeated losing seasons
                misses = team._consecutive_playoff_misses
                delta -= min(0.008, 0.0015 * misses)
                if team in bottom2:
                    delta -= 0.005

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

            # Work stoppage hangover: fans are slow to come back — cap recovery
            if self._stoppage_hangover > 0:
                delta = min(delta, 0.004)   # recovery crawls while resentment lingers

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

        # ── Base: pull toward composite of engagement + team popularity ─────────
        # De-duplicate shared markets so co-tenant cities count once at full weight.
        city_engs: dict = {}
        city_pops: dict = {}
        city_metro: dict = {}
        for team in self.teams:
            city = team.franchise.city
            city_engs.setdefault(city, []).append(team.market_engagement)
            city_pops.setdefault(city, []).append(team.popularity)
            city_metro[city] = max(city_metro.get(city, 0.0),
                                   team.franchise.effective_metro)
        total_w = sum(city_metro.values())
        avg_eng = sum(
            (sum(engs) / len(engs)) * city_metro[city]
            for city, engs in city_engs.items()
        ) / total_w
        avg_pop = sum(
            (sum(pops) / len(pops)) * city_metro[city]
            for city, pops in city_pops.items()
        ) / total_w
        # League popularity is a composite: city affinity + team brand equity
        composite = 0.5 * avg_eng + 0.5 * avg_pop
        fan_pull = cfg.league_pop_engagement_pull * (composite - self.league_popularity)
        signals["Fan composite"] = fan_pull
        delta += fan_pull

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
            # Neutral at league avg engagement; above → positive buzz, below → muted.
            # Using dynamic avg_eng (not fixed 0.30) so early seasons aren't always negative.
            neutral = avg_eng if avg_eng > 0 else 0.30
            finals_delta = cfg.league_pop_finals_interest_scale * (avg_engagement - neutral) / neutral
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

        # ── Work stoppage hangover: multi-season fan resentment ───────────────
        # Fades over 5 seasons: catastrophic → severe → moderate → lingering → trace
        # Modelled on 1994 MLB strike — took the '98 home run chase to fully recover.
        if self._stoppage_hangover > 0:
            hangover_delta = {
                5: -0.070,   # year 1: catastrophic — season cancelled, fans furious
                4: -0.045,   # year 2: severe — trust not rebuilt
                3: -0.025,   # year 3: moderate — scars still visible
                2: -0.010,   # year 4: lingering resentment
                1: -0.005,   # year 5: trace — needs something special to fully heal
            }.get(self._stoppage_hangover, 0.0)
            signals["Work stoppage hangover"] = hangover_delta
            delta += hangover_delta
            self._stoppage_hangover -= 1

        delta = self.apply_rival_popularity_dampening(delta)
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
        # Auto meta shock removed — the commissioner's desk rule change is the
        # only mechanism that can deliberately shift or reset the meta.

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
        original_franchise = franchise   # keep reference for reserve_pool removal
        is_secondary = franchise.secondary
        cfg = self.cfg

        # Entering this city clears any lingering grudge
        if franchise.city in self.market_grudges:
            del self.market_grudges[franchise.city]
            del self._grudge_metro[franchise.city]

        if franchise.nickname_options:
            franchise = dataclasses.replace(franchise, nickname=random.choice(franchise.nickname_options), nickname_options=[])

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
        self.reserve_pool.remove(original_franchise)
        self._generate_founding_players(new_team)
        new_team.owner = generate_owner(small_market=new_team.franchise.effective_metro < 3.0)
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

    # ── Rival league (Type A — external investors) ───────────────────────────

    def check_rival_league_trigger(self, season_num: int) -> bool:
        """Check whether a new Type A rival league should form this offseason.

        Returns True if a rival just formed (commissioner needs to show the event).
        Does nothing if a rival is already active or cooldown hasn't expired.
        """
        cfg = self.cfg
        if self.rival_league is not None and self.rival_league.active:
            return False
        if season_num < cfg.rival_a_min_season:
            return False
        if (self._last_rival_resolved > 0
                and season_num - self._last_rival_resolved < cfg.rival_a_cooldown):
            return False

        if self.league_popularity >= cfg.rival_a_popularity_threshold:
            self._rival_a_eligible_seasons += 1
        else:
            self._rival_a_eligible_seasons = 0
            return False

        if self._rival_a_eligible_seasons < cfg.rival_a_consecutive_seasons:
            return False

        # Trigger: spawn a new Type A rival league
        self._rival_a_eligible_seasons = 0
        funding = random.uniform(cfg.rival_a_funding_min, cfg.rival_a_funding_max)
        n_teams = random.randint(cfg.rival_a_teams_min, cfg.rival_a_teams_max)
        occupied = {t.franchise.city for t in self.teams}
        league_name = getattr(self, '_league_name', '')   # commissioner sets this if available

        self.rival_league = generate_rival_league(
            formed_season=season_num,
            formation_type="external",
            funding=funding,
            main_league_name=league_name,
            occupied_cities=occupied,
            n_teams=n_teams,
        )
        return True

    def advance_rival_season(self, season_num: int) -> tuple[RivalLeague, str | None]:
        """Simulate the rival league's season and apply passive strength growth.

        Returns (rival, intel_message_or_None).
        Call this each offseason while a rival is active, BEFORE showing the
        commissioner decision event so the record is up to date.
        """
        rival = self.rival_league
        if rival is None or not rival.active:
            return rival, None

        record = simulate_rival_season(rival, season_num)
        # Type C decays naturally; Type A/B grows passively
        if rival.formation_type == "walkout":
            delta = self.cfg.rival_c_player_circuit_decay
        else:
            delta = self.cfg.rival_strength_base_growth
        record.strength_delta = delta
        rival.strength = max(0.0, min(1.0, rival.strength + delta))
        rival.season_records.append(record)

        # Check intel event
        intel = maybe_fire_intel_event(rival, season_num)
        if intel:
            rival.intel_events.append((season_num, intel))

        # Type A passive legitimacy drain: a growing external rival erodes commissioner authority
        # by poaching free agents, courting owners, and winning media narratives.
        if rival.formation_type == "external" and rival.strength >= self.cfg.rival_a_legit_drain_threshold:
            drain = self.cfg.rival_a_legit_drain_rate
            self.legitimacy = max(0.0, self.legitimacy - drain)

        return rival, intel

    def apply_rival_commissioner_action(
        self,
        action: str,            # "monitor" | "talent_war" | "legal" | "merger"
        season_num: int,
    ) -> tuple[float, float, str]:
        """Apply a commissioner action against the rival. Returns (treasury_cost, legit_cost, summary).

        The strength delta from the action is on top of the passive growth already applied
        in advance_rival_season().
        """
        cfg = self.cfg
        rival = self.rival_league
        if rival is None or not rival.active:
            return 0.0, 0.0, "No active rival league."

        if action == "monitor":
            # Extra passive growth beyond the base already applied
            extra = 0.02
            rival.strength = min(1.0, rival.strength + extra)
            if rival.season_records:
                rival.season_records[-1].strength_delta += extra
            return 0.0, 0.0, f"The {rival.name} grows unchecked."

        elif action == "talent_war":
            cost = random.uniform(cfg.rival_talent_war_cost_min, cfg.rival_talent_war_cost_max)
            delta = cfg.rival_talent_war_strength_delta
            rival.strength = max(0.0, rival.strength + delta)
            if rival.season_records:
                rival.season_records[-1].strength_delta += delta
            return cost, 0.0, (
                f"Talent war launched. ${cost:.0f}M spent locking up key free agents. "
                f"The {rival.short_name} loses ground."
            )

        elif action == "legal":
            delta = cfg.rival_legal_pressure_strength_delta
            legit = cfg.rival_legal_pressure_legit_cost
            rival.strength = max(0.0, rival.strength + delta)
            if rival.season_records:
                rival.season_records[-1].strength_delta += delta
            return 0.0, legit, (
                f"Legal and media pressure applied. The {rival.short_name}'s broadcast "
                f"and stadium deals face challenges. Your legitimacy takes a hit."
            )

        elif action == "merger":
            cost = random.uniform(cfg.rival_brokered_merger_cost_min, cfg.rival_brokered_merger_cost_max)
            legit = cfg.rival_brokered_merger_legit_cost
            # Resolve: rival dissolves, commissioner absorbs some teams
            n_absorb = min(len(rival.teams), random.randint(2, 4))
            absorbed = [t.name for t in rival.teams[:n_absorb]]
            self._resolve_rival(season_num, resolution="brokered_merger")
            summary = (
                f"Merger terms agreed. ${cost:.0f}M paid to dissolve the {rival.name}. "
                f"{n_absorb} franchise{'s' if n_absorb != 1 else ''} absorbed into the league: "
                + ", ".join(absorbed) + "."
            )
            return cost, legit, summary

        return 0.0, 0.0, "Unknown action."

    def check_rival_resolution(self, season_num: int) -> str | None:
        """Check for automatic resolution conditions. Returns resolution type or None."""
        rival = self.rival_league
        if rival is None or not rival.active:
            return None
        cfg = self.cfg
        if rival.strength <= cfg.rival_strength_collapse_threshold:
            self._resolve_rival(season_num, resolution="collapse")
            return "collapse"
        if (self.legitimacy <= cfg.rival_forced_merger_legitimacy
                and rival.strength >= cfg.rival_forced_merger_strength):
            self._resolve_rival(season_num, resolution="forced_merger")
            return "forced_merger"
        return None

    def _resolve_rival(self, season_num: int, resolution: str) -> None:
        """Mark rival as inactive and move to history."""
        rival = self.rival_league
        if rival is None:
            return
        rival.active = False
        self.rival_league_history.append(rival)
        self.rival_league = None
        self._last_rival_resolved = season_num

        if rival.formation_type == "defection":
            self._last_rival_b_resolved = season_num
        elif rival.formation_type == "walkout":
            self._last_rival_c_resolved = season_num

        if resolution == "collapse":
            self.league_popularity = min(1.0, self.league_popularity + 0.03)
        elif resolution in ("win_back", "concession", "partial_deal"):
            # Modest positive signal — crisis resolved without full capitulation
            self.league_popularity = min(1.0, self.league_popularity + 0.01)

    def apply_rival_passive_fa_pull(self) -> int:
        """Remove a portion of the FA pool to rival contracts. Returns count removed."""
        rival = self.rival_league
        if rival is None or not rival.active or not self.free_agent_pool:
            return 0
        pull = rival.rival_fa_pull
        n_remove = max(0, round(len(self.free_agent_pool) * pull))
        # Remove the weakest players first (rivals sign bargain talent)
        self.free_agent_pool.sort(key=lambda p: p.overall, reverse=True)
        removed = self.free_agent_pool[len(self.free_agent_pool) - n_remove:]
        self.free_agent_pool = self.free_agent_pool[:len(self.free_agent_pool) - n_remove]
        return len(removed)

    def apply_rival_popularity_dampening(self, raw_delta: float) -> float:
        """If rival is strong enough, dampen league popularity growth this season."""
        rival = self.rival_league
        if rival is None or not rival.active:
            return raw_delta
        if rival.strength >= self.cfg.rival_pop_dampening_threshold:
            return raw_delta * self.cfg.rival_pop_dampening_factor
        return raw_delta

    # ── Type B: Owner defection ────────────────────────────────────────────────

    def check_rival_b_ringleader(self, season_num: int) -> tuple[str | None, list]:
        """Detect and track a ringleader; return (warning_message, defecting_teams) or (None, []).

        Call each offseason. Returns a warning message in the season BEFORE defection fires,
        or a (message, teams) tuple when defection actually happens.

        States:
          - No ringleader: scan for a THREAT_DEMAND owner with low loyalty
          - Ringleader found: count DEMAND seasons; build follower list
          - After ringleader_seasons: fire or fail
        """
        cfg = self.cfg
        if self.rival_league is not None and self.rival_league.active:
            return None, []
        if season_num < cfg.rival_b_min_season:
            return None, []
        if (self._last_rival_b_resolved > 0
                and season_num - self._last_rival_b_resolved < cfg.rival_b_cooldown):
            return None, []

        # Find / update ringleader
        ringleader_team = None
        if self._ringleader_team_id is not None:
            ringleader_team = next(
                (t for t in self.teams if t.team_id == self._ringleader_team_id), None
            )
            if (ringleader_team is None
                    or ringleader_team.owner is None
                    or ringleader_team.owner.threat_level != THREAT_DEMAND):
                # Ringleader calmed down or sold — reset
                self._ringleader_team_id = None
                self._ringleader_demand_seasons = 0
                self._defection_warning_season = None
                ringleader_team = None

        if ringleader_team is None:
            # Scan for a new ringleader: THREAT_DEMAND + low_loyalty + renegade preferred
            candidates = [
                t for t in self.teams
                if t.owner is not None
                and t.owner.threat_level == THREAT_DEMAND
                and t.owner.loyalty == "low_loyalty"
            ]
            if not candidates:
                return None, []
            # Prefer renegade personality
            renegades = [t for t in candidates if t.owner.personality == "renegade"]
            ringleader_team = random.choice(renegades if renegades else candidates)
            self._ringleader_team_id = ringleader_team.team_id
            self._ringleader_demand_seasons = 1
            self._defection_warning_season = None
            return None, []

        # Ringleader exists — increment demand counter
        self._ringleader_demand_seasons += 1

        # Warning window: one season before defection fires
        warning_thresh = cfg.rival_b_ringleader_seasons
        if self._ringleader_demand_seasons == warning_thresh:
            self._defection_warning_season = season_num
            owner = ringleader_team.owner
            return (
                f"{owner.name} ({ringleader_team.franchise.name}) is reportedly in contact "
                f"with other ownership groups about alternative arrangements.",
                [],
            )

        # Defection fires after ringleader_seasons + 1 seasons at DEMAND
        if self._ringleader_demand_seasons > warning_thresh:
            return self._fire_defection(ringleader_team, season_num)

        return None, []

    def _fire_defection(self, ringleader_team: "Team", season_num: int) -> tuple[str, list]:
        """Resolve owner defection: recruit followers, remove teams, spawn rival."""
        cfg = self.cfg
        ringleader_owner = ringleader_team.owner

        # Recruit followers based on threat level
        defectors = [ringleader_team]
        for team in self.teams:
            if team is ringleader_team:
                continue
            if team.owner is None:
                continue
            tl = team.owner.threat_level
            if tl == THREAT_DEMAND:
                prob = cfg.rival_b_follow_prob_demand
            elif tl == THREAT_LEAN:
                prob = cfg.rival_b_follow_prob_lean
            else:
                prob = cfg.rival_b_follow_prob_quiet
            if random.random() < prob:
                defectors.append(team)

        if len(defectors) < cfg.rival_b_min_defectors:
            # Attempt fails — ringleader forced out, threat cools
            ringleader_name = ringleader_owner.name if ringleader_owner else "The ringleader"
            self._ringleader_team_id = None
            self._ringleader_demand_seasons = 0
            self._defection_warning_season = None
            # Force ownership change on ringleader
            if ringleader_owner is not None:
                from owner import generate_buyers
                buyers = generate_buyers(n=1)
                ringleader_team.owner = buyers[0]
            # Cool threat on followers
            for team in self.teams:
                if team.owner is not None and team.owner.threat_level == THREAT_DEMAND:
                    team.owner.threat_level = THREAT_LEAN
            msg = (f"The defection plot collapsed. {ringleader_name} failed to recruit enough "
                   f"owners and was forced to sell the franchise.")
            return msg, []

        # Defection fires — remove teams from the league
        league_name = getattr(self, '_league_name', '')
        rival = generate_defection_league(
            formed_season=season_num,
            ringleader_name=ringleader_owner.name if ringleader_owner else "Unknown",
            defected_teams=defectors,
            main_league_name=league_name,
        )
        self.rival_league = rival

        # Remove defecting teams from the commissioner's league
        for team in defectors:
            if team in self.teams:
                self.teams.remove(team)
                self.departed_teams.append(team)
                # Their franchise goes back to reserve pool so cities can be re-entered
                self.reserve_pool.append(team.franchise)

        self._ringleader_team_id = None
        self._ringleader_demand_seasons = 0
        self._defection_warning_season = None

        names = ", ".join(t.franchise.name for t in defectors)
        return (
            f"{len(defectors)} franchises have defected: {names}. "
            f"They have formed the {rival.name} under {rival.ringleader_owner_name}.",
            defectors,
        )

    def apply_rival_b_commissioner_action(
        self,
        action: str,        # "monitor" | "win_back" | "expand" | "legal"
        season_num: int,
    ) -> tuple[float, float, str]:
        """Apply a Type B commissioner action. Returns (treasury_cost, legit_cost, summary)."""
        cfg = self.cfg
        rival = self.rival_league
        if rival is None or not rival.active or rival.formation_type != "defection":
            return 0.0, 0.0, "No active Type B rival."

        if action == "monitor":
            extra = 0.02
            rival.strength = min(1.0, rival.strength + extra)
            return 0.0, 0.0, f"The {rival.name} continues to operate unchallenged."

        elif action == "win_back":
            cost = random.uniform(cfg.rival_b_win_back_cost_min, cfg.rival_b_win_back_cost_max)
            legit = cfg.rival_b_win_back_legit_cost
            returned_teams = []
            still_out = []
            for rt in list(rival.teams):
                if random.random() < cfg.rival_b_win_back_prob:
                    returned_teams.append(rt)
                else:
                    still_out.append(rt)

            if returned_teams:
                # Re-absorb returned teams into the commissioner's league
                for rt in returned_teams:
                    # Find the original departed team and restore it
                    orig = next(
                        (t for t in self.departed_teams if t.team_id == rt.original_team_id),
                        None,
                    )
                    if orig is not None:
                        self.teams.append(orig)
                        self.departed_teams.remove(orig)
                        if orig.franchise in self.reserve_pool:
                            self.reserve_pool.remove(orig.franchise)
                    rival.teams.remove(rt)

            if not rival.teams:
                self._resolve_rival(season_num, resolution="win_back")
                summary = (f"All defecting owners agreed to return. ${cost:.0f}M spent. "
                           f"The {rival.name} has dissolved.")
            elif returned_teams:
                rival.strength = max(0.0, rival.strength - 0.15)
                summary = (f"{len(returned_teams)} franchise(s) returned. ${cost:.0f}M spent. "
                           f"{len(still_out)} still operating under {rival.short_name}.")
            else:
                summary = (f"Negotiations failed — no teams returned. ${cost:.0f}M wasted. "
                           f"The {rival.short_name} remains intact.")

            return cost, legit, summary

        elif action == "legal":
            delta = cfg.rival_legal_pressure_strength_delta
            legit = cfg.rival_legal_pressure_legit_cost
            rival.strength = max(0.0, rival.strength + delta)
            return 0.0, legit, (
                f"Legal challenges filed against the {rival.name}. "
                f"Their broadcast and venue deals face pressure."
            )

        elif action == "expand":
            # Commissioner can add an expansion team to fill the gap
            return 0.0, 0.0, "Use the expansion decision tool to add a new franchise."

        return 0.0, 0.0, "Unknown action."

    # ── Type C: Player walkout ─────────────────────────────────────────────────

    def check_rival_c_trigger(self, season_num: int) -> bool:
        """Check if a work stoppage should escalate to a player walkout (Type C rival).

        Called by commissioner.py after a failed CBA negotiation results in a work stoppage.
        Returns True if a walkout rival league forms.
        """
        cfg = self.cfg
        if self.rival_league is not None and self.rival_league.active:
            return False
        if season_num < cfg.rival_c_min_season:
            return False
        if (self._last_rival_c_resolved > 0
                and season_num - self._last_rival_c_resolved < cfg.rival_c_cooldown):
            return False

        league_name = getattr(self, '_league_name', '')
        n_teams = random.randint(4, 8)
        rival = generate_walkout_league(
            formed_season=season_num,
            main_league_name=league_name,
            n_teams=n_teams,
        )
        self.rival_league = rival
        return True

    def apply_walkout_season_effects(self) -> None:
        """Apply per-season penalties while a Type C walkout is active.

        Call this once per season during the offseason when walkout is ongoing.
        Decreases league popularity and legitimacy; degrades the player circuit strength.
        """
        cfg = self.cfg
        rival = self.rival_league
        if rival is None or not rival.active or rival.formation_type != "walkout":
            return
        # Player circuit degrades naturally — no real infrastructure
        rival.strength = max(0.0, rival.strength + cfg.rival_c_player_circuit_decay)
        # Fan engagement and legitimacy suffer
        self.league_popularity = max(
            0.0, self.league_popularity + cfg.rival_c_fan_engagement_penalty
        )
        self.legitimacy = max(0.0, self.legitimacy + cfg.rival_c_legitimacy_penalty)

    def install_replacement_rosters(self) -> list[str]:
        """Replace all rostered players with scab/replacement players for a walkout season.

        Saves originals in _walkout_replacement_rosters for restoration.
        Returns list of scab star event messages (for named scab events).
        """
        from player import generate_player, POSITIONS
        scab_events: list[str] = []
        self._walkout_replacement_rosters = {}

        for team in self.teams:
            saved = []
            for i, player in enumerate(team.roster):
                saved.append((i, player))  # save original (may be None)
                if player is not None:
                    # Move player off roster — they're striking
                    player.team_id = None
                    team.roster[i] = None

            self._walkout_replacement_rosters[team.team_id] = saved

            # Fill slots with replacement players
            for i, (slot_idx, original) in enumerate(saved):
                if original is None:
                    continue  # slot was already empty
                # Check FA pool for a scab: use a willing free agent first
                fa_candidate = None
                if self.free_agent_pool:
                    fa_candidate = self.free_agent_pool.pop(0)

                if fa_candidate is not None:
                    fa_candidate.crossed_picket = True
                    fa_candidate.team_id = team.team_id
                    team.roster[slot_idx] = fa_candidate
                    if self.rival_league:
                        self.rival_league.scab_player_ids.append(fa_candidate.player_id)
                    # Named scab star event for above-threshold players
                    if fa_candidate.overall >= self.cfg.star_fa_threshold * 0.6:
                        scab_events.append(
                            f"{fa_candidate.name} ({fa_candidate.position}) has signed "
                            f"a replacement contract with {team.franchise.name}."
                        )
                else:
                    # Generate a low-rated replacement nobody
                    pos = POSITIONS[slot_idx % len(POSITIONS)]
                    repl = generate_player(position=pos, tier="low", contract_length=1)
                    repl.crossed_picket = True
                    repl.team_id = team.team_id
                    team.roster[slot_idx] = repl
                    if self.rival_league:
                        self.rival_league.scab_player_ids.append(repl.player_id)

        self._recompute_all_ratings()
        return scab_events

    def restore_regular_rosters(self, concession_level: float = 0.0) -> list[str]:
        """Restore original players after a walkout ends. Release scab players.

        concession_level (0.0–1.0): how much the commissioner conceded.
          0.0 = hold firm (unhappy players return with happiness penalty)
          0.5 = partial deal
          1.0 = full concessions (players return with modest happiness boost)

        Returns list of event messages.
        """
        cfg = self.cfg
        events: list[str] = []

        for team in self.teams:
            saved = self._walkout_replacement_rosters.get(team.team_id, [])

            # Identify and release scab players currently on the roster
            for i, player in enumerate(team.roster):
                if player is not None and getattr(player, 'crossed_picket', False):
                    # Scab players return to FA pool with crossed_picket flag intact
                    player.team_id = None
                    team.roster[i] = None
                    self.free_agent_pool.append(player)

            # Restore original players
            for slot_idx, original in saved:
                if original is None:
                    continue
                if original.retired:
                    continue
                # Happiness adjustment based on concession level
                happiness_mod = (
                    -abs(cfg.rival_c_scab_happiness_penalty) * (1.0 - concession_level)
                    + 0.05 * concession_level
                )
                original.happiness = max(0.0, min(1.0, original.happiness + happiness_mod))
                original.team_id = team.team_id
                team.roster[slot_idx] = original

            events.append(f"{team.franchise.name} players have returned to the roster.")

        self._walkout_replacement_rosters = {}
        self._recompute_all_ratings()
        return events

    def apply_rival_c_commissioner_action(
        self,
        action: str,       # "hold_firm" | "concede" | "partial"
        season_num: int,
    ) -> tuple[float, float, str]:
        """Apply a Type C commissioner action. Returns (treasury_cost, legit_cost, summary)."""
        cfg = self.cfg
        rival = self.rival_league
        if rival is None or not rival.active or rival.formation_type != "walkout":
            return 0.0, 0.0, "No active Type C rival."

        if action == "hold_firm":
            # Season runs with replacements again; circuit continues to degrade
            self.apply_walkout_season_effects()
            return 0.0, 0.0, (
                "The league holds firm. Replacement ball continues. "
                "Fan engagement and legitimacy take further hits."
            )

        elif action == "concede":
            # Full concessions — players return
            legit = random.uniform(cfg.rival_c_concession_legit_min,
                                   cfg.rival_c_concession_legit_max)
            events = self.restore_regular_rosters(concession_level=1.0)
            self._resolve_rival(season_num, resolution="concession")
            self._last_rival_c_resolved = season_num
            return 0.0, legit, (
                f"CBA concessions accepted. Players return to their teams. "
                f"Legitimacy cost: {legit:.0%}."
            )

        elif action == "partial":
            legit = cfg.rival_c_concession_legit_min
            events = self.restore_regular_rosters(concession_level=0.5)
            self._resolve_rival(season_num, resolution="partial_deal")
            self._last_rival_c_resolved = season_num
            return 0.0, legit, (
                "Partial deal reached. Players return. Some grievances remain unresolved."
            )

        return 0.0, 0.0, "Unknown action."

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
        original_franchise = franchise   # keep reference for reserve_pool removal
        # Entering this city also clears any lingering grudge
        if franchise.city in self.market_grudges:
            del self.market_grudges[franchise.city]
            del self._grudge_metro[franchise.city]
        if franchise.nickname_options:
            franchise = dataclasses.replace(franchise, nickname=random.choice(franchise.nickname_options), nickname_options=[])
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
        self.reserve_pool.remove(original_franchise)
        self._generate_founding_players(new_team)
        new_team.owner = generate_owner(small_market=new_team.franchise.effective_metro < 3.0)
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
            self.distribute_revenue()
            self.update_all_owner_happiness(season)
            self._update_losing_streaks(season)
            self._check_relocations(season)   # headless sim still uses auto-relocation
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
