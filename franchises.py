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
    nickname_options: list = field(default_factory=list)  # 5 market-appropriate name choices

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


# All franchises — the league starts with the initial_teams highest effective_metro
# primaries and expands from there. Secondary franchises (secondary=True) may only
# enter a city that already has exactly one team.
ALL_FRANCHISES: list[Franchise] = [
    # ── Primary franchises, US markets ───────────────────────────────────────
    #                                                         market  sec    lat      lon     climate  entertain  mktbl
    Franchise("New York",      "Empires",      21.0,  1.0, False,  40.71, -74.01,  0.88,    1.30,    1.30,
              nickname_options=["Empires", "Boroughs", "Metropolitans", "Bridges", "Gotham"]),
    Franchise("Los Angeles",   "Palms",        12.7,  1.0, False,  34.05,-118.24,  1.25,    1.25,    1.25,
              nickname_options=["Palms", "Stars", "Condors", "Sunsets", "Wildcats"]),
    Franchise("Chicago",       "Wind",          9.4,  1.0, False,  41.88, -87.63,  0.80,    1.20,    1.20,
              nickname_options=["Wind", "Towers", "Gales", "Foxes", "Tempest"]),
    Franchise("Dallas",        "Smoke",         8.3,  1.0, False,  32.78, -96.80,  1.10,    1.10,    1.15,
              nickname_options=["Smoke", "Stampede", "Roughnecks", "Longhorns", "Mustangs"]),
    Franchise("Houston",       "Comets",        7.8,  1.0, False,  29.76, -95.37,  1.08,    1.10,    1.15,
              nickname_options=["Comets", "Apollos", "Oilers", "Explorers", "Texans"]),
    Franchise("Miami",         "Flamingos",     6.5,  1.0, False,  25.77, -80.20,  1.30,    1.25,    1.15,
              nickname_options=["Flamingos", "Barracudas", "Heatwave", "Riptide", "Caimans"]),
    Franchise("Atlanta",       "Peaches",       6.4,  1.0, False,  33.75, -84.39,  1.05,    1.15,    1.10,
              nickname_options=["Peaches", "Firebirds", "Phoenixes", "Magnolias", "Hotshots"]),
    Franchise("Washington",    "Monuments",     6.2,  1.0, False,  38.90, -77.04,  0.90,    1.10,    1.10,
              nickname_options=["Monuments", "Capital", "Diplomats", "Freedom", "Sentries"]),
    Franchise("Philadelphia",  "Fighters",      5.9,  1.0, False,  39.95, -75.17,  0.88,    1.10,    1.10,
              nickname_options=["Fighters", "Ironmen", "Continentals", "Founders", "Quakers"]),
    Franchise("Phoenix",       "Scorpions",     5.2,  1.0, False,  33.45,-112.07,  1.15,    1.00,    1.05,
              nickname_options=["Scorpions", "Coyotes", "Roadrunners", "Desert Storm", "Sandstorm"]),
    Franchise("Boston",        "Common",        5.0,  1.0, False,  42.36, -71.06,  0.85,    1.10,    1.10,
              nickname_options=["Common", "Shamrocks", "Minutemen", "Lobsters", "Pilgrims"]),
    Franchise("Detroit",       "Motors",        4.8,  1.0, False,  42.33, -83.05,  0.75,    0.88,    0.95,
              nickname_options=["Motors", "Engines", "Torque", "Mechanics", "Gears"]),
    Franchise("San Francisco", "Fog",           4.7,  1.0, False,  37.77,-122.42,  1.10,    1.25,    1.25,
              nickname_options=["Fog", "Seals", "Bay", "Ridgeline", "Redwoods"]),
    Franchise("Riverside",     "Empire",        4.6,  1.0, False,  33.97,-117.40,  1.20,    0.85,    0.95,
              nickname_options=["Empire", "Sundowners", "Highlanders", "Cruisers", "Ranchers"]),
    Franchise("Seattle",       "Emeralds",      4.1,  1.0, False,  47.61,-122.33,  0.80,    1.10,    1.05,
              nickname_options=["Emeralds", "Rainiers", "Cascades", "Evergreens", "Totems"]),
    Franchise("Minneapolis",   "Freeze",        3.6,  1.0, False,  44.98, -93.27,  0.70,    0.90,    1.00,
              nickname_options=["Freeze", "Blizzard", "Lakers", "North Stars", "Lumberjacks"]),
    Franchise("San Diego",     "Surf",          3.3,  1.0, False,  32.72,-117.16,  1.30,    1.00,    1.00,
              nickname_options=["Surf", "Gulls", "Tides", "Waves", "Conquistadors"]),
    Franchise("Tampa",         "Tropics",       3.2,  1.0, False,  27.95, -82.46,  1.22,    0.95,    1.00,
              nickname_options=["Tropics", "Sundogs", "Fireflies", "Stingrays", "Herons"]),
    Franchise("Denver",        "Blizzards",     3.1,  1.0, False,  39.74,-104.98,  0.85,    1.05,    1.00,
              nickname_options=["Blizzards", "Peaks", "Altitude", "Yeti", "Wolverines"]),
    Franchise("Orlando",       "Springs",       3.0,  1.0, False,  28.54, -81.38,  1.22,    0.90,    1.00,
              nickname_options=["Springs", "Sunshine", "Sorcerers", "Solar", "Phantoms"]),
    Franchise("Baltimore",     "Harbor",        2.9,  1.0, False,  39.29, -76.61,  0.88,    0.90,    0.95,
              nickname_options=["Harbor", "Crabs", "Chesapeakes", "Skipjacks", "Terrapins"]),
    Franchise("St. Louis",     "Arch",          2.8,  1.0, False,  38.63, -90.20,  0.88,    0.90,    0.90,
              nickname_options=["Arch", "Fleur", "Redbirds", "Gateway", "Spirits"]),
    Franchise("Charlotte",     "Crown",         2.7,  1.0, False,  35.23, -80.84,  1.05,    0.95,    1.00,
              nickname_options=["Crown", "Nighthawks", "Rattlesnakes", "Speed", "Cougars"]),
    Franchise("Oakland",       "Oaks",          2.7,  1.0, False,  37.80,-122.27,  1.08,    1.10,    1.05,
              nickname_options=["Oaks", "Gold", "Prowlers", "Miners", "Redwood"]),
    Franchise("San Antonio",   "Legends",       2.6,  1.0, False,  29.42, -98.49,  1.10,    0.95,    0.95,
              nickname_options=["Legends", "Missions", "Alamo", "Chaparrals", "Vaqueros"]),
    Franchise("Portland",      "Bridges",       2.5,  1.0, False,  45.52,-122.68,  0.82,    1.05,    0.95,
              nickname_options=["Loggers", "Stormers", "Firs", "Rosebuds", "Thorns"]),
    Franchise("Sacramento",    "Rush",          2.4,  1.0, False,  38.58,-121.49,  1.05,    0.85,    0.95,
              nickname_options=["Rush", "Gold Rush", "Prospectors", "Rivercats", "Valley Kings"]),
    Franchise("Pittsburgh",    "Forge",         2.4,  1.0, False,  40.44, -79.99,  0.85,    0.90,    0.95,
              nickname_options=["Forge", "Steel", "Hammers", "Smokestacks", "Foundry"]),
    Franchise("Las Vegas",     "Dealers",       2.4,  1.0, False,  36.17,-115.14,  1.10,    1.30,    1.05,
              nickname_options=["Dealers", "Neons", "Showstoppers", "High Rollers", "Gamblers"]),
    Franchise("Austin",        "Outlaws",       2.3,  1.0, False,  30.27, -97.74,  1.15,    1.15,    1.00,
              nickname_options=["Outlaws", "Bats", "Bluebonnets", "Armadillos", "Rodeo"]),
    Franchise("Cincinnati",    "Bends",         2.3,  1.0, False,  39.10, -84.51,  0.88,    0.88,    0.88,
              nickname_options=["Bends", "Rivers", "Porkopolis", "Boatmen", "Mudcats"]),
    Franchise("Kansas City",   "Plains",        2.2,  1.0, False,  39.10, -94.58,  0.88,    0.90,    0.90,
              nickname_options=["Plains", "Monarchs", "Cowhands", "Scouts", "Cutters"]),
    Franchise("Cleveland",     "Shores",        2.1,  1.0, False,  41.50, -81.69,  0.72,    0.85,    0.88,
              nickname_options=["Shores", "Lakemen", "Boulders", "Spiders", "Crushers"]),
    Franchise("Indianapolis",  "Racers",        2.1,  1.0, False,  39.77, -86.16,  0.85,    0.85,    0.90,
              nickname_options=["Racers", "Cannonballs", "Hoosiers", "Speedway", "Fuel"]),
    Franchise("Nashville",     "Sound",         2.1,  1.0, False,  36.16, -86.78,  1.00,    1.20,    0.95,
              nickname_options=["Sound", "Beats", "Strings", "Riverboats", "Showboats"]),
    Franchise("Columbus",      "Pioneers",      2.0,  1.0, False,  39.96, -82.99,  0.85,    0.85,    0.88,
              nickname_options=["Pioneers", "Frontier", "Arrows", "Navigators", "Discoverers"]),
    Franchise("San Jose",      "Silicon",       2.0,  1.0, False,  37.34,-121.89,  1.12,    1.00,    1.15,
              nickname_options=["Silicon", "Sharks", "Circuits", "Steelheads", "Voltage"]),
    Franchise("Virginia Beach","Waves",         1.8,  1.0, False,  36.85, -75.98,  1.05,    0.88,    0.90,
              nickname_options=["Breakers", "Surge", "Navy", "Beachcombers", "Admirals"]),
    Franchise("Milwaukee",     "Frost",         1.6,  1.0, False,  43.04, -87.91,  0.68,    0.88,    0.88,
              nickname_options=["Frost", "Cream City", "Badgers", "Millers", "Stags"]),
    Franchise("Jacksonville",  "Tides",         1.6,  1.0, False,  30.33, -81.66,  1.15,    0.82,    0.88,
              nickname_options=["Salty Dogs", "Coasters", "Pelicans", "Manatees", "Stingers"]),
    Franchise("Raleigh",       "Pinecones",     1.5,  1.0, False,  35.78, -78.64,  1.00,    0.85,    0.90,
              nickname_options=["Pinecones", "Talons", "Venom", "Strikers", "Cobras"]),
    Franchise("Providence",    "Whalers",       1.5,  1.0, False,  41.82, -71.42,  0.82,    0.95,    0.88,
              nickname_options=["Whalers", "Friars", "Ironworkers", "Anchors", "Corsairs"]),
    Franchise("Oklahoma City", "Bison",         1.4,  1.0, False,  35.47, -97.52,  0.88,    0.80,    0.85,
              nickname_options=["Bison", "Prairie", "Plainsmen", "Cyclones", "Drillers"]),
    Franchise("Louisville",    "Thoroughbreds", 1.4,  1.0, False,  38.25, -85.76,  0.88,    0.95,    0.88,
              nickname_options=["Thoroughbreds", "Sluggers", "Bourbon", "Colonels", "Steamboats"]),
    Franchise("Memphis",       "Bluesmen",      1.3,  1.0, False,  35.15, -90.05,  0.95,    0.95,    0.85,
              nickname_options=["Bluesmen", "Delta", "Hound Dogs", "Pharaohs", "Hustle"]),
    Franchise("Salt Lake City","Peaks",         1.3,  1.0, False,  40.76,-111.89,  0.85,    0.80,    0.88,
              nickname_options=["Powder", "Snow", "Settlers", "Elders", "Wasatch"]),
    Franchise("New Orleans",   "Voodoo",        1.3,  1.0, False,  29.95, -90.07,  1.10,    1.25,    0.88,
              nickname_options=["Voodoo", "Creoles", "Bayou", "Zephyrs", "Brass"]),
    Franchise("Richmond",      "Colonials",     1.3,  1.0, False,  37.54, -77.44,  0.90,    0.88,    0.88,
              nickname_options=["Colonials", "Rebels", "Ironclads", "Statesmen", "Cannons"]),
    Franchise("Buffalo",       "Drifts",        1.2,  1.0, False,  42.89, -78.85,  0.65,    0.80,    0.82,
              nickname_options=["Drifts", "Snowbelt", "Niagara", "Bisons", "Lightning"]),
    # ── International markets ─────────────────────────────────────────────────
    Franchise("Toronto",       "Ice",           7.1,  0.4, False,  43.65, -79.38,  0.80,    1.10,    0.90,
              nickname_options=["Ice", "Maples", "Voyageurs", "Northmen", "Huskies"]),
    Franchise("Montreal",      "Rouge",         4.6,  0.3, False,  45.50, -73.57,  0.75,    1.15,    0.75,
              nickname_options=["Rouge", "Nordiques", "Canadiens", "Expos", "Alouettes"]),
    Franchise("Vancouver",     "Gales",         3.1,  0.3, False,  49.25,-123.12,  0.80,    1.05,    0.80,
              nickname_options=["Rainforest", "Grizzlies", "Orcas", "Salmon", "Bolts"]),
    Franchise("Mexico City",   "Aztecs",       22.8,  0.1, False,  19.43, -99.13,  0.95,    1.20,    0.70,
              nickname_options=["Aztecs", "Jaguares", "Dragons", "Aguilas", "Reales"]),
    Franchise("Guadalajara",   "Sol",           5.3,  0.1, False,  20.66,-103.35,  1.00,    1.00,    0.60,
              nickname_options=["Sol", "Chivas", "Tapatios", "Rayos", "Leones"]),
    Franchise("Monterrey",     "Summit",        5.3,  0.1, False,  25.67,-100.31,  0.95,    0.95,    0.60,
              nickname_options=["Summit", "Sultanes", "Norte", "Cañones", "Rayados"]),
    # ── Secondary franchises (second-team slots in large markets) ─────────────
    Franchise("New York",      "Knights",      21.0,  1.0, True,   40.71, -74.01,  0.88,    1.30,    1.30,
              nickname_options=["Knights", "Shadows", "Vigilantes", "Renegades", "Wanderers"]),
    Franchise("Los Angeles",   "Hollywood",    12.7,  1.0, True,   34.05,-118.24,  1.25,    1.25,    1.25,
              nickname_options=["Hollywood", "Dreamers", "Sunset", "Fury", "Lights"]),
    Franchise("Chicago",       "Blaze",         9.4,  1.0, True,   41.88, -87.63,  0.80,    1.20,    1.20,
              nickname_options=["Blaze", "Inferno", "Sting", "Storm", "Hounds"]),
    Franchise("Dallas",        "Rattlers",      8.3,  1.0, True,   32.78, -96.80,  1.10,    1.10,    1.15,
              nickname_options=["Rattlers", "Wranglers", "Desperados", "Sidekicks", "Burn"]),
    Franchise("Houston",       "Express",       7.8,  1.0, True,   29.76, -95.37,  1.08,    1.10,    1.15,
              nickname_options=["Express", "Skyhawks", "Enforcers", "Hustlers", "Tornadoes"]),
    Franchise("Miami",         "Surge",         6.5,  1.0, True,   25.77, -80.20,  1.30,    1.25,    1.15,
              nickname_options=["Breeze", "Wave", "Tarpons", "Marlins", "Swordfish"]),
    Franchise("Atlanta",       "Crimson",       6.4,  1.0, True,   33.75, -84.39,  1.05,    1.15,    1.10,
              nickname_options=["Crimson", "Embers", "Thrashers", "Flame", "Pacesetters"]),
    Franchise("Washington",    "Sentinels",     6.2,  1.0, True,   38.90, -77.04,  0.90,    1.10,    1.10,
              nickname_options=["Sentinels", "Red", "Justice", "Valor", "Envoys"]),
]
