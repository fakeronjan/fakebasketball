from dataclasses import dataclass


@dataclass
class Franchise:
    city: str
    nickname: str
    metro: float          # raw population in millions (approximate)
    market_factor: float = 1.0  # discount for non-US markets (Canada=0.6, Mexico=0.3)

    @property
    def name(self) -> str:
        return f"{self.city} {self.nickname}"

    @property
    def effective_metro(self) -> float:
        """Market-adjusted population used for bias and relocation calculations."""
        return self.metro * self.market_factor


# The 20 active franchises — assigned randomly to teams at league start
ACTIVE_FRANCHISES: list[Franchise] = [
    Franchise("New York",     "Empires",   21.0),
    Franchise("Los Angeles",  "Palms",     12.7),
    Franchise("Chicago",      "Blues",      9.4),
    Franchise("Houston",      "Oilers",     7.8),
    Franchise("Dallas",       "Smoke",      8.3),
    Franchise("Toronto",      "Ice",        7.1,  0.4),
    Franchise("Washington",   "Monuments",  6.2),
    Franchise("Miami",        "Flamingos",  6.5),
    Franchise("Atlanta",      "Peaches",    6.4),
    Franchise("Philadelphia", "Fighters",   5.9),
    Franchise("Phoenix",      "Scorpions",  5.2),
    Franchise("Boston",       "Common",     5.0),
    Franchise("Detroit",      "Motors",     4.8),
    Franchise("Montreal",     "Royals",     4.6,  0.3),
    Franchise("Seattle",      "Emeralds",   4.1),
    Franchise("Denver",       "Blizzards",  3.1),
    Franchise("Vancouver",    "Gales",      3.1,  0.3),
    Franchise("Mexico City",  "Jaguars",   22.8, 0.1),
    Franchise("Las Vegas",    "Dealers",    2.4),
    Franchise("New Orleans",  "Voodoo",     1.3),
]

# Reserve pool — available relocation destinations, ordered roughly by metro size
RESERVE_FRANCHISES: list[Franchise] = [
    Franchise("Guadalajara",   "Sol",       5.3,  0.1),
    Franchise("Monterrey",     "Summit",    5.3,  0.1),
    Franchise("Minneapolis",   "Freeze",    3.6),
    Franchise("San Diego",     "Surf",      3.3),
    Franchise("Tampa",         "Storm",     3.2),
    Franchise("Orlando",       "Springs",   3.0),
    Franchise("Baltimore",     "Harbor",    2.9),
    Franchise("St. Louis",     "Arch",      2.8),
    Franchise("Charlotte",     "Crown",     2.7),
    Franchise("San Antonio",   "Legends",   2.6),
    Franchise("Portland",      "Bridges",   2.5),
    Franchise("Sacramento",    "Rush",      2.4),
    Franchise("Pittsburgh",    "Forge",     2.4),
    Franchise("Austin",        "Outlaws",   2.3),
    Franchise("Kansas City",   "Plains",    2.2),
    Franchise("Indianapolis",  "Racers",    2.1),
    Franchise("Nashville",     "Sound",     2.1),
    Franchise("Salt Lake City","Peaks",     1.3),
]
