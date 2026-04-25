from __future__ import annotations
import random
from dataclasses import dataclass

# ── Position / zone / motivation constants ────────────────────────────────────

GUARD = "Guard"
WING  = "Wing"
BIG   = "Big"
POSITIONS = [GUARD, WING, BIG]

ZONE_FT    = "ft"
ZONE_PAINT = "paint"
ZONE_MID   = "mid"
ZONE_3PT   = "3pt"
ZONES = [ZONE_FT, ZONE_PAINT, ZONE_MID, ZONE_3PT]

MOT_WINNING = "winning"
MOT_MARKET  = "market"
MOT_LOYALTY = "loyalty"
MOTIVATIONS = [MOT_WINNING, MOT_MARKET, MOT_LOYALTY]

TIER_ELITE = "Elite"
TIER_HIGH  = "High"
TIER_MID   = "Mid"
TIER_LOW   = "Low"

# ── Happiness / popularity tiers ──────────────────────────────────────────────

def happiness_emoji(h: float) -> str:
    if h >= 0.75: return "😄"
    if h >= 0.50: return "🙂"
    if h >= 0.25: return "😤"
    return "😡"

def happiness_label(h: float) -> str:
    if h >= 0.75: return "Content"
    if h >= 0.50: return "Settled"
    if h >= 0.25: return "Restless"
    return "Miserable"

def popularity_tier(p: float) -> str:
    if p >= 0.85: return "Legend"
    if p >= 0.65: return "Fan Fave"
    if p >= 0.40: return "Known"
    if p >= 0.20: return "Obscure"
    return "Unknown"

def durability_label(d: float) -> str:
    if d >= 0.88: return "Iron"
    if d >= 0.75: return "Sturdy"
    if d >= 0.62: return "Average"
    return "Glass"

# ── Name generator ────────────────────────────────────────────────────────────

_FIRST_MALE = [
    # North American
    "Marcus", "Tyler", "Deon", "Jamison", "Kevin", "Andre", "Chris",
    "DeShawn", "Malik", "Anthony", "Brandon", "Trevor", "Isaiah", "Darius",
    "Corey", "Terrell", "Justin", "Aaron", "Derrick", "Lance", "Marvin",
    "Todd", "Keith", "Gary", "Eric", "DaQuan", "Tremaine", "Javon", "Kofi",
    "DeAndre", "Jarrett", "Draymond", "Jaylen", "Donovan", "Tyrese",
    "Tre", "Wendell", "Ochai", "Bennedict", "Keegan", "Nassir", "Naz",
    "Jalen", "Obi", "Hamidou", "Dyson", "Tari", "Precious", "Scottie",
    "Cade", "Zion", "Elijah", "Dante", "Miles", "Dominique", "Travis",
    "Davion", "Amen", "Scoot", "Ausar", "Jabari", "Jalen", "Keyonte",
    "Bilal", "Cam", "Jerami", "Kira", "Luguentz", "Mamadi", "Sekou",
    "Xavier", "Alonzo", "Rajon", "Chauncey", "Monta", "Amar'e", "Udonis",
    "Thaddeus", "Joakim", "Luol", "Serge", "Bismack", "Clint", "Gorgui",
    # European / International
    "Luka", "Aleksei", "Mateo", "Franz", "Moritz", "Goga", "Alperen",
    "Killian", "Leandro", "Bruno", "Shai", "Bol", "Deni", "Nikola",
    "Jusuf", "Bojan", "Bogdan", "Nemanja", "Vladimir", "Milos", "Vasilije",
    "Danilo", "Kristaps", "Rodions", "Lauri", "Svi", "Mateusz", "Domas",
    "Jonas", "Ivica", "Ante", "Mario", "Goran", "Ricky", "Rudy", "Evan",
    "Theis", "Maxi", "Isaiah", "Usman", "Nerlens", "Cheick", "Moussa",
    # Asian — East Asian, South Asian, Southeast Asian
    "Yuki", "Rui", "Kai", "Wei", "Jae", "Sung", "Jin", "Hiro",
    "Kei", "Takuma", "Daiki", "Yuta", "Satoshi", "Ren", "Kenji",
    "Jun", "Tao", "Zhen", "Mingyu", "Seung", "Doyeon", "Hyun",
    "Rohan", "Arjun", "Vikram", "Preet", "Kiran", "Raj", "Dev",
    "Thanh", "Minh", "Linh", "Khoa",
    # Latin American
    "Carlos", "Diego", "Juan", "Rafael", "Luis", "Alejandro", "Sergio",
    "Pablo", "Thiago", "Facundo", "Gonzalo", "Eduardo", "Ricardo",
    "Gabriel", "Braian", "Nicolás", "Cristian",
    # East / Horn of Africa
    "Dawit", "Tesfaye", "Yonas", "Belay", "Abdi", "Otieno", "Kamau",
    "Emeka", "Hakim", "Karim", "Ndidi",
]

_FIRST_FEMALE = [
    # North American
    "Breanna", "Diana", "Maya", "Candace", "Elena", "Brittney", "Nneka",
    "Jonquel", "Arike", "Napheesa", "Chiney", "Chelsea", "Kelsey", "Tina",
    "Tamika", "Chamique", "Lisa", "Cynthia", "Tasha", "Jasmine", "Alicia",
    "Monique", "Imani", "Simone", "Alexis", "Brianna", "Aaliyah", "Riquna",
    "Betnijah", "Teaira", "Destinee", "Layshia", "Essence", "Lexie",
    "Chennedy", "Dearica", "Aerial", "Crystal", "Kayla", "Kiara", "Tiara",
    "Sierra", "Amaya", "Nyla", "Kyla", "Liz", "Rhyne", "A'ja", "Azurá",
    "Sylvia", "Kylee", "Cierra", "Shakia", "Kia", "Reshanda", "Shakira",
    "Dominique", "Didi", "Tanisha", "LaToya", "Swin", "Seimone", "Cheyenne",
    "Odyssey", "Kalani", "Deja", "Alysha", "Lexie", "Allisha", "Aerial",
    "Michaela", "Natasha", "Stefanie", "Isabelle", "Marina", "Sandrine",
    "Sabrina", "Erica", "Tiffany", "Courtney", "Tierra", "Roneeka",
    "Kristi", "Jantel", "Nnemkadi", "Reshanda", "Marissa", "Danielle",
    "Destinee", "Alana", "Kalani", "Leilani", "Asjha", "Ivory", "Epiphanny",
    # International
    "Sika", "Astou", "Awak", "Éva", "Sandrine", "Cayla", "Endy",
    "Clarissa", "Gabby", "Marine", "Marième", "Sonja", "Jonquel",
    "Stephanie", "Kiah", "Colleen", "Jenna", "Laia", "Ezi", "Shakyla",
    # Asian — East Asian, South Asian, Southeast Asian
    "Yuna", "Miku", "Hana", "Sora", "Aoi", "Mei", "Rin", "Yui",
    "Jiyeon", "Sooyeon", "Hyuna", "Chaeyoung", "Jisoo", "Minji",
    "Lan", "Huong", "Tuyen", "Bao", "Linh", "Phuong",
    "Priya", "Ananya", "Divya", "Neha", "Pooja", "Riya", "Shreya",
    "Xiu", "Fang", "Yanmei", "Ying", "Zhen",
    # Latin American
    "Valentina", "Camila", "Gabriela", "Fernanda", "Mariana", "Juliana",
    "Daniela", "Leticia", "Bruna", "Carolina", "Tatiana", "Raquel",
    "Adriana", "Luciana", "Sofia",
    # East / Horn of Africa
    "Tigist", "Hiwot", "Selam", "Meron", "Adaeze", "Ngozi",
    "Wanjiru", "Achieng", "Ifunanya", "Amara",
]

_FIRST_SWING = [
    "Jordan", "Taylor", "Cameron", "Riley", "Devon", "Morgan", "Quinn",
    "Avery", "Peyton", "Skylar", "Kendall", "Reese", "Dana", "Jamie",
    "Harley", "Sidney", "Ryan", "Kyle", "Chris", "Pat",
    "Alex", "Drew", "Casey", "Sage", "Emery", "Lennon", "Remy", "Rowan",
    "Finley", "Parker", "Hayden", "Blake", "Shea", "Bryn", "Dylan", "Logan",
    "River", "Tatum", "Oakley", "Haven",
]

_LAST_REAL = [
    # Common American surnames
    "Johnson", "Williams", "Davis", "Thompson", "Anderson", "Jackson",
    "Harris", "Martin", "Thomas", "White", "Robinson", "Walker",
    "Mitchell", "Carter", "Morgan", "Collins", "Richardson", "Howard",
    "Taylor", "Moore", "Hall", "Allen", "Young", "Green", "Adams",
    "Baker", "Nelson", "Hill", "Wright", "Scott", "Washington",
    # Additional common American surnames
    "James", "Brown", "Jones", "Miller", "Wilson", "Evans", "Turner",
    "Parker", "Cook", "Cooper", "Reed", "Bell", "Murphy", "Price",
    "Foster", "Bryant", "Jordan", "Pierce", "Ross", "Holmes", "Webb",
    "Dixon", "Simmons", "Hayes", "Graham", "Woods", "Cole",
    "Spencer", "Sanders", "Ingram", "Leonard", "George", "Bridges",
    "Powell", "Coleman", "Payne", "Gilmore", "Booker", "Hardaway",
    # Asian surnames
    "Kim", "Park", "Lee", "Choi",
    "Tanaka", "Suzuki", "Sato", "Nakamura",
    "Wang", "Zhang", "Chen", "Lin",
    "Nguyen", "Tran", "Pham",
    "Sharma", "Singh", "Patel", "Rao",
    # Latin American surnames
    "Rodriguez", "Gonzalez", "Martinez", "Herrera", "Rivera", "Reyes",
    "Cruz", "Torres", "Ramos", "Delgado", "Mendoza", "Perez", "Flores",
    "Suarez", "Vargas", "Castillo", "Morales", "Vega",
    # African surnames
    "Okafor", "Diallo", "Mensah", "Okonkwo", "Kamara", "Traore",
    "Coulibaly", "Dembele", "Keita", "Adetokunbo",
]

_LAST_STEMS = [
    # Original stems
    "Bond", "Bon", "Tal", "Verd", "Stromb", "Kazl", "Volz",
    "Okon", "Mbay", "Thorn", "Stall", "Griff", "Crom", "Blunt",
    "Wynn", "Fletch", "Chid", "Bram", "Quint", "Treff", "Drex",
    "Snell", "Przyk", "Kond", "Bjelk", "Oluw", "Adey", "Diall",
    # African stems
    "Nwak", "Chuk", "Emek", "Osei", "Aban", "Koff", "Asant",
    # Slavic / Eastern European stems
    "Zubk", "Koval", "Havel", "Novak", "Petrov", "Ivanov", "Sorok",
    # Invented / generic stems
    "Var", "Dur", "Pelk", "Fend", "Grav", "Holt", "Krel", "Mord",
    "Strax", "Velk", "Brask", "Colm", "Rand", "Spen", "Torr", "Phelp",
    # Spanish / Latin American stems (combine with -ez, -ez, -irez, -zalez etc.)
    "Gonz", "Ram", "Rodr", "Fern", "Alv", "Gut", "Jim", "Lop",
    "Dom", "Garc", "Ort", "Cas", "Nav", "Agu", "Esp", "Mir",
]

_LAST_SUFFIXES = [
    # Original suffixes
    "zalez", "irez", "nguez", "tinez",
    "ski", "wicz", "beck", "berg",
    "son", "ston", "ford", "wood", "well",
    "ović", "ić",
    "ombe", "aylo", "ofor",
    "field", "ington", "worth", "ley",
    # New suffixes — broader phonetic range
    "man", "mond", "low", "shaw", "dale",
    "enko", "chuk", "enko", "vich", "itch",
    "ara", "ema", "olu", "ade", "ike",
    "ez", "oz", "az", "ux", "ax",
    "ton", "den", "ven", "ken", "ren",
    "ard", "ert", "olt", "ist", "ast",
]

_used_names: set[str] = set()


def _make_name() -> tuple[str, str]:
    """Return (full_name, gender). Gender is 50/50."""
    gender = random.choice(["female", "male"])
    for _ in range(30):
        r = random.random()
        if r < 0.80:
            first = random.choice(_FIRST_FEMALE if gender == "female" else _FIRST_MALE)
        else:
            first = random.choice(_FIRST_SWING)

        r2 = random.random()
        if r2 < 0.35:
            last = random.choice(_LAST_REAL)
        elif r2 < 0.80:
            last = random.choice(_LAST_STEMS) + random.choice(_LAST_SUFFIXES)
        else:
            last = (random.choice(_LAST_REAL) + "-"
                    + random.choice(_LAST_STEMS) + random.choice(_LAST_SUFFIXES))
        name = f"{first} {last}"
        if name not in _used_names:
            _used_names.add(name)
            return name, gender
    # Fallback
    name = f"{first} {last} II"
    _used_names.add(name)
    return name, gender


# ── Career arc math ───────────────────────────────────────────────────────────

def _career_mult(seasons_played: int, peak_season: int,
                 career_length: int, start_mult: float) -> float:
    """0.0–1.0 multiplier on peak rating for the given career position.

    Rise: linear from start_mult → 1.0 over seasons 0..peak_season.
    Decline: accelerating from 1.0 → ~0.50 over peak_season..career_length.
    """
    if seasons_played <= peak_season:
        if peak_season == 0:
            return 1.0
        t = seasons_played / peak_season
        return start_mult + t * (1.0 - start_mult)
    else:
        seasons_past = seasons_played - peak_season
        decline_len  = max(1, career_length - peak_season)
        t = min(1.0, seasons_past / decline_len)
        return max(0.45, 1.0 - (t ** 1.3) * 0.50)


# ── Zone style distributions ──────────────────────────────────────────────────
# Each zone preference maps to a (ft, paint, mid, 3pt) distribution used when
# computing team style from player rosters.

_ZONE_DISTS: dict[str, tuple] = {
    ZONE_FT:    (0.25, 0.35, 0.25, 0.15),  # was (0.50,...) — 50% FT rate was unrealistically high
    ZONE_PAINT: (0.10, 0.55, 0.20, 0.15),
    ZONE_MID:   (0.08, 0.20, 0.52, 0.20),
    ZONE_3PT:   (0.05, 0.10, 0.20, 0.65),
}
_ZONE_DEFAULT = (0.10, 0.45, 0.20, 0.25)  # league avg, used for empty slots


def zone_dist(zone: str | None) -> tuple:
    return _ZONE_DISTS.get(zone, _ZONE_DEFAULT) if zone else _ZONE_DEFAULT


# ── Player ────────────────────────────────────────────────────────────────────

_next_id = 1


def _new_id() -> int:
    global _next_id
    i = _next_id
    _next_id += 1
    return i


@dataclass
class Player:
    player_id:   int
    name:        str
    gender:      str    # "female" | "male"
    position:    str    # Guard | Wing | Big
    age:         int
    preferred_zone: str # ft | paint | mid | 3pt
    pace_contrib:   float  # delta to team pace preference
    motivation:     str    # winning | market | loyalty

    contract_years_remaining: int
    contract_length: int

    # ── Hidden (not surfaced directly in commissioner UI) ─────────────────────
    peak_ortg:     float   # offensive contribution at peak
    peak_drtg:     float   # defensive contribution at peak (negative = suppresses scoring)
    career_length: int     # 8–20 seasons
    peak_season:   int     # seasons_played value when peak is reached
    start_mult:    float   # rating multiplier at career start (0.70–0.85)
    ceiling_noise: float   # baked-in noise offset for ceiling label
    durability:    float   # injury resistance (0.50–1.00); partially hidden

    # ── Mutable state ─────────────────────────────────────────────────────────
    seasons_played: int = 0
    team_id: int | None = None   # None = free agent / unsigned
    retiring: bool = False
    retired:  bool = False
    happiness: float = 0.5         # 0.0–1.0; recomputed each offseason
    popularity: float = 0.0        # 0.0–1.0; updated each season
    seasons_with_team: int = 0     # resets on team change; drives loyalty happiness
    fatigue: float = 0.0           # accumulated playoff load (0.0–1.0); decays each offseason
    crossed_picket: bool = False   # True if player signed a scab/replacement contract (Type C)

    # ── Computed: current ratings ─────────────────────────────────────────────

    @property
    def mult(self) -> float:
        return _career_mult(self.seasons_played, self.peak_season,
                            self.career_length, self.start_mult)

    @property
    def ortg_contrib(self) -> float:
        """Current offensive contribution delta from baseline."""
        return round(self.peak_ortg * self.mult, 2)

    @property
    def drtg_contrib(self) -> float:
        """Current defensive contribution delta (negative = suppresses scoring)."""
        return round(self.peak_drtg * self.mult, 2)

    @property
    def overall(self) -> float:
        """Combined quality for sorting/display. Higher = better."""
        return self.ortg_contrib - self.drtg_contrib

    @property
    def peak_overall(self) -> float:
        return self.peak_ortg - self.peak_drtg

    @property
    def ceiling_tier(self) -> str:
        """Noisy ceiling indicator — what the commissioner sees for prospects."""
        val = self.peak_overall + self.ceiling_noise
        if val >= 18:  return TIER_ELITE
        if val >= 12:  return TIER_HIGH
        if val >= 6:   return TIER_MID
        return TIER_LOW

    @property
    def trend(self) -> str:
        """Season-over-season trend arrow."""
        if self.seasons_played < 1:
            return "→"
        prev = _career_mult(self.seasons_played - 1, self.peak_season,
                            self.career_length, self.start_mult)
        curr = self.mult
        if curr > prev + 0.015: return "↑"
        if curr < prev - 0.015: return "↓"
        return "→"

    @property
    def is_declining(self) -> bool:
        return self.seasons_played > self.peak_season

    @property
    def happiness_mult(self) -> float:
        """Performance multiplier from happiness. Only penalises Restless/Miserable."""
        if self.happiness >= 0.50: return 1.0
        if self.happiness >= 0.25: return 0.93   # Restless: −7%
        return 0.85                               # Miserable: −15%

    def advance_season(self) -> bool:
        """Increment age and career counter. Returns True if player retires."""
        self.seasons_played += 1
        self.age += 1
        if self.contract_years_remaining > 0:
            self.contract_years_remaining -= 1
        if self.seasons_played >= self.career_length:
            self.retiring = True
        return self.retiring

    def __repr__(self) -> str:
        return f"{self.name} ({self.position}, {self.age})"


# ── Generation ────────────────────────────────────────────────────────────────

def _zone_for_position(pos: str) -> str:
    if pos == GUARD:
        return random.choices(ZONES, weights=[10, 10, 30, 50])[0]
    elif pos == BIG:
        return random.choices(ZONES, weights=[25, 50, 15, 10])[0]
    else:  # Wing
        return random.choices(ZONES, weights=[10, 20, 25, 45])[0]


def generate_player(
    position:        str | None = None,
    age:             int | None = None,
    tier:            str | None = None,
    founding:        bool = False,
    contract_length: int | None = None,
) -> Player:
    """Create a new Player with hidden career arc set.

    Args:
        position:        Force a position; random if None.
        age:             Force an age; uses defaults if None.
        tier:            "elite" | "high" | "mid" | "low" — quality tier.
                         Randomly weighted if None.
        founding:        True for league-start players (older, already mid-career).
        contract_length: Override contract; uses age-based default if None.
    """
    pos = position or random.choice(POSITIONS)

    # Age
    if age is not None:
        a = age
    elif founding:
        a = random.randint(22, 32)
    else:
        a = random.randint(18, 22)  # draft prospects

    # Quality tier
    if tier is None:
        tier = random.choices(
            ["elite", "high", "mid", "low"],
            weights=[5, 20, 45, 30],
        )[0]

    # Peak contributions by tier
    # Tier floors are chosen so peak_overall (p_ortg − p_drtg) ranges never overlap:
    #   elite ≥ 17  (10−(−7))  ·  high ≤ 16 (9−(−7))  ·  mid ≤ 10 (6−(−4))  ·  low ≥ 0 (enforced below)
    if tier == "elite":
        p_ortg = random.uniform(10.0, 12.0)   # was 9.0 — raised floor to close overlap with High
        p_drtg = random.uniform(-10.0, -7.0)
    elif tier == "high":
        p_ortg = random.uniform(6.0, 9.0)
        p_drtg = random.uniform(-7.0, -4.0)
    elif tier == "mid":
        p_ortg = random.uniform(2.0, 6.0)
        p_drtg = random.uniform(-4.0, -1.0)
    else:  # low
        p_ortg = random.uniform(-2.0, 3.0)
        p_drtg = random.uniform(-2.0, 4.0)
        # Floor: no rostered player should be a net negative overall.
        # A zero-scorer who locks down their match-up (Rodman) is fine at 0.
        # Clamp p_drtg so peak_overall = p_ortg − p_drtg ≥ 0.
        p_drtg = min(p_drtg, p_ortg)

    # Career arc
    seasons_already = max(0, a - 22) if founding else 0
    min_career = max(8, seasons_already + 5)  # at least 5 more seasons for founding players
    career_len = random.randint(min_career, max(min_career, 20))
    peak_mid   = (seasons_already + career_len) // 2
    peak_s     = max(0, min(career_len - 2,
                            peak_mid - seasons_already + random.randint(-2, 2)))
    start_m    = random.uniform(0.70, 0.85)

    # Preferred zone and pace
    zone = _zone_for_position(pos)
    if pos == GUARD:
        pace = random.uniform(1.0, 8.0)
    elif pos == BIG:
        pace = random.uniform(-8.0, -1.0)
    else:
        pace = random.uniform(-3.0, 4.0)

    # Motivation
    mot = random.choices(
        MOTIVATIONS,
        weights=[40, 35, 25],
    )[0]

    # Contract
    if contract_length is not None:
        cl = contract_length
    elif founding:
        cl = 3
    else:
        if a <= 25:   cl = random.randint(3, 5)
        elif a <= 30: cl = random.randint(2, 4)
        else:         cl = random.randint(2, 3)

    name, gender = _make_name()
    return Player(
        player_id              = _new_id(),
        name                   = name,
        gender                 = gender,
        position               = pos,
        age                    = a,
        preferred_zone         = zone,
        pace_contrib           = pace,
        motivation             = mot,
        contract_years_remaining = cl,
        contract_length        = cl,
        peak_ortg              = p_ortg,
        peak_drtg              = p_drtg,
        career_length          = career_len,
        peak_season            = peak_s,
        start_mult             = start_m,
        ceiling_noise          = random.gauss(0, 2.0),
        durability             = random.uniform(0.50, 1.00),
        seasons_played         = seasons_already,
        seasons_with_team      = seasons_already,  # founding players have tenure
    )


def generate_draft_class(n: int, talent_boost: float = 0.0) -> list[Player]:
    """Generate n draft prospects. Mostly mid/low ceiling with rare high/elite.

    talent_boost (0.0–1.0): shifts weights toward elite/high tiers.
    At 1.0: elite ~13%, high ~27%, mid ~37%, low ~23%.
    """
    b = max(0.0, min(1.0, talent_boost))
    elite_w = 3  + round(b * 10)
    high_w  = 15 + round(b * 12)
    mid_w   = max(25, 47 - round(b * 10))
    low_w   = max(20, 35 - round(b * 12))
    prospects = []
    for _ in range(n):
        tier = random.choices(
            ["elite", "high", "mid", "low"],
            weights=[elite_w, high_w, mid_w, low_w],
        )[0]
        prospects.append(generate_player(tier=tier, founding=False))
    return prospects
