from franchises import Franchise


class Team:
    def __init__(self, team_id: int, quality: float, franchise: Franchise,
                 identity: float = 0.5, popularity: float = 0.5,
                 joined_season: int = 1):
        self.team_id = team_id
        self.quality = quality
        self.identity = identity          # 0 = pure defense, 1 = pure offense
        self._identity_stability = 0.0   # 0 = fluid, 1 = entrenched
        self.championships = 0
        self.popularity = popularity      # 0 = obscure, 1 = universally beloved
        self.legacy: float = 0.0         # accumulated championship legacy; raises pop floor
        self._consecutive_playoff_misses: int = 0
        self.joined_season = joined_season  # first season this team played

        self.franchise = franchise
        self.franchise_history: list[tuple[int, Franchise]] = [(joined_season, franchise)]

        # Market engagement: how much the local city cares about basketball generally.
        # Starts uniform across all markets; diverges through performance over time.
        self.market_engagement: float = 0.03

        # Relocation eligibility tracking
        self._consecutive_losing_seasons: int = 0
        self._bottom2_in_streak: int = 0
        self._protected_until: int = 0  # cannot relocate while season.number < this

    @property
    def name(self) -> str:
        return self.franchise.name

    @property
    def nickname(self) -> str:
        return self.franchise.nickname

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
        # Reset eligibility — must earn relocation again in the new city
        self._consecutive_losing_seasons = 0
        self._bottom2_in_streak = 0
        # New city, new identity — organizational culture resets
        import random
        self.identity = random.random()
        self._identity_stability = 0.0
        # Popularity takes a haircut — some fans don't follow the move
        self.popularity *= 0.6
        # Legacy partially survives — history travels with the franchise
        self.legacy *= 0.75
        # Market engagement resets to a fresh-market baseline
        self.market_engagement = 0.03
        return old

    def __repr__(self) -> str:
        return self.name
