from __future__ import annotations
from typing import TYPE_CHECKING

from franchises import Franchise

if TYPE_CHECKING:
    from config import Config
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

        self.market_engagement: float = 0.03

        self._consecutive_losing_seasons: int = 0
        self._bottom2_in_streak: int = 0
        self._protected_until: int = 0

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
        self.market_engagement = 0.03
        return old

    def slot_label(self, idx: int) -> str:
        return ["Star", "Co-Star", "Starter"][idx]

    def compute_chemistry(self, cfg: Config) -> float:
        """Return 0.80–1.10 chemistry multiplier based on fit and continuity."""
        from player import GUARD, WING, BIG  # local import avoids circular dep at module level
        players = [p for p in self.roster if p is not None]
        n = len(players)
        if n == 0:
            return cfg.chemistry_min

        chem = 1.0

        if n >= 2:
            # Positional fit
            positions = [p.position for p in players]
            if len(set(positions)) == n:
                chem += cfg.chemistry_positional_bonus
            elif len(set(positions)) < n:
                chem -= cfg.chemistry_positional_penalty

            # Zone diversity
            zones = [p.preferred_zone for p in players]
            if len(set(zones)) == n:
                chem += cfg.chemistry_zone_bonus
            elif len(set(zones)) == 1:
                chem -= cfg.chemistry_zone_penalty

            # Continuity bonus
            pairs, total_seasons = 0, 0
            for i in range(n):
                for j in range(i + 1, n):
                    key = (min(players[i].player_id, players[j].player_id),
                           max(players[i].player_id, players[j].player_id))
                    total_seasons += self._pair_seasons.get(key, 0)
                    pairs += 1
            if pairs:
                avg = total_seasons / pairs
                chem += min(3.0, avg) * cfg.chemistry_continuity_per_season

        return max(cfg.chemistry_min, min(cfg.chemistry_max, chem))

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

        chem = self.compute_chemistry(cfg)
        self.ortg = max(cfg.ortg_min, min(cfg.ortg_max,
                        cfg.ortg_baseline + ortg_delta * chem))
        self.drtg = max(cfg.drtg_min, min(cfg.drtg_max,
                        cfg.drtg_baseline + drtg_delta * chem))
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
