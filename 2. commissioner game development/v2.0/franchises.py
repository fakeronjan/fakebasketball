from dataclasses import dataclass, field


@dataclass
class Franchise:
    city: str
    nickname: str
    metro: float          # raw population in millions (approximate)
    market_factor: float = 1.0   # discount for non-US markets
    secondary: bool = False      # True = second-team slot in a shared market
    lat: float = 0.0             # latitude (degrees N)
    lon: float = 0.0             # longitude (degrees E, negative = W)
    # TODO: tune these per-franchise once player model is in place
    climate_draw: float = 1.0    # player preference for weather/lifestyle (e.g. Miami > Detroit)
    entertainment_draw: float = 1.0  # nightlife/culture pull beyond raw market size
    marketability: float = 1.0   # GDP/sponsorship ceiling (currently all domestic = 1.0)

    @property
    def name(self) -> str:
        return f"{self.city} {self.nickname}"

    @property
    def effective_metro(self) -> float:
        """Market-adjusted population used for bias and popularity calculations."""
        return self.metro * self.market_factor

    @property
    def draw_factor(self) -> float:
        """Composite player/sponsor draw. Placeholder — all 1.0 until player model."""
        return self.climate_draw * self.entertainment_draw * self.marketability


# All 50 franchises — the league starts with the initial_teams highest effective_metro
# primaries and expands from there. Secondary franchises (secondary=True) may only
# enter a city that already has exactly one team.
ALL_FRANCHISES: list[Franchise] = [
    # ── Primary franchises, US markets ───────────────────────────────────────
    #                                                         market  sec    lat      lon
    Franchise("New York",      "Empires",      21.0,  1.0, False,  40.71, -74.01),
    Franchise("Los Angeles",   "Palms",        12.7,  1.0, False,  34.05,-118.24),
    Franchise("Chicago",       "Blues",         9.4,  1.0, False,  41.88, -87.63),
    Franchise("Dallas",        "Smoke",         8.3,  1.0, False,  32.78, -96.80),
    Franchise("Houston",       "Oilers",        7.8,  1.0, False,  29.76, -95.37),
    Franchise("Miami",         "Flamingos",     6.5,  1.0, False,  25.77, -80.20),
    Franchise("Atlanta",       "Peaches",       6.4,  1.0, False,  33.75, -84.39),
    Franchise("Washington",    "Monuments",     6.2,  1.0, False,  38.90, -77.04),
    Franchise("Philadelphia",  "Fighters",      5.9,  1.0, False,  39.95, -75.17),
    Franchise("Phoenix",       "Scorpions",     5.2,  1.0, False,  33.45,-112.07),
    Franchise("Boston",        "Common",        5.0,  1.0, False,  42.36, -71.06),
    Franchise("Detroit",       "Motors",        4.8,  1.0, False,  42.33, -83.05),
    Franchise("Seattle",       "Emeralds",      4.1,  1.0, False,  47.61,-122.33),
    Franchise("Minneapolis",   "Freeze",        3.6,  1.0, False,  44.98, -93.27),
    Franchise("San Diego",     "Surf",          3.3,  1.0, False,  32.72,-117.16),
    Franchise("Tampa",         "Storm",         3.2,  1.0, False,  27.95, -82.46),
    Franchise("Denver",        "Blizzards",     3.1,  1.0, False,  39.74,-104.98),
    Franchise("Orlando",       "Springs",       3.0,  1.0, False,  28.54, -81.38),
    Franchise("Baltimore",     "Harbor",        2.9,  1.0, False,  39.29, -76.61),
    Franchise("St. Louis",     "Arch",          2.8,  1.0, False,  38.63, -90.20),
    Franchise("Charlotte",     "Crown",         2.7,  1.0, False,  35.23, -80.84),
    Franchise("San Antonio",   "Legends",       2.6,  1.0, False,  29.42, -98.49),
    Franchise("Portland",      "Bridges",       2.5,  1.0, False,  45.52,-122.68),
    Franchise("Sacramento",    "Rush",          2.4,  1.0, False,  38.58,-121.49),
    Franchise("Pittsburgh",    "Forge",         2.4,  1.0, False,  40.44, -79.99),
    Franchise("Las Vegas",     "Dealers",       2.4,  1.0, False,  36.17,-115.14),
    Franchise("Austin",        "Outlaws",       2.3,  1.0, False,  30.27, -97.74),
    Franchise("Kansas City",   "Plains",        2.2,  1.0, False,  39.10, -94.58),
    Franchise("Indianapolis",  "Racers",        2.1,  1.0, False,  39.77, -86.16),
    Franchise("Nashville",     "Sound",         2.1,  1.0, False,  36.16, -86.78),
    Franchise("Columbus",      "Pioneers",      2.0,  1.0, False,  39.96, -82.99),
    Franchise("Raleigh",       "Wings",         1.5,  1.0, False,  35.78, -78.64),
    Franchise("Oklahoma City", "Bison",         1.4,  1.0, False,  35.47, -97.52),
    Franchise("Memphis",       "Kings",         1.3,  1.0, False,  35.15, -90.05),
    Franchise("Salt Lake City","Peaks",         1.3,  1.0, False,  40.76,-111.89),
    Franchise("New Orleans",   "Voodoo",        1.3,  1.0, False,  29.95, -90.07),
    # ── International markets ─────────────────────────────────────────────────
    Franchise("Toronto",       "Ice",           7.1,  0.4, False,  43.65, -79.38),
    Franchise("Montreal",      "Royals",        4.6,  0.3, False,  45.50, -73.57),
    Franchise("Vancouver",     "Gales",         3.1,  0.3, False,  49.25,-123.12),
    Franchise("Mexico City",   "Jaguars",      22.8,  0.1, False,  19.43, -99.13),
    Franchise("Guadalajara",   "Sol",           5.3,  0.1, False,  20.66,-103.35),
    Franchise("Monterrey",     "Summit",        5.3,  0.1, False,  25.67,-100.31),
    # ── Secondary franchises (second-team slots in large markets) ─────────────
    Franchise("New York",      "Knights",      21.0,  1.0, True,   40.71, -74.01),
    Franchise("Los Angeles",   "Angels",       12.7,  1.0, True,   34.05,-118.24),
    Franchise("Chicago",       "Blaze",         9.4,  1.0, True,   41.88, -87.63),
    Franchise("Dallas",        "Rattlers",      8.3,  1.0, True,   32.78, -96.80),
    Franchise("Houston",       "Express",       7.8,  1.0, True,   29.76, -95.37),
    Franchise("Miami",         "Surge",         6.5,  1.0, True,   25.77, -80.20),
    Franchise("Atlanta",       "Crimson",       6.4,  1.0, True,   33.75, -84.39),
    Franchise("Washington",    "Sentinels",     6.2,  1.0, True,   38.90, -77.04),
]
