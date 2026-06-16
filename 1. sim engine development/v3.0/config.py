from dataclasses import dataclass


@dataclass
class Config:
    num_teams: int = 20
    possessions: int = 95           # per team per game (neutral era baseline)
    possession_scale: float = 100.0 # possessions += league_meta * possession_scale
    min_quality: float = 3.0
    max_quality: float = 3.3
    quality_delta: float = 0.03     # quality change per win/loss
    O_scale: float = 1.333          # offensive scaling of quality excess
    D_scale: float = 1.333          # defensive scaling of quality excess
    home_advantage: float = 0.05    # added to home team's effective strength (regular season)
    playoff_home_advantage: float = 0.05  # home advantage during playoff series
    playoff_seed_bonus: float = 0.04      # always-on bonus for the higher seed in every playoff game
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
    # League meta (era) dynamics
    meta_sigma: float = 0.012             # random velocity noise per season
    meta_reversion: float = 0.05          # spring pull back toward neutral
    meta_velocity_damping: float = 0.80   # velocity decay per season
    meta_max: float = 0.15                # max era shift (controls possession swing)
    meta_champion_influence: float = 0.010 # recent champ identity → velocity push
    meta_identity_nudge: float = 0.015    # meta → team identity drift nudge
    # Popularity
    popularity_market_weight: float = 0.40  # pull toward market baseline each season
    popularity_championship:  float = 0.08  # boost for winning title
    popularity_finals:        float = 0.04  # boost for reaching finals
    popularity_playoff:       float = 0.01  # boost for any playoff appearance
    popularity_miss_playoffs: float = 0.01  # penalty per consecutive playoff miss (progressive)
    popularity_miss_playoffs_max: float = 0.05  # cap on progressive miss penalty
    popularity_bottom2:       float = 0.03  # extra penalty for bottom-2 finish
    popularity_relocation_keep: float = 0.6 # fraction of popularity retained on relocation
    # Rule-change shocks
    meta_shock_threshold: float = 0.05   # |meta| must exceed this to be shock-eligible
    meta_shock_min_seasons: int = 6      # consecutive extreme seasons before eligible
    meta_shock_base_prob: float = 0.20   # base probability per season when eligible
    meta_shock_prob_growth: float = 0.04 # extra probability per season beyond minimum
    meta_shock_spread: float = 0.025     # std dev of post-shock meta (allows over/undercorrect)
