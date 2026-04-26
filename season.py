from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cmp_to_key
from typing import TYPE_CHECKING

from config import Config
from game import GameResult, PlayerGameLog, _BENCH_ID, play_game, play_series
from team import Team

if TYPE_CHECKING:
    from player import Player


# ── Per-player season statistics ──────────────────────────────────────────────

@dataclass
class PlayerSeasonStats:
    """Accumulated per-player stats for one season (regular season only)."""
    player_id: int
    games:         int = 0
    games_missed:  int = 0   # games missed due to injury
    points:        int = 0
    fga:           int = 0
    fgm:           int = 0
    fga_3:         int = 0
    fgm_3:         int = 0
    fga_mid:       int = 0
    fgm_mid:       int = 0
    fga_paint:     int = 0
    fgm_paint:     int = 0
    fta:           int = 0
    ftm:           int = 0
    poss_defended: int = 0
    pts_allowed:   int = 0

    def absorb(self, log: PlayerGameLog) -> None:
        """Merge a single game log into season totals."""
        self.games         += 1
        self.points        += log.points
        self.fga           += log.fga
        self.fgm           += log.fgm
        self.fga_3         += log.fga_3
        self.fgm_3         += log.fgm_3
        self.fga_mid       += log.fga_mid
        self.fgm_mid       += log.fgm_mid
        self.fga_paint     += log.fga_paint
        self.fgm_paint     += log.fgm_paint
        self.fta           += log.fta
        self.ftm           += log.ftm
        self.poss_defended += log.poss_defended
        self.pts_allowed   += log.pts_allowed

    # ── Derived stats ─────────────────────────────────────────────────────────

    @property
    def ppg(self) -> float:
        return self.points / self.games if self.games else 0.0

    @property
    def fg_pct(self) -> float:
        return self.fgm / self.fga if self.fga else 0.0

    @property
    def fg3_pct(self) -> float:
        return self.fgm_3 / self.fga_3 if self.fga_3 else 0.0

    @property
    def ft_pct(self) -> float:
        return self.ftm / self.fta if self.fta else 0.0

    @property
    def def_rtg(self) -> float:
        """Points allowed per 100 possessions defended."""
        return self.pts_allowed / self.poss_defended * 100 if self.poss_defended else 0.0

    @property
    def paint_pct(self) -> float:
        return self.fgm_paint / self.fga_paint if self.fga_paint else 0.0

    @property
    def mid_pct(self) -> float:
        return self.fgm_mid / self.fga_mid if self.fga_mid else 0.0

    def pts_from_zone(self) -> tuple[int, int, int, int]:
        """Points scored from each zone: (paint, mid, three, ft)."""
        return (
            self.fgm_paint * 2,
            self.fgm_mid   * 2,
            self.fgm_3     * 3,
            self.ftm,
        )


def _playoff_count(n_teams: int) -> int:
    """Dynamic playoff bracket size based on league size."""
    if n_teams >= 24:
        return 16
    elif n_teams >= 14:
        return 8
    else:
        return 4


def _games_per_pair(n_teams: int, target: int = 40) -> int:
    """Number of times each unordered pair plays (always even, min 2).

    Chooses the even number closest to target / (n_teams - 1).
    With 8 teams → 6 (42 games), 12 → 4 (44), 16 → 2 (30), 20 → 2 (38), 32 → 2 (62).
    """
    opponents = n_teams - 1
    raw = target / opponents
    x = max(2, round(raw / 2) * 2)
    return x


def _generate_schedule(teams: list[Team], games_per_pair: int = 0) -> list[tuple[Team, Team]]:
    """Each pair plays games_per_pair times (or auto-calculated), split evenly home/away."""
    reps = (games_per_pair if games_per_pair > 0 else _games_per_pair(len(teams))) // 2
    matchups = [
        (home, away)
        for _ in range(reps)
        for home in teams
        for away in teams
        if home is not away
    ]
    random.shuffle(matchups)
    return matchups


def _round_name(n_remaining: int) -> str:
    return {2: "Finals", 4: "Semifinals", 8: "Quarterfinals", 16: "Round of 16"}.get(
        n_remaining, f"Round of {n_remaining}"
    )


def _round_labels(n_rounds: int) -> list[str]:
    """Short labels for each round, earliest first."""
    if n_rounds == 2:
        return ["SF", "Finals"]
    elif n_rounds == 3:
        return ["QF", "SF", "Finals"]
    elif n_rounds == 4:
        return ["R16", "QF", "SF", "Finals"]
    else:
        return [f"R{2 ** (n_rounds - i)}" for i in range(n_rounds - 1)] + ["Finals"]


@dataclass
class PlayoffSeries:
    seed1: Team
    seed2: Team
    winner: Team
    games: list[GameResult]

    @property
    def seed1_wins(self) -> int:
        return sum(1 for g in self.games if g.winner is self.seed1)

    @property
    def seed2_wins(self) -> int:
        return sum(1 for g in self.games if g.winner is self.seed2)


class Season:
    def __init__(self, number: int, teams: list[Team], cfg: Config, league_meta: float = 0.0):
        self.number = number
        self.teams = teams
        self.cfg = cfg
        self.league_meta = league_meta
        self.playoff_teams: int = (cfg.playoff_teams_override if cfg.playoff_teams_override > 0
                                   else _playoff_count(len(teams)))
        self.meta_shock: bool = False   # set True if a rule-change shock fires this offseason

        self._wins: dict[Team, int] = {t: 0 for t in teams}
        self._losses: dict[Team, int] = {t: 0 for t in teams}
        # Snapshot ratings at season start (ortg, drtg, pace, style_3pt)
        self._start_ratings: dict[Team, tuple[float, float, float, float]] = {
            t: (t.ortg, t.drtg, t.pace, t.style_3pt) for t in teams
        }

        self.regular_season_games: list[GameResult] = []
        self.regular_season_standings: list[Team] = []  # snapshot after regular season
        self.playoff_rounds: list[list[PlayoffSeries]] = []
        self.champion: Team | None = None

        # ── Player statistics (regular season) ────────────────────────────────
        self.player_stats: dict[int, PlayerSeasonStats] = {}  # player_id → stats
        # Name/team registry: snapshot at season start while rosters are intact.
        # Survives retirements/releases that mutate rosters later.
        self.player_names: dict[int, str] = {
            p.player_id: p.name
            for t in teams
            for p in t.roster
            if p is not None
        }
        self.player_teams: dict[int, str] = {
            p.player_id: t.franchise_at(number).nickname[:16]
            for t in teams
            for p in t.roster
            if p is not None
        }

        # ── Season awards ─────────────────────────────────────────────────────
        self.mvp:        Player | None = None
        self.mvp_team:   Team   | None = None
        self.opoy:       Player | None = None
        self.opoy_team:  Team   | None = None
        self.dpoy:       Player | None = None
        self.dpoy_team:  Team   | None = None
        self.finals_mvp:      Player | None = None
        self.finals_mvp_ppg:  float = 0.0   # Finals-only PPG for display
        self.finals_mvp_drtg: float = 0.0   # Finals-only DRtg for display
        self.mip:             Player | None = None
        self.mip_team:        Team   | None = None
        self.mip_delta:       float = 0.0   # composite 60/40 score improvement
        self.mip_ppg_delta:   float = 0.0   # PPG change for display
        # Coach of the Year (set by league.update_all_coach_happiness)
        self.coy:              "Coach | None" = None
        self.coy_team:         "Team  | None" = None
        self.coy_delta:        float = 0.0   # net rating delta (szn 2+) or net rating (szn 1)
        self.coy_first_season: bool  = False  # True when awarded on raw net rating (no prior baseline)

    # -- Record helpers -------------------------------------------------------

    def wins(self, team: Team) -> int:
        return self._wins[team]

    def losses(self, team: Team) -> int:
        return self._losses[team]

    def win_pct(self, team: Team) -> float:
        total = self._wins[team] + self._losses[team]
        return self._wins[team] / total if total > 0 else 0.5

    def _record(self, result: GameResult) -> None:
        self._wins[result.winner] += 1
        self._losses[result.loser] += 1

    def standings(self) -> list[Team]:
        # Build head-to-head wins from games played so far
        h2h: dict[Team, dict[Team, int]] = {t: {} for t in self.teams}
        for g in self.regular_season_games:
            h2h[g.winner][g.loser] = h2h[g.winner].get(g.loser, 0) + 1

        def compare(a: Team, b: Team) -> int:
            """Negative = a ranks higher. Tiebreaker order: win%, H2H win%, net rating."""
            pct_a, pct_b = self.win_pct(a), self.win_pct(b)
            if abs(pct_a - pct_b) > 1e-9:
                return -1 if pct_a > pct_b else 1
            wins_a = h2h[a].get(b, 0)
            wins_b = h2h[b].get(a, 0)
            if wins_a != wins_b:
                return -1 if wins_a > wins_b else 1
            net_a, net_b = a.ortg - a.drtg, b.ortg - b.drtg
            if abs(net_a - net_b) > 1e-9:
                return -1 if net_a > net_b else 1
            return 0

        return sorted(self.teams, key=cmp_to_key(compare))

    # -- Simulation -----------------------------------------------------------

    def reg_wins(self, team: Team) -> int:
        return self._reg_wins.get(team, 0)

    def reg_losses(self, team: Team) -> int:
        return self._reg_losses.get(team, 0)

    def reg_win_pct(self, team: Team) -> float:
        total = self.reg_wins(team) + self.reg_losses(team)
        return self.reg_wins(team) / total if total > 0 else 0.5

    def team_ppg(self, team: Team) -> float:
        """Average points scored per regular season game."""
        points = sum(
            g.home_score if g.home is team else g.away_score
            for g in self.regular_season_games
            if g.home is team or g.away is team
        )
        games = self.reg_wins(team) + self.reg_losses(team)
        return points / games if games > 0 else 0.0

    def team_papg(self, team: Team) -> float:
        """Average points allowed per regular season game."""
        points = sum(
            g.away_score if g.home is team else g.home_score
            for g in self.regular_season_games
            if g.home is team or g.away is team
        )
        games = self.reg_wins(team) + self.reg_losses(team)
        return points / games if games > 0 else 0.0

    def league_avg_ppg(self) -> float:
        """League-wide average points per team per game."""
        if not self.regular_season_games:
            return 0.0
        total = sum(g.home_score + g.away_score for g in self.regular_season_games)
        return total / (2 * len(self.regular_season_games))

    def _absorb_game_logs(self, result: GameResult) -> None:
        """Merge per-player game logs from a GameResult into season totals."""
        for pid, log in result.home_logs.items():
            if pid not in self.player_stats:
                self.player_stats[pid] = PlayerSeasonStats(player_id=pid)
            self.player_stats[pid].absorb(log)
        for pid, log in result.away_logs.items():
            if pid not in self.player_stats:
                self.player_stats[pid] = PlayerSeasonStats(player_id=pid)
            self.player_stats[pid].absorb(log)

    def play_regular_season(self) -> None:
        cfg = self.cfg

        # ── Pre-season injury rolls ───────────────────────────────────────────
        # Each rostered player rolls for injury once. If injured, they miss a
        # contiguous block of games distributed through the season.
        injury_remaining: dict[int, int] = {}  # player_id → games still to miss
        for team in self.teams:
            for player in team.roster:
                if player is None:
                    continue
                prob = min(0.80,
                    cfg.player_injury_base_prob
                    + (1.0 - player.durability) * cfg.player_injury_durability_scale
                    + player.fatigue * cfg.player_injury_fatigue_scale
                    + max(0, player.age - cfg.player_injury_age_threshold) * cfg.player_injury_age_scale
                )
                if random.random() < prob:
                    injury_remaining[player.player_id] = random.randint(
                        cfg.player_injury_games_min, cfg.player_injury_games_max
                    )

        for home, away in _generate_schedule(self.teams, self.cfg.games_per_pair):
            # Determine which players are out for this game
            out_home = frozenset(
                p.player_id for p in home.roster
                if p is not None and injury_remaining.get(p.player_id, 0) > 0
            )
            out_away = frozenset(
                p.player_id for p in away.roster
                if p is not None and injury_remaining.get(p.player_id, 0) > 0
            )
            # Decrement counters and record misses in season stats
            for pid in out_home | out_away:
                injury_remaining[pid] -= 1
                if pid not in self.player_stats:
                    self.player_stats[pid] = PlayerSeasonStats(player_id=pid)
                self.player_stats[pid].games_missed += 1

            result = play_game(home, away, cfg, league_meta=self.league_meta,
                               out_home=out_home, out_away=out_away)
            self.regular_season_games.append(result)
            self._record(result)
            self._absorb_game_logs(result)

        self.regular_season_standings = self.standings()
        # Snapshot records before playoffs inflate the counts
        self._reg_wins = dict(self._wins)
        self._reg_losses = dict(self._losses)
        self._compute_regular_season_awards()

    def play_playoffs(self) -> None:
        bracket = self.regular_season_standings[:self.playoff_teams]

        while len(bracket) > 1:
            round_series: list[PlayoffSeries] = []
            next_bracket: list[Team] = []
            for i in range(len(bracket) // 2):
                s1 = bracket[i]
                s2 = bracket[len(bracket) - 1 - i]
                winner, games = play_series(
                    s1, s2, self.cfg,
                    home_advantage=None,   # computed per-game from home team's popularity
                    league_meta=self.league_meta,
                    seed_bonus=self.cfg.playoff_seed_pscore_bonus,
                )
                for g in games:
                    self._record(g)
                round_series.append(PlayoffSeries(s1, s2, winner, games))
                next_bracket.append(winner)
            self.playoff_rounds.append(round_series)
            bracket = next_bracket

        self.champion = bracket[0]
        self.champion.championships += 1
        self._compute_finals_mvp()

    def _compute_regular_season_awards(self) -> None:
        """Compute MVP, OPOY, and DPOY from the regular-season player pool.

        MVP: restricted to playoff teams; scored 60% PPG + 40% defensive value,
             weighted by regular-season win%. Best two-way performer on a good team.

        OPOY: all players eligible (including MVP); pure scoring champ — highest PPG
              regardless of team quality. No win% weighting.

        DPOY: all players except OPOY winner eligible (including MVP); pure defensive
              champ — lowest def_rtg (pts allowed per 100 poss defended). No win%
              weighting. Falls back to player attribute if no game-log data.
        """
        pool = [
            (p, t)
            for t in self.teams
            for p in t.roster
            if p is not None
        ]
        if not pool:
            return

        playoff_set = set(self.regular_season_standings[:self.playoff_teams])

        def _ppg(p: Player) -> float:
            s = self.player_stats.get(p.player_id)
            return s.ppg if s else 0.0

        def _def_score(p: Player) -> float:
            """Defensive value: positive = better than league average (110 baseline)."""
            s = self.player_stats.get(p.player_id)
            if s and s.poss_defended > 0:
                return -(s.def_rtg - 110.0)
            return -p.drtg_contrib  # fallback: attribute already on same scale

        def _raw_def_rtg(p: Player) -> float:
            """Raw def_rtg for DPOY sorting (lower = better)."""
            s = self.player_stats.get(p.player_id)
            return s.def_rtg if (s and s.poss_defended > 0) else (110.0 + p.drtg_contrib)

        # MVP: playoff teams only; 60/40 two-way formula weighted by win%
        mvp_pool = [(p, t) for p, t in pool if t in playoff_set]
        if mvp_pool:
            self.mvp, self.mvp_team = max(
                mvp_pool,
                key=lambda pt: (
                    (0.60 * _ppg(pt[0]) + 0.40 * _def_score(pt[0]))
                    * (0.70 + 0.60 * self.reg_win_pct(pt[1]))
                ),
            )

        # OPOY: all players, pure PPG — scoring champ, independent of team success
        if pool:
            self.opoy, self.opoy_team = max(pool, key=lambda pt: _ppg(pt[0]))

        # DPOY: all players except OPOY winner, pure def_rtg — OPOY and DPOY
        #       cannot be the same player, but MVP can win either or both
        dpoy_pool = [(p, t) for p, t in pool if p is not self.opoy]
        if dpoy_pool:
            self.dpoy, self.dpoy_team = min(dpoy_pool, key=lambda pt: _raw_def_rtg(pt[0]))

    def compute_mip(self, prior_stats: dict) -> None:
        """Most Improved Player: biggest positive delta in the 60/40 two-way score.

        Same formula as the MVP numerator — 60% PPG + 40% defensive value — applied
        to the change from the prior season. All slots eligible. Current MVP excluded
        so the award goes to a genuine breakout story rather than the dominant player
        who was already dominant.

        Requires stats in both seasons; minimum 15 games each.
        Only fires when a prior season exists (season 2+).
        """
        MIN_GAMES = 15
        if not prior_stats:
            return

        def _two_way(ps: "PlayerSeasonStats") -> float:
            """60/40 composite — same numerator as MVP formula."""
            def_val = -(ps.def_rtg - 110.0) if ps.poss_defended > 0 else 0.0
            return 0.60 * ps.ppg + 0.40 * def_val

        best_p    = None
        best_t    = None
        best_delta = -999.0
        best_ppg_delta = 0.0

        for t in self.teams:
            for p in t.roster:
                if p is None or p is self.mvp:
                    continue
                curr = self.player_stats.get(p.player_id)
                prev = prior_stats.get(p.player_id)
                if curr is None or prev is None:
                    continue
                if curr.games < MIN_GAMES or prev.games < MIN_GAMES:
                    continue
                delta = _two_way(curr) - _two_way(prev)
                if delta > best_delta:
                    best_delta     = delta
                    best_ppg_delta = curr.ppg - prev.ppg
                    best_p = p
                    best_t = t

        if best_p is not None and best_delta > 0:
            self.mip           = best_p
            self.mip_team      = best_t
            self.mip_delta     = round(best_delta, 2)
            self.mip_ppg_delta = round(best_ppg_delta, 1)

    def _compute_finals_mvp(self) -> None:
        """Compute Finals MVP from championship series game logs.

        Uses the same 60/40 two-way formula as regular-season MVP (PPG + defensive
        value), applied to stats from the Finals games only. No win% weighting —
        all champion players won the same series.
        """
        if not self.champion or not self.playoff_rounds:
            return

        finals_series = self.playoff_rounds[-1][0]

        # Aggregate stats from each Finals game for champion's players
        pts:      dict[int, int] = {}
        pd:       dict[int, int] = {}   # poss_defended
        pa:       dict[int, int] = {}   # pts_allowed
        gp:       dict[int, int] = {}   # games played

        for game in finals_series.games:
            logs = game.home_logs if game.home is self.champion else game.away_logs
            for pid, log in logs.items():
                if pid == _BENCH_ID:
                    continue
                pts[pid] = pts.get(pid, 0) + log.points
                pd[pid]  = pd.get(pid, 0)  + log.poss_defended
                pa[pid]  = pa.get(pid, 0)  + log.pts_allowed
                gp[pid]  = gp.get(pid, 0)  + 1

        pid_to_player = {p.player_id: p for p in self.champion.roster if p is not None}

        def _fmvp_score(pid: int) -> float:
            games = gp.get(pid, 0)
            if games == 0:
                return -999.0
            ppg = pts.get(pid, 0) / games
            poss = pd.get(pid, 0)
            if poss > 0:
                def_score = -(pa.get(pid, 0) / poss * 100 - 110.0)
            else:
                p = pid_to_player[pid]
                def_score = -p.drtg_contrib
            return 0.60 * ppg + 0.40 * def_score

        candidates = [pid for pid in pts if pid in pid_to_player and gp.get(pid, 0) > 0]
        if candidates:
            best_pid = max(candidates, key=_fmvp_score)
            self.finals_mvp = pid_to_player[best_pid]
            games = gp.get(best_pid, 1)
            self.finals_mvp_ppg  = round(pts.get(best_pid, 0) / games, 1)
            poss = pd.get(best_pid, 0)
            self.finals_mvp_drtg = round(
                pa.get(best_pid, 0) / poss * 100 if poss > 0 else 110.0 + self.finals_mvp.drtg_contrib, 1
            )

    def run(self) -> None:
        self.play_regular_season()
        self.play_playoffs()
