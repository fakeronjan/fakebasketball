from __future__ import annotations
from typing import TYPE_CHECKING

from franchises import Franchise

if TYPE_CHECKING:
    from coach import Coach
    from config import Config
    from owner import Owner
    from player import Player


class Team:
    def __init__(self, team_id: int, franchise: Franchise,
                 ortg: float = 110.0, drtg: float = 110.0, pace: float = 95.0,
                 style_ft: float = 0.10, style_paint: float = 0.45,
                 style_mid: float = 0.20, style_3pt: float = 0.25,
                 popularity: float = 0.5, joined_season: int = 1):
        self.team_id = team_id
        self.ortg = ortg           # offensive rating (pts per 100 possessions)
        self.drtg = drtg           # defensive rating (pts per 100 possessions allowed)
        self.pace = pace           # pace preference (possessions per team per game)
        # Shot style — sum to 1.0; all 2pt plays produce 2 pts, style_3pt produces 3
        self.style_ft = style_ft       # free-throw plays
        self.style_paint = style_paint # paint 2s
        self.style_mid = style_mid     # mid-range 2s
        self.style_3pt = style_3pt     # three-pointers
        self.championships = 0
        self.popularity = popularity
        self.legacy: float = 0.0
        self._consecutive_playoff_misses: int = 0
        self.joined_season = joined_season

        self.franchise = franchise
        self.franchise_history: list[tuple[int, Franchise]] = [(joined_season, franchise)]

        self.market_engagement: float = 0.11

        self._consecutive_losing_seasons: int = 0
        self._bottom2_in_streak: int = 0
        self._protected_until: int = 0
        self._rebrand_cooldown_until: int = 0   # season number after which rebrand is allowed again
        self._rebrand_season: int = 0           # season number of most recent rebrand (0 = never)

        # Owner
        self.owner: Owner | None = None

        # Coach
        self.coach: Coach | None = None

        # Player roster: [star, co-star, starter] — None = empty slot
        self.roster: list[Player | None] = [None, None, None]
        # Tracks seasons each player pair has been together: (id_lo, id_hi) → seasons
        self._pair_seasons: dict[tuple[int, int], int] = {}

    @property
    def name(self) -> str:
        return self.franchise.name

    @property
    def nickname(self) -> str:
        return self.franchise.nickname

    def net_rating(self) -> float:
        """ORtg minus DRtg — positive = net advantage."""
        return self.ortg - self.drtg

    def franchise_at(self, season_num: int) -> Franchise:
        """Return the franchise this team had during the given season."""
        active = self.franchise_history[0][1]
        for s_num, f in self.franchise_history:
            if s_num <= season_num:
                active = f
        return active

    def relocate(self, new_franchise: Franchise, next_season_num: int) -> Franchise:
        """Assign a new franchise. Returns the old one so it can go back to the pool."""
        old = self.franchise
        self.franchise = new_franchise
        self.franchise_history.append((next_season_num, new_franchise))
        self._consecutive_losing_seasons = 0
        self._bottom2_in_streak = 0
        # New city: randomize shot style — organizational culture resets
        import random
        raw = [random.random() for _ in range(4)]
        s = sum(raw)
        self.style_ft, self.style_paint, self.style_mid, self.style_3pt = [r / s for r in raw]
        self.popularity *= 0.6
        self.legacy *= 0.75
        self.market_engagement = 0.11
        return old

    def slot_label(self, idx: int) -> str:
        return ["Star", "Co-Star", "Starter"][idx]

    def compute_chemistry(self, cfg: Config) -> float:
        """Return a bonus-only chemistry multiplier in [chemistry_min, chemistry_max].

        Chemistry is purely additive — it can only help, never hurt. Bad roster
        construction (duplicate positions, redundant zones) means no bonus, not a penalty;
        the talent/rating hit from suboptimal construction is punishment enough.

        Three components:
          fit_bonus       — positional variety + zone diversity (static given roster)
          continuity_bonus — saturating curve on average pair-seasons together
          chemistry = 1.00 + fit_bonus + continuity_bonus, clamped to [min, max]
        """
        import math
        players = [p for p in self.roster if p is not None]
        n = len(players)
        if n == 0:
            return cfg.chemistry_min   # = 1.00; empty roster gets no bonus

        fit_bonus = 0.0

        if n >= 2:
            # Positional fit — bonus only when all filled slots have distinct positions
            positions = [p.position for p in players]
            if len(set(positions)) == n:
                fit_bonus += cfg.chemistry_positional_bonus

            # Zone diversity — bonus only when all filled slots prefer different zones
            zones = [p.preferred_zone for p in players]
            if len(set(zones)) == n:
                fit_bonus += cfg.chemistry_zone_bonus

            # Continuity — saturating curve: max × (1 − e^(−k × avg_pair_seasons))
            pairs, total_seasons = 0, 0
            for i in range(n):
                for j in range(i + 1, n):
                    key = (min(players[i].player_id, players[j].player_id),
                           max(players[i].player_id, players[j].player_id))
                    total_seasons += self._pair_seasons.get(key, 0)
                    pairs += 1
            avg_pair_seasons = total_seasons / pairs if pairs else 0.0
            continuity_bonus = cfg.chemistry_continuity_max * (
                1.0 - math.exp(-cfg.chemistry_continuity_k * avg_pair_seasons)
            )
        else:
            continuity_bonus = 0.0

        return max(cfg.chemistry_min, min(cfg.chemistry_max, 1.0 + fit_bonus + continuity_bonus))

    def update_pair_seasons(self) -> None:
        """Call each offseason to record another season of continuity for each pair."""
        players = [p for p in self.roster if p is not None]
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                key = (min(players[i].player_id, players[j].player_id),
                       max(players[i].player_id, players[j].player_id))
                self._pair_seasons[key] = self._pair_seasons.get(key, 0) + 1

    def compute_ratings_from_roster(self, cfg: Config) -> None:
        """Recompute ortg, drtg, pace, and style from the current player roster.

        Weights: Star 50%, Co-Star 30%, Starter 20%.
        Chemistry multiplies the rating deltas (not the baseline itself).
        Empty slots contribute league baseline / zero delta.
        """
        from player import zone_dist
        weights = (cfg.slot_weight_star, cfg.slot_weight_costar, cfg.slot_weight_starter)

        ortg_delta = drtg_delta = pace_delta = 0.0
        ft = paint = mid = three = 0.0

        for i, player in enumerate(self.roster):
            w = weights[i]
            if player is not None:
                hm = player.happiness_mult
                ortg_delta += w * player.ortg_contrib * hm
                drtg_delta += w * player.drtg_contrib * hm
                pace_delta  += w * player.pace_contrib
                zd = zone_dist(player.preferred_zone)
            else:
                zd = zone_dist(None)  # league avg for empty slot
            ft    += w * zd[0]
            paint += w * zd[1]
            mid   += w * zd[2]
            three += w * zd[3]

        # Coach modifiers — applied before clamping
        coach_mods: dict = {}
        if self.coach is not None:
            coach_mods = self.coach.compute_modifiers()

        chem_raw = self.compute_chemistry(cfg)
        if coach_mods:
            # Scale the chemistry bonus (not the baseline) by the coach's chem_scale
            chem_bonus = (chem_raw - 1.0) * coach_mods["chem_scale"]
            chem = 1.0 + chem_bonus
        else:
            chem = chem_raw

        raw_ortg = cfg.ortg_baseline + ortg_delta * chem + coach_mods.get("ortg_mod", 0.0)
        raw_drtg = cfg.drtg_baseline + drtg_delta * chem + coach_mods.get("drtg_mod", 0.0)

        self.ortg = max(cfg.ortg_min, min(cfg.ortg_max, raw_ortg))
        self.drtg = max(cfg.drtg_min, min(cfg.drtg_max, raw_drtg))
        self.pace = max(cfg.pace_min,  min(cfg.pace_max,
                        cfg.pace_baseline + pace_delta))

        # Renormalize zone style to sum to 1.0
        total = ft + paint + mid + three
        if total > 0:
            self.style_ft    = ft    / total
            self.style_paint = paint / total
            self.style_mid   = mid   / total
            self.style_3pt   = three / total

    def __repr__(self) -> str:
        return self.name
