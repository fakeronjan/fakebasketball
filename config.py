from dataclasses import dataclass, field


@dataclass
class Config:
    num_seasons: int = 20
    # ── League size ───────────────────────────────────────────────────────────
    initial_teams: int = 8
    max_teams: int = 32
    # ── Expansion ─────────────────────────────────────────────────────────────
    expansion_min_seasons: int = 4
    expansion_consecutive_seasons: int = 2
    expansion_trigger_popularity: float = 0.52
    expansion_boom_popularity: float = 0.70
    expansion_teams_per_wave: int = 2
    expansion_boom_teams: int = 4
    expansion_grace_seasons: int = 5
    expansion_secondary_min_seasons: int = 8
    # ── Rival league merger ────────────────────────────────────────────────────
    merger_trigger_popularity: float = 0.50
    merger_consecutive_seasons: int = 4
    merger_min_teams: int = 10
    merger_max_teams: int = 22
    merger_min_season: int = 8
    merger_cooldown_seasons: int = 15
    merger_size_min: int = 4
    merger_size_max: int = 8
    merger_ortg_min: float = 104.0   # min starting ORtg for merger teams
    merger_ortg_max: float = 116.0   # max starting ORtg for merger teams
    merger_drtg_min: float = 104.0   # min starting DRtg for merger teams
    merger_drtg_max: float = 116.0   # max starting DRtg for merger teams
    merger_pop_fraction_min: float = 0.35
    merger_pop_fraction_max: float = 0.65
    merger_league_pop_boost: float = 0.06
    # ── Game engine ───────────────────────────────────────────────────────────
    games_per_pair: int = 0
    playoff_teams_override: int = 0
    series_length: int = 7
    # ── Team rating bounds ────────────────────────────────────────────────────
    ortg_baseline: float = 110.0     # league average ORtg (pts per 100 poss)
    drtg_baseline: float = 110.0     # league average DRtg (pts per 100 poss allowed)
    pace_baseline: float = 95.0      # league average pace (poss per team per game)
    ortg_min: float = 100.0
    ortg_max: float = 120.0
    drtg_min: float = 100.0
    drtg_max: float = 120.0
    pace_min: float = 82.0
    pace_max: float = 108.0
    initial_rating_mode: str = "moderate"  # uniform | moderate | haves_havenots
    # ── Home / playoff advantage ──────────────────────────────────────────────
    home_pscore_bonus: float = 0.020     # p_score boost for home team (regular season)
    playoff_home_pscore_bonus: float = 0.020  # p_score boost for home team (playoffs)
    playoff_seed_pscore_bonus: float = 0.015  # always-on bonus for the higher seed
    pace_home_weight: float = 0.80       # home team weight in game pace calculation
    # ── Offseason random walk ─────────────────────────────────────────────────
    ortg_sigma: float = 2.0
    drtg_sigma: float = 2.0
    pace_sigma: float = 1.5
    style_3pt_sigma: float = 0.020
    # ── Relocation ────────────────────────────────────────────────────────────
    relocation_threshold: int = 8
    relocation_bottom2_required: int = 3
    relocation_chance: float = 0.5
    championship_protection: int = 20
    finals_protection: int = 10
    # ── League meta (era) dynamics ────────────────────────────────────────────
    meta_sigma: float = 0.012
    meta_reversion: float = 0.05
    meta_velocity_damping: float = 0.80
    meta_max: float = 0.15
    meta_champion_style_influence: float = 0.010  # champ style_3pt → meta velocity push
    meta_style_nudge: float = 0.015    # meta → team style_3pt drift per season
    meta_pace_scale: float = 50.0      # possessions += league_meta × pace_scale
    # ── Rule-change shocks ────────────────────────────────────────────────────
    meta_shock_threshold: float = 0.05
    meta_shock_min_seasons: int = 6
    meta_shock_base_prob: float = 0.20
    meta_shock_prob_growth: float = 0.04
    meta_shock_spread: float = 0.025
    # ── Championship legacy ───────────────────────────────────────────────────
    legacy_per_title: float = 0.03
    legacy_max: float = 0.15
    legacy_decay: float = 0.03
    # ── Co-tenant market sharing ─────────────────────────────────────────────
    cotenant_primary_share: float = 0.70
    cotenant_secondary_share: float = 0.50
    cotenant_steal_fraction: float = 0.25
    # ── Popularity (team) ─────────────────────────────────────────────────────
    popularity_market_weight: float = 0.40
    popularity_championship:  float = 0.08
    popularity_finals:        float = 0.04
    popularity_playoff:       float = 0.01
    popularity_miss_playoffs: float = 0.01
    popularity_miss_playoffs_max: float = 0.05
    popularity_bottom2:       float = 0.03
    # ── League popularity ─────────────────────────────────────────────────────
    league_pop_engagement_pull: float = 0.15
    league_pop_drama_max: float = 0.08
    league_pop_entertainment_max: float = 0.015
    league_pop_balance_window: int = 8
    league_pop_balance_penalty: float = 0.025
    league_pop_rivalry_bonus: float = 0.008
    league_pop_expansion_boost: float = 0.02
    # ── Market grudge ─────────────────────────────────────────────────────────
    market_grudge_decay: float = 0.08
    market_grudge_floor: float = 0.05
    league_pop_grudge_max: float = 0.015
    league_pop_geo_spread_max: float = 0.010
    league_pop_finals_interest_scale: float = 0.008
    league_pop_legacy_matchup_scale: float = 0.8
    # ── Revenue ───────────────────────────────────────────────────────────────
    revenue_per_fan_million: float = 5.0
    # ── Legitimacy ────────────────────────────────────────────────────────────
    legitimacy_recovery: float = 0.02
    legitimacy_pop_penalty: float = 0.03
    # ── Player model ──────────────────────────────────────────────────────────
    player_slots: int = 3                    # cornerstone slots per team
    slot_weight_star:    float = 0.50        # Star weight in team rating aggregation
    slot_weight_costar:  float = 0.30        # Co-Star weight
    slot_weight_starter: float = 0.20        # Starter weight
    player_career_min: int = 8
    player_career_max: int = 20
    player_founding_contract: int = 3        # all founding players start on 3-year deals
    player_contract_min: int = 2
    player_contract_max: int = 5
    # Chemistry multiplier bounds and components
    chemistry_min: float = 0.80
    chemistry_max: float = 1.10
    chemistry_positional_bonus:   float = 0.04   # all 3 positions different
    chemistry_positional_penalty: float = 0.06   # duplicate positions
    chemistry_zone_bonus:         float = 0.03   # all 3 preferred zones different
    chemistry_zone_penalty:       float = 0.04   # all 3 preferred zones same
    chemistry_continuity_per_season: float = 0.005  # per season of pair continuity (max 3 seasons)
    # Draft
    draft_class_base: int = 3                # minimum draft class size
    # Free agency
    fa_pool_per_team: int = 1                # free agents available per team in the league
    # Star FA event threshold (peak_overall above this triggers special FA event)
    star_fa_threshold: float = 14.0
