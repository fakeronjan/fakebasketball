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
    # Home court is dynamic: base (travel/familiarity) + crowd component (scales with team.popularity).
    # At avg popularity 0.50: effective bonus ≈ base + scale×0.50 = 0.007 + 0.007 = 0.014 (unchanged league avg).
    home_pscore_bonus_base: float = 0.007      # fixed floor — travel fatigue, court familiarity
    home_pscore_bonus_pop_scale: float = 0.014  # crowd component; multiplied by home team's popularity
    playoff_seed_pscore_bonus: float = 0.005    # reduced — popular/better teams already get more home court
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
    # Era-driven zone efficiency: base make% shifts with league_meta
    # 3pt improves in a 3pt era; paint improves in a paint era (and vice versa).
    # FT and mid stay stable. At meta=±0.15: 3pt shifts ±0.020, paint shifts ±0.015.
    meta_3pt_base_scale:   float = 0.13   # 3pt base += league_meta × this
    meta_paint_base_scale: float = 0.10   # paint base -= league_meta × this
    # ── Rule-change shocks ────────────────────────────────────────────────────
    meta_shock_threshold: float = 0.05
    meta_shock_min_seasons: int = 6
    meta_shock_base_prob: float = 0.20
    meta_shock_prob_growth: float = 0.04
    meta_shock_spread: float = 0.025
    # ── Championship entropy (dynasty decay) ─────────────────────────────────
    # After winning the championship, a team's ortg/drtg regress toward baseline.
    # Compounds per consecutive title (up to 3x): factor^1, factor^2, factor^3.
    # At 0.84: 1st defense → -1.28 pts; 2nd → -2.43 pts; 3rd+ → -3.44 pts (ortg=118 basis).
    # Simulates opponents studying more tape, complacency, and the difficulty of sustaining peaks.
    champion_entropy_factor: float = 0.84
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
    league_pop_engagement_pull: float = 0.07   # was 0.15 — reduced so narrative signals aren't drowned out
    league_pop_drama_max: float = 0.025        # was 0.08 — rescaled to match peer signal magnitudes
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
    revenue_per_fan_million: float = 7.5
    owner_treasury_share:    float = 0.20   # commissioner takes 20% of gross; teams get 80%
    team_cost_base:          float = 0.0    # flat operating cost per team (intentionally 0 — metro scales it)
    team_cost_per_metro:     float = 0.11   # $0.11M per million effective_metro per season (progressive curve applied at runtime)
    # ── Legitimacy ────────────────────────────────────────────────────────────
    legitimacy_recovery: float = 0.02
    legitimacy_pop_penalty: float = 0.03
    # ── Player model ──────────────────────────────────────────────────────────
    player_slots: int = 3                    # cornerstone slots per team
    slot_weight_star:    float = 0.50        # Star weight in team rating aggregation
    slot_weight_costar:  float = 0.30        # Co-Star weight
    slot_weight_starter: float = 0.20        # Starter weight
    # Shot selection weights: who initiates each possession (≠ rating weights)
    # Bench slot absorbs remaining weight — top-3 total ≈ 66% of possessions.
    slot_shot_star:    float = 0.21   # was 0.28→0.24→0.21 — reduced to bring scoring leader PPG to ~26-30
    slot_shot_costar:  float = 0.22
    slot_shot_starter: float = 0.16
    slot_shot_bench:   float = 0.37   # aggregate "rest of team" (no individual tracking)
    player_career_min: int = 8
    player_career_max: int = 20
    player_founding_contract: int = 3        # all founding players start on 3-year deals
    player_contract_min: int = 2
    player_contract_max: int = 5
    # Chemistry — bonus-only cohesion multiplier (floor 1.00, no negative amplification)
    # Fit bonuses are purely additive; bad fit = no bonus, not a penalty.
    # Continuity grows with diminishing returns via a saturating curve.
    # Result range: thrown-together ≈ 1.00, well-built ≈ 1.03–1.06, elite core ≈ 1.08–1.12
    chemistry_min: float = 1.00             # floor — chemistry never hurts
    chemistry_max: float = 1.15             # ceiling — exceptional long-running core
    chemistry_positional_bonus: float = 0.03  # all filled slots have different positions
    chemistry_zone_bonus:       float = 0.02  # all filled slots have different preferred zones
    # Continuity: max_bonus × (1 − e^(−k × avg_pair_seasons))
    # k=0.55 gives: 1yr→+0.030, 2yr→+0.047, 3yr→+0.057, 5yr→+0.066, 10yr→+0.070 (≈max)
    chemistry_continuity_max: float = 0.07   # asymptotic ceiling for continuity component
    chemistry_continuity_k:   float = 0.55   # curvature — higher = faster saturation
    # Draft
    draft_class_base: int = 3                # minimum draft class size
    # Free agency
    fa_pool_per_team: int = 1                # free agents available per team in the league
    # Star FA event threshold (peak_overall above this triggers special FA event)
    star_fa_threshold: float = 14.0
    # ── Injury & fatigue ──────────────────────────────────────────────────────
    player_durability_min: float = 0.50   # most fragile possible player
    player_durability_max: float = 1.00   # most durable possible player
    # Injury probability = base + (1−dur)×dur_scale + fatigue×fat_scale + age_factor
    player_injury_base_prob: float = 0.12   # 12% base chance of missing some games
    player_injury_durability_scale: float = 0.20  # fragile penalty (additive on prob)
    player_injury_fatigue_scale: float = 0.28     # fatigue penalty (additive on prob)
    player_injury_age_threshold: int = 30          # age at which risk begins rising
    player_injury_age_scale: float = 0.012         # per year past threshold
    player_injury_games_min: int = 5
    player_injury_games_max: int = 20
    # Fatigue: earned from playoff exposure; decays (but not fully) each offseason
    player_fatigue_per_playoff_game: float = 0.020  # per playoff game played (was 0.012)
    player_fatigue_decay: float = 0.68              # fraction carried to next season (was 0.60)
    # ── Rival league (Type A — external investors) ────────────────────────────
    rival_a_min_season: int = 8                     # earliest season a rival can form (was 5)
    rival_a_popularity_threshold: float = 0.43      # league_popularity must exceed this (was 0.72 — unreachable; recalibrated to actual equilibrium ~0.47)
    rival_a_consecutive_seasons: int = 5            # seasons above threshold before rival forms (was 3; higher bar offsets lower threshold)
    rival_a_cooldown: int = 10                      # seasons after resolution before next rival (was 8)
    rival_a_funding_min: float = 0.20               # least-funded rival
    rival_a_funding_max: float = 0.90               # most-funded rival
    rival_a_teams_min: int = 4
    rival_a_teams_max: int = 8
    # Rival strength dynamics
    rival_strength_base_growth: float = 0.04        # passive growth per season (no commissioner action)
    rival_strength_collapse_threshold: float = 0.0  # collapses when strength reaches this
    rival_forced_merger_legitimacy: float = 0.20    # your legitimacy floor that triggers forced merger
    rival_forced_merger_strength: float = 0.70      # rival must be at least this strong
    rival_merger_offer_max_strength: float = 0.40   # rival must be this weak for brokered merger option
    # Commissioner action costs / effects
    rival_talent_war_cost_min: float = 15.0         # $M treasury cost
    rival_talent_war_cost_max: float = 25.0
    rival_talent_war_strength_delta: float = -0.08  # rival strength change
    rival_legal_pressure_strength_delta: float = -0.12
    rival_legal_pressure_legit_cost: float = 0.05
    rival_brokered_merger_cost_min: float = 30.0
    rival_brokered_merger_cost_max: float = 50.0
    rival_brokered_merger_legit_cost: float = 0.08
    # Passive effects on your league
    rival_pop_dampening_threshold: float = 0.50     # strength above this slows your pop growth
    rival_pop_dampening_factor: float = 0.40        # fraction of normal pop growth retained
    # Type A rivals above this strength erode commissioner legitimacy each season —
    # represents investors poaching talent, media narratives, and owner restlessness.
    rival_a_legit_drain_threshold: float = 0.35     # rival strength above which drain activates
    rival_a_legit_drain_rate: float = 0.015         # legitimacy drained per rival season (applies to Type A only)
    # ── Rival league (Type B — owner defection) ───────────────────────────────
    rival_b_min_season: int = 6                     # earliest season a defection can fire
    rival_b_ringleader_seasons: int = 2             # THREAT_DEMAND seasons before recruiting starts
    rival_b_min_defectors: int = 4                  # minimum defecting owners to trigger split
    rival_b_follow_prob_demand: float = 0.70        # probability a THREAT_DEMAND owner follows ringleader
    rival_b_follow_prob_lean: float = 0.30          # probability a THREAT_LEAN owner follows
    rival_b_follow_prob_quiet: float = 0.05         # probability a THREAT_QUIET owner follows
    rival_b_cooldown: int = 6                       # seasons after resolution before next Type B
    rival_b_win_back_cost_min: float = 20.0         # $M to negotiate team return
    rival_b_win_back_cost_max: float = 40.0
    rival_b_win_back_legit_cost: float = 0.06
    rival_b_win_back_prob: float = 0.55             # probability each team agrees to return
    # ── Rival league (Type C — player walkout) ────────────────────────────────
    rival_c_min_season: int = 5                     # earliest season a walkout can fire
    rival_c_cooldown: int = 10                      # seasons after resolution before next Type C
    rival_c_player_circuit_decay: float = -0.06     # strength delta per season (natural degradation)
    rival_c_fan_engagement_penalty: float = -0.05   # league popularity per season during walkout
    rival_c_legitimacy_penalty: float = -0.04       # legitimacy per season during walkout
    rival_c_scab_happiness_penalty: float = -0.15   # happiness for scab players who rejoin
    rival_c_concession_legit_min: float = 0.05      # legitimacy cost of offering CBA concessions
    rival_c_concession_legit_max: float = 0.15
