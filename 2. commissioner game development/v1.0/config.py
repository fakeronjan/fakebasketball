from dataclasses import dataclass, field


@dataclass
class Config:
    num_teams: int = 20          # legacy field, ignored when initial_teams is set
    num_seasons: int = 20
    # ── League size ───────────────────────────────────────────────────────────
    initial_teams: int = 8       # teams at league founding
    max_teams: int = 32          # hard cap on league size
    # ── Expansion ─────────────────────────────────────────────────────────────
    expansion_min_seasons: int = 4          # min seasons between expansion waves
    expansion_consecutive_seasons: int = 2  # seasons above pop threshold before wave fires
    expansion_trigger_popularity: float = 0.52  # league_pop threshold to trigger expansion
    expansion_boom_popularity: float = 0.70    # above this → larger wave
    expansion_teams_per_wave: int = 2          # franchises added per normal wave
    expansion_boom_teams: int = 4              # franchises added per boom wave
    expansion_grace_seasons: int = 5           # seasons before expansion team eligible for relocation
    expansion_secondary_min_seasons: int = 8   # seasons primary must exist before secondary eligible
    # ── Rival league merger ────────────────────────────────────────────────────
    merger_trigger_popularity: float = 0.50   # league_pop below this triggers merger eligibility
    merger_consecutive_seasons: int = 4       # seasons below threshold before merger fires
    merger_min_teams: int = 10                # league must have this many teams first
    merger_max_teams: int = 22                # mergers only while league is still growing
    merger_min_season: int = 8                # earliest season a merger can occur
    merger_cooldown_seasons: int = 15         # min seasons between mergers
    merger_size_min: int = 4                  # min teams absorbed
    merger_size_max: int = 8                  # max teams absorbed
    merger_quality_min: float = 3.10          # min starting quality for merger teams
    merger_quality_max: float = 3.25          # max starting quality for merger teams
    merger_pop_fraction_min: float = 0.35     # min fraction of market baseline for starting pop
    merger_pop_fraction_max: float = 0.65     # max fraction of market baseline for starting pop
    merger_league_pop_boost: float = 0.06     # league pop bump when merger fires
    # ── Game engine ──────────────────────────────────────────────────────────
    games_per_pair: int = 0          # 0 = auto-calculate based on team count
    playoff_teams_override: int = 0  # 0 = auto based on league size
    possessions: int = 95           # per team per game (neutral era baseline)
    possession_scale: float = 100.0 # possessions += league_meta * possession_scale
    min_quality: float = 3.0
    max_quality: float = 3.3
    quality_delta: float = 0.03     # quality change per win/loss
    initial_quality_mode: str = "moderate"  # uniform | moderate | haves_havenots
    O_scale: float = 1.333          # offensive scaling of quality excess
    D_scale: float = 1.333          # defensive scaling of quality excess
    home_advantage: float = 0.05    # added to home team's effective strength (regular season)
    playoff_home_advantage: float = 0.05  # home advantage during playoff series
    playoff_seed_bonus: float = 0.04      # always-on bonus for the higher seed in every playoff game
    series_length: int = 7          # best-of-N (should be odd)
    # ── Relocation ────────────────────────────────────────────────────────────
    relocation_threshold: int = 8        # consecutive losing seasons before eligible
    relocation_bottom2_required: int = 3 # min bottom-2 finishes within the streak
    relocation_chance: float = 0.5       # probability of relocating if eligible
    championship_protection: int = 20    # seasons of protection after winning title
    finals_protection: int = 10          # seasons of protection after reaching finals
    # ── Offseason ─────────────────────────────────────────────────────────────
    offseason_sigma: float = 0.07        # std dev for non-playoff team quality adjustment
    market_bias: float = 0.03            # max mean shift for market-size effect on offseason
    # ── Identity evolution ────────────────────────────────────────────────────
    identity_reinforce_champ: float = 0.08    # identity pull toward extreme for champion
    identity_reinforce_finalist: float = 0.05 # identity pull for finalist
    identity_reinforce_playoff: float = 0.03  # identity pull for other playoff teams
    identity_drift_sigma: float = 0.06        # base std dev for identity random drift
    # ── League meta (era) dynamics ────────────────────────────────────────────
    meta_sigma: float = 0.012             # random velocity noise per season
    meta_reversion: float = 0.05          # spring pull back toward neutral
    meta_velocity_damping: float = 0.80   # velocity decay per season
    meta_max: float = 0.15                # max era shift (controls possession swing)
    meta_champion_influence: float = 0.010 # recent champ identity → velocity push
    meta_identity_nudge: float = 0.015    # meta → team identity drift nudge
    # ── Rule-change shocks ────────────────────────────────────────────────────
    meta_shock_threshold: float = 0.05   # |meta| must exceed this to be shock-eligible
    meta_shock_min_seasons: int = 6      # consecutive extreme seasons before eligible
    meta_shock_base_prob: float = 0.20   # base probability per season when eligible
    meta_shock_prob_growth: float = 0.04 # extra probability per season beyond minimum
    meta_shock_spread: float = 0.025     # std dev of post-shock meta
    # ── Championship legacy ───────────────────────────────────────────────────
    legacy_per_title: float = 0.03       # legacy gained per championship
    legacy_max: float = 0.15             # cap on total legacy boost
    legacy_decay: float = 0.03           # fraction lost per season (~23-season half-life)
    # ── Co-tenant market sharing ─────────────────────────────────────────────
    cotenant_primary_share: float = 0.70    # primary's natural market target (fraction of baseline)
    cotenant_secondary_share: float = 0.50  # secondary's natural market target (fraction of baseline)
    cotenant_steal_fraction: float = 0.25   # fraction of champ/finals boost stolen from co-tenant
    # ── Popularity (team) ─────────────────────────────────────────────────────
    popularity_market_weight: float = 0.40  # pull toward market baseline each season
    popularity_championship:  float = 0.08  # boost for winning title
    popularity_finals:        float = 0.04  # boost for reaching finals
    popularity_playoff:       float = 0.01  # boost for any playoff appearance
    popularity_miss_playoffs: float = 0.01  # penalty per consecutive playoff miss (progressive)
    popularity_miss_playoffs_max: float = 0.05  # cap on progressive miss penalty
    popularity_bottom2:       float = 0.03  # extra penalty for bottom-2 finish
    popularity_relocation_keep: float = 0.6 # fraction of popularity retained on relocation
    # ── League popularity ─────────────────────────────────────────────────────
    league_pop_engagement_pull: float = 0.15    # how fast league_pop converges to market-engagement avg
    league_pop_drama_max: float = 0.08          # max seasonal boost from dramatic playoff series
    league_pop_entertainment_max: float = 0.015 # max boost at optimal meta (slight offensive lean)
    league_pop_balance_window: int = 8          # seasons to look back for champion variety
    league_pop_balance_penalty: float = 0.025   # max penalty/bonus from competitive balance
    league_pop_rivalry_bonus: float = 0.008     # boost per established rivalry (capped at 3)
    league_pop_expansion_boost: float = 0.02    # one-time boost when expansion wave fires
    # ── Market grudge ─────────────────────────────────────────────────────────
    market_grudge_decay: float = 0.08    # fraction of grudge lost per season
    market_grudge_floor: float = 0.05    # grudge floor until market is made whole
    league_pop_grudge_max: float = 0.015 # max league pop penalty from grudge markets
    league_pop_geo_spread_max: float = 0.010   # max boost from geographically spread playoffs
    league_pop_finals_interest_scale: float = 0.008  # Finals matchup market-interest effect
    league_pop_legacy_matchup_scale: float = 0.8    # scales legacy-product across all playoff series
    # ── Revenue ───────────────────────────────────────────────────────────────
    revenue_per_fan_million: float = 5.0            # annual revenue per million fans in fan base
    # ── Legitimacy ────────────────────────────────────────────────────────────
    legitimacy_recovery: float = 0.02       # legitimacy recovered per season (passive)
    legitimacy_pop_penalty: float = 0.03    # max league pop penalty when legitimacy is low
