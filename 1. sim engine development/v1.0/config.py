from dataclasses import dataclass


@dataclass
class Config:
    num_teams: int = 20
    possessions: int = 100          # per team per game
    min_strength: float = 3.0
    max_strength: float = 3.3
    strength_delta: float = 0.05    # strength change per win/loss
    home_advantage: float = 0.05    # added to home team's effective strength (regular season)
    playoff_home_advantage: float = 0.10  # home advantage during playoff series
    playoff_teams: int = 8
    series_length: int = 7          # best-of-N (should be odd)
    num_seasons: int = 20
    relocation_threshold: int = 8        # consecutive losing seasons before eligible
    relocation_bottom2_required: int = 3 # min bottom-2 finishes within the streak
    relocation_chance: float = 0.5       # probability of relocating if eligible
    championship_protection: int = 20    # seasons of protection after winning title
    finals_protection: int = 10          # seasons of protection after reaching finals
    offseason_sigma: float = 0.07        # std dev for non-playoff team strength adjustment
    market_bias: float = 0.03           # max mean shift for market-size effect on offseason
