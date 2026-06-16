from dataclasses import dataclass, field


@dataclass
class Franchise:
    city: str
    nickname: str
    metro: float          # raw population in millions (approximate)
    market_factor: float = 1.0   # discount for non-US markets
    secondary: bool = False      # True = second-team slot in a shared market

    @property
    def name(self) -> str:
        return f"{self.city} {self.nickname}"

    @property
    def effective_metro(self) -> float:
        """Market-adjusted population used for bias and popularity calculations."""
        return self.metro * self.market_factor


# All 50 franchises — the league starts with the initial_teams highest effective_metro
# primaries and expands from there. Secondary franchises (secondary=True) may only
# enter a city that already has exactly one team.
ALL_FRANCHISES: list[Franchise] = [
    # ── Primary franchises, US markets ───────────────────────────────────────
    Franchise("New York",      "Empires",      21.0),
    Franchise("Los Angeles",   "Palms",        12.7),
    Franchise("Chicago",       "Blues",         9.4),
    Franchise("Dallas",        "Smoke",         8.3),
    Franchise("Houston",       "Oilers",        7.8),
    Franchise("Miami",         "Flamingos",     6.5),
    Franchise("Atlanta",       "Peaches",       6.4),
    Franchise("Washington",    "Monuments",     6.2),
    Franchise("Philadelphia",  "Fighters",      5.9),
    Franchise("Phoenix",       "Scorpions",     5.2),
    Franchise("Boston",        "Common",        5.0),
    Franchise("Detroit",       "Motors",        4.8),
    Franchise("Seattle",       "Emeralds",      4.1),
    Franchise("Minneapolis",   "Freeze",        3.6),
    Franchise("San Diego",     "Surf",          3.3),
    Franchise("Tampa",         "Storm",         3.2),
    Franchise("Denver",        "Blizzards",     3.1),
    Franchise("Orlando",       "Springs",       3.0),
    Franchise("Baltimore",     "Harbor",        2.9),
    Franchise("St. Louis",     "Arch",          2.8),
    Franchise("Charlotte",     "Crown",         2.7),
    Franchise("San Antonio",   "Legends",       2.6),
    Franchise("Portland",      "Bridges",       2.5),
    Franchise("Sacramento",    "Rush",          2.4),
    Franchise("Pittsburgh",    "Forge",         2.4),
    Franchise("Las Vegas",     "Dealers",       2.4),
    Franchise("Austin",        "Outlaws",       2.3),
    Franchise("Kansas City",   "Plains",        2.2),
    Franchise("Indianapolis",  "Racers",        2.1),
    Franchise("Nashville",     "Sound",         2.1),
    Franchise("Columbus",      "Pioneers",      2.0),
    Franchise("Raleigh",       "Wings",         1.5),
    Franchise("Oklahoma City", "Bison",         1.4),
    Franchise("Memphis",       "Kings",         1.3),
    Franchise("Salt Lake City","Peaks",         1.3),
    Franchise("New Orleans",   "Voodoo",        1.3),
    # ── International markets ─────────────────────────────────────────────────
    Franchise("Toronto",       "Ice",           7.1,  0.4),
    Franchise("Montreal",      "Royals",        4.6,  0.3),
    Franchise("Vancouver",     "Gales",         3.1,  0.3),
    Franchise("Mexico City",   "Jaguars",      22.8,  0.1),
    Franchise("Guadalajara",   "Sol",           5.3,  0.1),
    Franchise("Monterrey",     "Summit",        5.3,  0.1),
    # ── Secondary franchises (second-team slots in large markets) ─────────────
    Franchise("New York",      "Knights",      21.0,  1.0, secondary=True),
    Franchise("Los Angeles",   "Angels",       12.7,  1.0, secondary=True),
    Franchise("Chicago",       "Blaze",         9.4,  1.0, secondary=True),
    Franchise("Dallas",        "Rattlers",      8.3,  1.0, secondary=True),
    Franchise("Houston",       "Express",       7.8,  1.0, secondary=True),
    Franchise("Miami",         "Surge",         6.5,  1.0, secondary=True),
    Franchise("Atlanta",       "Crimson",       6.4,  1.0, secondary=True),
    Franchise("Washington",    "Sentinels",     6.2,  1.0, secondary=True),
]
