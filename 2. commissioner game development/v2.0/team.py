from franchises import Franchise


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

    def __repr__(self) -> str:
        return self.name
