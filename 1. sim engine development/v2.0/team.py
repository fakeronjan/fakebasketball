from franchises import Franchise


class Team:
    def __init__(self, team_id: int, quality: float, franchise: Franchise, identity: float = 0.5):
        self.team_id = team_id
        self.quality = quality
        self.identity = identity          # 0 = pure defense, 1 = pure offense
        self._identity_stability = 0.0   # 0 = fluid, 1 = entrenched
        self.championships = 0

        self.franchise = franchise
        self.franchise_history: list[tuple[int, Franchise]] = [(1, franchise)]

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
        return old

    def __repr__(self) -> str:
        return self.name
