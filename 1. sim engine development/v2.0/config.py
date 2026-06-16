from dataclasses import dataclass


@dataclass
class Config:
    num_teams: int = 20
    possessions: int = 100          # per team per game
    min_quality: float = 3.0
    max_quality: float = 3.3
    quality_delta: float = 0.05     # quality change per win/loss
    O_scale: float = 1.333          # offensive scaling of quality excess
    D_scale: float = 1.333          # defensive scaling of quality excess
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
    offseason_sigma: float = 0.07        # std dev for non-playoff team quality adjustment
    market_bias: float = 0.03            # max mean shift for market-size effect on offseason
    # Identity evolution
    identity_reinforce_champ: float = 0.08    # identity pull toward extreme for champion
    identity_reinforce_finalist: float = 0.05 # identity pull for finalist
    identity_reinforce_playoff: float = 0.03  # identity pull for other playoff teams
    identity_drift_sigma: float = 0.06        # base std dev for identity random drift
