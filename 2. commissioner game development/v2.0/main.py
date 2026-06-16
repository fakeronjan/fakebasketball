import argparse
import random

from config import Config
from league import League
from season import Season, _round_name


# ── Formatting helpers ────────────────────────────────────────────────────────

def _bar(width: int = 54) -> str:
    return "─" * width


def print_standings(season: Season) -> None:
    print(f"\n  {'#':<4} {'Team':<24} {'W':>4} {'L':>4}  {'Pct':>5}  {'Net':>6}")
    print(f"  {_bar(52)}")
    for rank, team in enumerate(season.regular_season_standings, 1):
        marker = "*" if rank <= season.playoff_teams else " "
        print(
            f"  {marker}{rank:<3} {team.name:<24} "
            f"{season.reg_wins(team):>4} {season.reg_losses(team):>4}  "
            f"{season.reg_win_pct(team):.3f}  {team.net_rating():>+6.1f}"
        )


def print_playoffs(season: Season) -> None:
    bracket_sizes = [season.playoff_teams // (2 ** r) for r in range(len(season.playoff_rounds))]
    for r_idx, (round_series, size) in enumerate(zip(season.playoff_rounds, bracket_sizes)):
        print(f"\n  {_round_name(size)}:")
        for series in round_series:
            loser = series.seed2 if series.winner is series.seed1 else series.seed1
            winner_wins = series.seed1_wins if series.winner is series.seed1 else series.seed2_wins
            loser_wins = series.seed2_wins if series.winner is series.seed1 else series.seed1_wins
            print(
                f"    {series.winner.name} def. {loser.name}"
                f"  ({winner_wins}–{loser_wins})"
            )


def print_season(season: Season, relocations: list[tuple[int, str, str]]) -> None:
    print(f"\n{'═' * 62}")
    print(f"  SEASON {season.number}")
    print(f"{'═' * 62}")
    print("\nRegular Season Standings  (* = playoff)")
    print_standings(season)
    print("\nPlayoffs")
    print_playoffs(season)
    print(f"\n  ★  CHAMPION: {season.champion.name}")

    # Show any relocations/expansions that happened after this season
    moves = [(o, n) for (s, o, n, *_) in relocations if s == season.number]
    if moves:
        print(f"\n  Offseason moves:")
        for old, new in moves:
            print(f"    ↪  {old}  →  {new}")


def _runner_up(season: Season):
    finals = season.playoff_rounds[-1][0]
    return finals.seed2 if finals.winner is finals.seed1 else finals.seed1


def _playoff_seed(season: Season, team) -> int:
    return season.regular_season_standings.index(team) + 1


def _finals_score(season: Season) -> str:
    """Return the finals series result as 'W-L' from the champion's perspective."""
    finals = season.playoff_rounds[-1][0]
    cw = finals.seed1_wins if finals.winner is finals.seed1 else finals.seed2_wins
    lw = finals.seed2_wins if finals.winner is finals.seed1 else finals.seed1_wins
    return f"{cw}-{lw}"


def print_league_summary_table(league: League) -> None:
    W = 26  # fixed cell width for team+stat cells (city + nickname + record/ppg)
    FW = 5  # finals score cell width

    # Column headers
    h_sn    = f"{'S':>3}"
    h_rsl   = f"{'RS LEADER':<{W}}"
    h_champ = f"{'CHAMP':<{W}}"
    h_fin   = f"{'FIN':^{FW}}"
    h_rs2   = f"{'RS 2ND':<{W}}"
    h_final = f"{'FINALIST':<{W}}"
    h_hppg  = f"{'HI PPG':<{W}}"
    h_lppg  = f"{'LO PPG':<{W}}"
    h_worst = f"{'WORST':<{W}}"
    h_avg   = f"{'AVG':>6}"
    h_moves = "  MOVES"

    header = f"{h_sn}  {h_rsl}{h_champ}{h_fin}  {h_rs2}{h_final}{h_hppg}{h_lppg}{h_worst}{h_avg}{h_moves}"
    divider = "─" * len(header)

    print(f"\n\n{'═' * len(header)}")
    print(f"  {len(league.seasons)}-SEASON SUMMARY")
    print(f"{'═' * len(header)}")
    print(f"\n{header}")
    print(divider)

    prev_champ = None
    for s in league.seasons:
        stand = s.regular_season_standings

        rs_leader  = stand[0]
        rs_2nd     = stand[1]
        champ      = s.champion
        finalist   = _runner_up(s)
        worst      = stand[-1]

        ppg        = {t: s.team_ppg(t) for t in s.teams}
        hi_t       = max(ppg, key=ppg.__getitem__)
        lo_t       = min(ppg, key=ppg.__getitem__)
        avg        = s.league_avg_ppg()
        fin_score  = _finals_score(s)
        repeat     = "★" if champ is prev_champ else " "

        # Full name for a team as of this season
        nm = lambda t: t.franchise_at(s.number).name

        # Relocations after this season — show full city+name
        moves = [(o, n) for (sn, o, n, *_) in league.relocation_log if sn == s.number]
        moves_str = "  " + "  |  ".join(
            f"{o}  →  {n}" for o, n in moves
        ) if moves else ""

        def tc(name: str, w: int, l: int) -> str:
            return f"{name} {w}-{l}"[:W].ljust(W)

        def tp(name: str, v: float) -> str:
            return f"{name} {v:.1f}"[:W].ljust(W)

        champ_seed    = _playoff_seed(s, champ)
        finalist_seed = _playoff_seed(s, finalist)
        champ_cell    = f"{repeat}{nm(champ)}({champ_seed})"[:W].ljust(W)
        finalist_cell = f"{nm(finalist)}({finalist_seed})"[:W].ljust(W)

        row = (
            f"{s.number:>3}  "
            f"{tc(nm(rs_leader), s.reg_wins(rs_leader),  s.reg_losses(rs_leader))}"
            f"{champ_cell}"
            f"{fin_score:^{FW}}  "
            f"{tc(nm(rs_2nd),    s.reg_wins(rs_2nd),    s.reg_losses(rs_2nd))}"
            f"{finalist_cell}"
            f"{tp(nm(hi_t), ppg[hi_t])}"
            f"{tp(nm(lo_t), ppg[lo_t])}"
            f"{tc(nm(worst),     s.reg_wins(worst),     s.reg_losses(worst))}"
            f"{avg:>6.1f}"
            f"{moves_str}"
        )
        print(row)
        prev_champ = champ

    print(divider)
    print(f"  ★ = repeat champion   FIN = finals series score   AVG = league pts/game")


def print_summary_table(league: League) -> None:
    seasons = league.seasons
    teams = sorted(league.teams, key=lambda t: t.team_id)

    col_w = 9
    header = f"  {'Team':<22}" + "".join(f"{'S' + str(s.number):^{col_w}}" for s in seasons)
    print(f"\n\n{'═' * len(header)}")
    print("  SEASON SUMMARY")
    print(f"{'═' * len(header)}")
    print(f"\n{header}")
    print(f"  {_bar(len(header) - 2)}")

    for team in teams:
        row = f"  {team.franchise_at(seasons[-1].number).name:<22}"
        for s in seasons:
            name_then = team.franchise_at(s.number).name
            w = s.reg_wins(team)
            l = s.reg_losses(team)
            if team is s.champion:
                indicator = "*"
            elif team is _runner_up(s):
                indicator = "+"
            else:
                indicator = " "
            # Flag seasons where team played under a different name
            changed = "~" if name_then != team.franchise_at(seasons[-1].number).name else ""
            cell = f"{w}-{l}{indicator}{changed}"
            row += f"{cell:^{col_w}}"
        print(row)

    print(f"\n  * = champion   + = runner-up   ~ = different name that season")


def print_history(league: League) -> None:
    print(f"\n\n{'═' * 62}")
    print("  LEAGUE HISTORY")
    print(f"{'═' * 62}")
    print(f"\n  {'Season':<8} {'Champion':<26} {'Net':>6}")
    print(f"  {_bar(42)}")
    for s in league.seasons:
        nm = s.champion.franchise_at(s.number).name
        print(f"  {s.number:<8} {nm:<26} {s.champion.net_rating():>+6.1f}")

    print(f"\n  All-Time Championships:")
    ranked = sorted(league.teams, key=lambda t: t.championships, reverse=True)
    for team in ranked:
        if team.championships > 0:
            bar = "█" * team.championships
            print(f"    {team.name:<26} {team.championships:>3}  {bar}")

    if league.relocation_log:
        print(f"\n  Franchise Moves:")
        for season_num, old, new, *_ in league.relocation_log:
            print(f"    After S{season_num}: {old}  →  {new}")


def print_cumulative_stats(league: League) -> None:
    seasons  = league.seasons
    teams    = league.teams
    n        = len(seasons)
    W        = 28

    print(f"\n\n{'═' * 62}")
    print("  ALL-TIME RECORDS")
    print(f"{'═' * 62}")

    # ── Championship counts ───────────────────────────────────────
    print(f"\n  Championships:")
    ranked = sorted(teams, key=lambda t: t.championships, reverse=True)
    for t in ranked:
        if t.championships > 0:
            print(f"    {t.name:<{W}} {t.championships:>3}  {'█' * t.championships}")

    # ── Finals appearances (wins + runner-up) ─────────────────────
    finals_apps  = {t: 0 for t in teams}
    finals_wins  = {t: 0 for t in teams}
    for s in seasons:
        finals_apps[s.champion]   += 1
        finals_apps[_runner_up(s)] += 1
        finals_wins[s.champion]   += 1
    print(f"\n  Finals Appearances (W-L):")
    for t in sorted(teams, key=lambda t: finals_apps[t], reverse=True):
        if finals_apps[t] > 0:
            w = finals_wins[t]
            l = finals_apps[t] - w
            print(f"    {t.name:<{W}} {finals_apps[t]:>3}  ({w}W–{l}L)")

    # ── Most regular season titles ────────────────────────────────
    rs_titles = {t: 0 for t in teams}
    for s in seasons:
        rs_titles[s.regular_season_standings[0]] += 1
    print(f"\n  Most Regular Season Titles (best record):")
    for t in sorted(teams, key=lambda t: rs_titles[t], reverse=True):
        if rs_titles[t] > 0:
            print(f"    {t.name:<{W}} {rs_titles[t]:>3}")

    # ── Championship streaks ──────────────────────────────────────
    # Collect all streaks of 2+
    streaks = []
    cur_team, cur_start, cur_len = None, None, 0
    for s in seasons:
        if s.champion is cur_team:
            cur_len += 1
        else:
            if cur_len >= 2:
                streaks.append((cur_len, cur_start, cur_start + cur_len - 1, cur_team))
            cur_team, cur_start, cur_len = s.champion, s.number, 1
    if cur_len >= 2:
        streaks.append((cur_len, cur_start, cur_start + cur_len - 1, cur_team))
    streaks.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    print(f"\n  Longest Championship Streaks:")
    if streaks:
        for length, start, end, team in streaks[:8]:
            print(f"    {team.franchise_at(start).name:<{W}} {length}  (S{start}–S{end})")
    else:
        print(f"    No team repeated as champion")

    # ── Championship droughts ─────────────────────────────────────
    champ_seasons = {t: [s.number for s in seasons if s.champion is t] for t in teams}

    # Longest gap ever for any team (including never-won teams)
    droughts = []  # (length, start, end, team)
    for team in teams:
        wins = champ_seasons[team]
        if not wins:
            droughts.append((n, 1, n, team))
            continue
        # Gap before first title
        if wins[0] > 1:
            droughts.append((wins[0] - 1, 1, wins[0] - 1, team))
        # Gaps between titles
        for i in range(len(wins) - 1):
            gap = wins[i+1] - wins[i] - 1
            if gap > 0:
                droughts.append((gap, wins[i] + 1, wins[i+1] - 1, team))
        # Current drought since last title
        if wins[-1] < n:
            droughts.append((n - wins[-1], wins[-1] + 1, n, team))
    droughts.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    print(f"\n  Longest Championship Droughts:")
    for length, start, end, team in droughts[:8]:
        label = "(never won)" if not champ_seasons[team] else f"(S{start}–S{end})"
        print(f"    {team.name:<{W}} {length:>3} seasons  {label}")

    # ── Never won ─────────────────────────────────────────────────
    never_won = [t for t in teams if not champ_seasons[t]]
    if never_won:
        print(f"\n  Teams Without a Championship:")
        for t in sorted(never_won, key=lambda t: t.team_id):
            print(f"    {t.name}")
    else:
        print(f"\n  Every team won at least one championship.")

    # ── Best / worst single season records ───────────────────────
    best  = (0,  0, None, 0)   # (wins, season_num, team, losses)
    worst = (999, 0, None, 0)
    for s in seasons:
        for team in s.teams:
            w, l = s.reg_wins(team), s.reg_losses(team)
            if w > best[0]:
                best  = (w, s.number, team, l)
            if w < worst[0]:
                worst = (w, s.number, team, l)
    bname = best[2].franchise_at(best[1]).name
    wname = worst[2].franchise_at(worst[1]).name
    print(f"\n  Best Single Season:   {bname} — {best[0]}-{best[3]} (S{best[1]})")
    print(f"  Worst Single Season:  {wname} — {worst[0]}-{worst[3]} (S{worst[1]})")

    # ── Finals competitiveness ────────────────────────────────────
    series_counts = {}
    for s in seasons:
        g = len(s.playoff_rounds[-1][0].games)
        series_counts[g] = series_counts.get(g, 0) + 1
    print(f"\n  Finals by Series Length:")
    for g in sorted(series_counts):
        label = "sweep (4-0)" if g == 4 else f"games      "
        pct = series_counts[g] / n * 100
        print(f"    {g} {label}  {series_counts[g]:>3}x  ({pct:.0f}%)")

    # ── Franchise moves summary ───────────────────────────────────
    if league.relocation_log:
        print(f"\n  Franchise Moves ({len(league.relocation_log)} total):")
        for season_num, old, new, *_ in league.relocation_log:
            print(f"    After S{season_num:<4} {old}  →  {new}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ronjan Basketball League Simulator")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible results")
    parser.add_argument("--seasons", type=int, default=50,
                        help="Number of seasons to simulate (default: 50)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        print(f"  [seed: {args.seed}]")

    cfg = Config(num_seasons=args.seasons)

    league = League(cfg)
    league.simulate()

    print_league_summary_table(league)
    print_history(league)
    print_cumulative_stats(league)


if __name__ == "__main__":
    main()
