"""Generate index.html — a self-contained website for the Ronjan Basketball League simulation."""

import random
from html import escape

from config import Config
from league import League
from season import Season, _round_name


SEED = 19
NUM_SEASONS = 100


# ── helpers ──────────────────────────────────────────────────────────────────

def _runner_up(season: Season):
    finals = season.playoff_rounds[-1][0]
    return finals.seed2 if finals.winner is finals.seed1 else finals.seed1


def _playoff_seed(season: Season, team) -> int:
    return season.regular_season_standings.index(team) + 1


def _finals_score(season: Season) -> str:
    finals = season.playoff_rounds[-1][0]
    cw = finals.seed1_wins if finals.winner is finals.seed1 else finals.seed2_wins
    lw = finals.seed2_wins if finals.winner is finals.seed1 else finals.seed1_wins
    return f"{cw}–{lw}"


def nm(team, season_num: int) -> str:
    return escape(team.franchise_at(season_num).name)


# ── data extraction ───────────────────────────────────────────────────────────

def build_season_rows(league: League) -> list[dict]:
    from collections import defaultdict
    rows = []
    prev_champ = None
    champ_titles: dict[str, int] = defaultdict(int)
    finals_apps:  dict[str, int] = defaultdict(int)
    rs_titles:    dict[str, int] = defaultdict(int)
    last_place:   dict[str, int] = defaultdict(int)

    for s in league.seasons:
        stand = s.regular_season_standings
        champ = s.champion
        finalist = _runner_up(s)
        rs_leader = stand[0]
        rs_2nd = stand[1]
        repeat = champ is prev_champ

        c_name = nm(champ, s.number)
        f_name = nm(finalist, s.number)

        # Cumulative counts — increment first so this season is included
        champ_titles[c_name] += 1
        finals_apps[c_name]  += 1
        finals_apps[f_name]  += 1
        rs_titles[nm(rs_leader, s.number)] += 1
        last_place[nm(stand[-1], s.number)] += 1

        # Clinching game score — champion score first
        clincher = s.playoff_rounds[-1][0].games[-1]
        clinch_str = (
            f"{clincher.home_score}–{clincher.away_score}"
            if clincher.home is champ
            else f"{clincher.away_score}–{clincher.home_score}"
        )

        # Points scored and allowed per game across all games (reg season + playoffs)
        def pts(team):
            scored = allowed = count = 0
            all_games = list(s.regular_season_games)
            for rnd in s.playoff_rounds:
                for series in rnd:
                    all_games.extend(series.games)
            for g in all_games:
                if g.home is team:
                    scored += g.home_score; allowed += g.away_score; count += 1
                elif g.away is team:
                    scored += g.away_score; allowed += g.home_score; count += 1
            return round(scored / count, 1), round(allowed / count, 1)

        # Regular season points scored and allowed per game
        def rs_pts(team):
            scored = allowed = count = 0
            for g in s.regular_season_games:
                if g.home is team:
                    scored += g.home_score; allowed += g.away_score; count += 1
                elif g.away is team:
                    scored += g.away_score; allowed += g.home_score; count += 1
            return (round(scored / count, 1), round(allowed / count, 1)) if count else (0, 0)

        last = stand[-1]
        rows.append({
            "season": s.number,
            "meta": s.league_meta,
            "meta_shock": s.meta_shock,
            "avg_ppg": s.league_avg_ppg(),
            "champ": c_name,
            "champ_seed": _playoff_seed(s, champ),
            "champ_titles": champ_titles[c_name],
            "champ_finals": finals_apps[c_name],
            "champ_pts": pts(champ),
            "champ_w": s.wins(champ),
            "champ_l": s.losses(champ),
            "repeat": repeat,
            "finalist": f_name,
            "finalist_seed": _playoff_seed(s, finalist),
            "finalist_finals": finals_apps[f_name],
            "finalist_pts": pts(finalist),
            "finalist_w": s.wins(finalist),
            "finalist_l": s.losses(finalist),
            "fin": _finals_score(s),
            "clinch": clinch_str,
            "rs_leader": nm(rs_leader, s.number),
            "rs_leader_w": s.reg_wins(rs_leader),
            "rs_leader_l": s.reg_losses(rs_leader),
            "rs_leader_pts": rs_pts(rs_leader),
            "rs_leader_titles": rs_titles[nm(rs_leader, s.number)],
            "last": nm(last, s.number),
            "last_w": s.reg_wins(last),
            "last_l": s.reg_losses(last),
            "last_pts": rs_pts(last),
            "last_place_count": last_place[nm(last, s.number)],
            "team_count": len(s.teams),
            "league_pop": getattr(s, "_league_popularity", None),
        })
        prev_champ = champ
    return rows


def build_alltime(league: League) -> dict:
    from collections import defaultdict
    seasons = league.seasons
    teams = league.teams
    n = len(seasons)

    # All stats credited to the franchise name held AT THE TIME of the event.
    # If New York Empires relocates, their past titles stay with "New York Empires".
    # A new team that later moves to New York starts its own tally.

    champ_seasons_by_name:  dict[str, list[int]] = defaultdict(list)
    finals_seasons_by_name: dict[str, list[int]] = defaultdict(list)
    finals_wins_by_name:    dict[str, int] = defaultdict(int)
    finals_apps_by_name:    dict[str, int] = defaultdict(int)
    playoff_seasons_by_name: dict[str, set] = defaultdict(set)
    rs_by_name:             dict[str, int] = defaultdict(int)

    for s in seasons:
        c_name = s.champion.franchise_at(s.number).name
        r_name = _runner_up(s).franchise_at(s.number).name
        rs_name = s.regular_season_standings[0].franchise_at(s.number).name
        champ_seasons_by_name[c_name].append(s.number)
        finals_seasons_by_name[c_name].append(s.number)
        finals_seasons_by_name[r_name].append(s.number)
        finals_wins_by_name[c_name] += 1
        finals_apps_by_name[c_name] += 1
        finals_apps_by_name[r_name] += 1
        rs_by_name[rs_name] += 1
        for rnd in s.playoff_rounds:
            for sr in rnd:
                for t in (sr.seed1, sr.seed2):
                    playoff_seasons_by_name[t.franchise_at(s.number).name].add(s.number)

    champ_count = {name: len(wins) for name, wins in champ_seasons_by_name.items()}

    # Active season ranges for each franchise name
    # (a name can appear for multiple teams in different eras)
    franchise_ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for team in teams:
        hist = team.franchise_history
        for i, (start, franchise) in enumerate(hist):
            end = hist[i + 1][0] - 1 if i + 1 < len(hist) else n
            franchise_ranges[franchise.name].append((start, end))

    # Seasons each franchise name was active (sum across all eras)
    seasons_active: dict[str, int] = {}
    for fname, ranges in franchise_ranges.items():
        seasons_active[fname] = sum(end - start + 1 for start, end in ranges)

    championships = sorted(
        [(name, c, seasons_active.get(name, 0)) for name, c in champ_count.items()],
        key=lambda x: -x[1],
    )
    finals_list = sorted(
        [(name, finals_apps_by_name[name], finals_wins_by_name[name],
          finals_apps_by_name[name] - finals_wins_by_name[name],
          seasons_active.get(name, 0))
         for name in finals_apps_by_name],
        key=lambda x: -x[1],
    )
    rs_list = sorted(
        [(name, c, seasons_active.get(name, 0)) for name, c in rs_by_name.items()],
        key=lambda x: -x[1],
    )

    # Streaks: consecutive seasons won under the same franchise name
    streaks = []
    cur_name, cur_start, cur_len = None, None, 0
    for s in seasons:
        name = s.champion.franchise_at(s.number).name
        if name == cur_name:
            cur_len += 1
        else:
            if cur_len >= 2:
                streaks.append((cur_len, cur_start, cur_start + cur_len - 1, cur_name))
            cur_name, cur_start, cur_len = name, s.number, 1
    if cur_len >= 2:
        streaks.append((cur_len, cur_start, cur_start + cur_len - 1, cur_name))
    streaks.sort(reverse=True)

    # Droughts: gaps within each franchise name's active existence
    droughts = []
    for fname, ranges in franchise_ranges.items():
        # Merge active ranges in case the same city name appeared in multiple eras
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append([start, end])

        wins = sorted(champ_seasons_by_name.get(fname, []))

        for r_start, r_end in merged:
            range_wins = [w for w in wins if r_start <= w <= r_end]
            never = not range_wins
            if never:
                droughts.append((r_end - r_start + 1, r_start, r_end, fname, True))
            else:
                if range_wins[0] > r_start:
                    droughts.append((range_wins[0] - r_start, r_start, range_wins[0] - 1, fname, False))
                for i in range(len(range_wins) - 1):
                    gap = range_wins[i + 1] - range_wins[i] - 1
                    if gap > 0:
                        droughts.append((gap, range_wins[i] + 1, range_wins[i + 1] - 1, fname, False))
                if range_wins[-1] < r_end:
                    droughts.append((r_end - range_wins[-1], range_wins[-1] + 1, r_end, fname, False))
    droughts.sort(reverse=True)

    # Playoff streaks and droughts by franchise name
    playoff_streaks  = []
    playoff_droughts = []
    champ_sns_all = {sn for sns in champ_seasons_by_name.values() for sn in sns}
    finals_sns_all = {sn for sns in finals_seasons_by_name.values() for sn in sns}

    for fname, ranges in franchise_ranges.items():
        p_sns = playoff_seasons_by_name.get(fname, set())
        c_sns = set(champ_seasons_by_name.get(fname, []))
        f_sns = set(finals_seasons_by_name.get(fname, []))

        for r_start, r_end in sorted(ranges):
            streak, drought = [], []
            for sn in range(r_start, r_end + 1):
                if sn in p_sns:
                    if drought:
                        if len(drought) >= 3:
                            playoff_droughts.append((len(drought), drought[0], drought[-1], fname))
                        drought = []
                    streak.append(sn)
                else:
                    if streak:
                        if len(streak) >= 3:
                            titles  = sum(1 for x in streak if x in c_sns)
                            finals  = sum(1 for x in streak if x in f_sns)
                            playoff_streaks.append((len(streak), streak[0], streak[-1], fname, titles, finals))
                        streak = []
                    drought.append(sn)
            if streak and len(streak) >= 3:
                titles = sum(1 for x in streak if x in c_sns)
                finals = sum(1 for x in streak if x in f_sns)
                playoff_streaks.append((len(streak), streak[0], streak[-1], fname, titles, finals))
            if drought and len(drought) >= 3:
                playoff_droughts.append((len(drought), drought[0], drought[-1], fname))

    playoff_streaks.sort(reverse=True)
    playoff_droughts.sort(reverse=True)

    # Series length counts by round — use maximum rounds seen across all seasons
    max_rounds = max(len(s.playoff_rounds) for s in seasons)
    round_names = [_round_name(2 ** (max_rounds - i)) for i in range(max_rounds)]
    series_counts_by_round = [{} for _ in range(max_rounds)]
    for s in seasons:
        for round_idx, round_series in enumerate(s.playoff_rounds):
            for series in round_series:
                g = len(series.games)
                series_counts_by_round[round_idx][g] = series_counts_by_round[round_idx].get(g, 0) + 1

    best_single = (0, 0, None, 0)
    worst_single = (999, 0, None, 0)

    # Best teams (by total win% incl. postseason) and worst (by reg season win%)
    team_season_records = []
    for s in seasons:
        champ_team = s.champion
        for team in s.teams:
            name = escape(team.franchise_at(s.number).name)
            # Regular season
            rw = s.reg_wins(team)
            rl = s.reg_losses(team)
            reg_ps = sum(g.home_score if g.home is team else g.away_score
                         for g in s.regular_season_games if g.home is team or g.away is team)
            reg_pa = sum(g.away_score if g.home is team else g.home_score
                         for g in s.regular_season_games if g.home is team or g.away is team)
            # Postseason
            post_games = [g for rnd in s.playoff_rounds for sr in rnd
                          for g in sr.games if g.home is team or g.away is team]
            pw = sum(1 for g in post_games if g.winner is team)
            pl = len(post_games) - pw
            post_ps = sum(g.home_score if g.home is team else g.away_score for g in post_games)
            post_pa = sum(g.away_score if g.home is team else g.home_score for g in post_games)

            total_w  = rw + pw
            total_l  = rl + pl
            total_g  = total_w + total_l
            total_ps = reg_ps + post_ps
            total_pa = reg_pa + post_pa
            total_pct = total_w / total_g if total_g > 0 else 0

            reg_g   = rw + rl
            reg_pct = rw / reg_g if reg_g > 0 else 0
            reg_margin = (reg_ps - reg_pa) / reg_g if reg_g > 0 else 0

            is_champ = team is champ_team

            team_season_records.append({
                "season": s.number, "name": name,
                "total_w": total_w, "total_l": total_l, "total_pct": total_pct,
                "total_ps": total_ps, "total_pa": total_pa,
                "total_margin": (total_ps - total_pa) / total_g if total_g > 0 else 0,
                "rw": rw, "rl": rl, "reg_pct": reg_pct,
                "reg_ps": reg_ps, "reg_pa": reg_pa, "reg_margin": reg_margin,
                "is_champ": is_champ,
            })

            if rw > best_single[0]:
                best_single = (rw, s.number, team, rl)
            if rw < worst_single[0]:
                worst_single = (rw, s.number, team, rl)

    best_teams  = sorted(team_season_records, key=lambda x: (-x["total_pct"], -x["total_w"]))[:10]
    worst_teams = sorted(team_season_records, key=lambda x: (x["reg_pct"], x["rw"]))[:10]

    return {
        "championships": [(escape(name), c, sa) for name, c, sa in championships],
        "finals": [(escape(name), apps, w, l, sa) for name, apps, w, l, sa in finals_list],
        "rs_titles": [(escape(name), c, sa) for name, c, sa in rs_list],
        "streaks": [(length, start, end, escape(name))
                    for length, start, end, name in streaks[:8]],
        "droughts": [(length, start, end, escape(fname), never)
                     for length, start, end, fname, never in droughts[:8]],
        "series_counts_by_round": series_counts_by_round,
        "series_round_names": round_names,
        "champ_seasons": {escape(name): sorted(sns) for name, sns in champ_seasons_by_name.items()},
        "playoff_streaks":  [(l, s, e, escape(nm), t, f) for l, s, e, nm, t, f in playoff_streaks[:10]],
        "playoff_droughts": [(l, s, e, escape(nm)) for l, s, e, nm in playoff_droughts[:10]],
        "best": (best_single[0], best_single[3], best_single[1], escape(best_single[2].franchise_at(best_single[1]).name)),
        "worst": (worst_single[0], worst_single[3], worst_single[1], escape(worst_single[2].franchise_at(worst_single[1]).name)),
        "best_teams": best_teams,
        "worst_teams": worst_teams,
        "relocations": [(sn, escape(o), escape(nn), ls, b2, pop) for sn, o, nn, ls, b2, pop in league.relocation_log],
        "total_relocations": len(league.relocation_log),
        "expansions": [(sn, escape(fname), is_sec) for sn, fname, is_sec in league.expansion_log],
        "total_expansions": len(league.expansion_log),
        "mergers": [(sn, escape(fname), is_sec) for sn, fname, is_sec in league.merger_log],
        "total_mergers": len(league.merger_log),
        "merger_waves": len({sn for sn, *_ in league.merger_log}),
        "n": n,
    }


def build_rivalries(league: League) -> dict:
    from collections import defaultdict

    # pair key is always alphabetically sorted so (A, B) == (B, A)
    playoff_data   = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})
    finals_data    = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})
    rs_data        = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})
    all_games_data = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})

    for s in league.seasons:
        # Regular season games
        for g in s.regular_season_games:
            n1 = g.home.franchise_at(s.number).name
            n2 = g.away.franchise_at(s.number).name
            winner_name = g.winner.franchise_at(s.number).name
            pair = tuple(sorted([n1, n2]))
            rs_data[pair]["total"] += 1
            rs_data[pair]["wins"][winner_name] += 1
            all_games_data[pair]["total"] += 1
            all_games_data[pair]["wins"][winner_name] += 1

        # Playoff series + individual games
        num_rounds = len(s.playoff_rounds)
        for round_idx, round_series in enumerate(s.playoff_rounds):
            is_finals = round_idx == num_rounds - 1
            for series in round_series:
                n1 = series.seed1.franchise_at(s.number).name
                n2 = series.seed2.franchise_at(s.number).name
                winner = series.winner.franchise_at(s.number).name
                pair = tuple(sorted([n1, n2]))

                playoff_data[pair]["total"] += 1
                playoff_data[pair]["wins"][winner] += 1
                if is_finals:
                    finals_data[pair]["total"] += 1
                    finals_data[pair]["wins"][winner] += 1

                for g in series.games:
                    gn1 = g.home.franchise_at(s.number).name
                    gn2 = g.away.franchise_at(s.number).name
                    gw = g.winner.franchise_at(s.number).name
                    gpair = tuple(sorted([gn1, gn2]))
                    all_games_data[gpair]["total"] += 1
                    all_games_data[gpair]["wins"][gw] += 1

    def _format(pair, data):
        a, b = pair
        wa = data["wins"].get(a, 0)
        wb = data["wins"].get(b, 0)
        total = data["total"]
        # Put the leader first
        if wb > wa:
            a, b, wa, wb = b, a, wb, wa
        if wa > wb:
            record = f"{escape(a)} leads {wa}–{wb}"
        else:
            record = f"Tied {wa}–{wb}"
        return (escape(a), escape(b), total, record)

    playoff_list   = sorted(playoff_data.items(),   key=lambda x: -x[1]["total"])
    finals_list    = sorted(finals_data.items(),    key=lambda x: -x[1]["total"])
    rs_list        = sorted(rs_data.items(),        key=lambda x: -x[1]["total"])
    all_games_list = sorted(all_games_data.items(), key=lambda x: -x[1]["total"])

    return {
        "playoff":    [_format(p, d) for p, d in playoff_list[:15]],
        "finals":     [_format(p, d) for p, d in finals_list[:10]],
        "rs":         [_format(p, d) for p, d in rs_list[:15]],
        "all_games":  [_format(p, d) for p, d in all_games_list[:15]],
    }


def build_popularity_rows(league: League) -> list[dict]:
    rows = []
    for s in league.seasons:
        pop = getattr(s, "_popularity", {})
        if not pop:
            continue

        finalist = s.playoff_rounds[-1][0]
        runner_up = finalist.seed2 if finalist.winner is finalist.seed1 else finalist.seed1
        playoff_teams = {t for rnd in s.playoff_rounds for sr in rnd for t in (sr.seed1, sr.seed2)}
        standings = s.regular_season_standings

        def _label(team):
            if team is s.champion:
                return "Champion"
            if team is runner_up:
                return "Finals"
            if team in playoff_teams:
                return "Playoffs"
            if team is standings[-1]:
                return "Last Place"
            if team in set(standings[-2:]):
                return "Bottom 2"
            return ""

        top5 = sorted(pop.items(), key=lambda x: -x[1])[:5]
        rows.append({
            "season": s.number,
            "top5": [(t.franchise_at(s.number).name, v, _label(t)) for t, v in top5],
        })
    return rows


def build_team_histories(league: League) -> list:
    from collections import defaultdict
    from season import _round_labels

    # Group (season, team) pairs by the franchise name active that season.
    # Relocations split histories; a team returning to a city merges entries.
    # Expansion teams are skipped for seasons before they joined the league.
    franchise_seasons: dict[str, list] = defaultdict(list)
    for team in league.teams:
        for s in league.seasons:
            if s.number < team.joined_season:
                continue
            fname = team.franchise_at(s.number).name
            franchise_seasons[fname].append((s, team))

    histories = []
    for fname in sorted(franchise_seasons.keys()):
        pairs = sorted(franchise_seasons[fname], key=lambda x: x[0].number)
        seasons_data = []

        for s, team in pairs:
            rw, rl = s.reg_wins(team), s.reg_losses(team)
            reg_games = [g for g in s.regular_season_games if g.home is team or g.away is team]
            reg_g = len(reg_games)
            ps_g = sum(g.home_score if g.home is team else g.away_score for g in reg_games) / reg_g if reg_g else 0
            pa_g = sum(g.away_score if g.home is team else g.home_score for g in reg_games) / reg_g if reg_g else 0

            # Win% rank among all teams this season
            all_pcts = sorted([s.reg_win_pct(t) for t in s.teams], reverse=True)
            win_rank = all_pcts.index(s.reg_win_pct(team)) + 1

            # Popularity rank
            pop_data = getattr(s, "_popularity", {})
            pop = pop_data.get(team)
            if pop_data:
                all_pops = sorted(pop_data.values(), reverse=True)
                pop_rank = all_pops.index(pop) + 1 if pop is not None else None
            else:
                pop_rank = None

            # Playoff info — per-round matchups
            playoff_teams = {t for rnd in s.playoff_rounds for sr in rnd for t in (sr.seed1, sr.seed2)}
            seed = None
            matchups = []

            if team in playoff_teams:
                seed = s.regular_season_standings.index(team) + 1
                labels = _round_labels(len(s.playoff_rounds))
                for round_idx, rnd in enumerate(s.playoff_rounds):
                    for sr in rnd:
                        if sr.seed1 is team or sr.seed2 is team:
                            opp = sr.seed2 if sr.seed1 is team else sr.seed1
                            opp_name = opp.franchise_at(s.number).name
                            pg = [g for g in sr.games if g.home is team or g.away is team]
                            tw = sum(1 for g in pg if g.winner is team)
                            tl = len(pg) - tw
                            won = sr.winner is team
                            label = labels[round_idx] if round_idx < len(labels) else f"R{round_idx+1}"
                            matchups.append({
                                "label": label,
                                "won": won,
                                "tw": tw, "tl": tl,
                                "opp": escape(opp_name),
                            })

            seasons_data.append({
                "_sort": s.number,
                "season": s.number,
                "rw": rw, "rl": rl,
                "ps_g": ps_g, "pa_g": pa_g,
                "margin": ps_g - pa_g,
                "win_rank": win_rank,
                "seed": seed,
                "matchups": matchups,
                "pop": pop,
                "pop_rank": pop_rank,
            })

        # Inject expansion entry markers
        for sn, fname_log, is_secondary in league.expansion_log:
            if fname_log == fname:
                seasons_data.append({
                    "_sort": sn + 0.3,
                    "expansion": True,
                    "entry_type": "expansion",
                    "is_secondary": is_secondary,
                    "after_season": sn,
                })

        # Inject merger entry markers
        for sn, fname_log, is_secondary in league.merger_log:
            if fname_log == fname:
                seasons_data.append({
                    "_sort": sn + 0.3,
                    "expansion": True,
                    "entry_type": "merger",
                    "is_secondary": is_secondary,
                    "after_season": sn,
                })

        # Inject relocation marker rows from the relocation log
        for sn, old, new, *_ in league.relocation_log:
            if old == fname:
                seasons_data.append({
                    "_sort": sn + 0.5,
                    "relocation": True,
                    "direction": "away",
                    "dest": escape(new),
                    "after_season": sn,
                })
            if new == fname:
                seasons_data.append({
                    "_sort": sn + 0.5,
                    "relocation": True,
                    "direction": "from",
                    "dest": escape(old),
                    "after_season": sn,
                })

        seasons_data.sort(key=lambda e: e["_sort"])

        histories.append({
            "current_name": escape(fname),
            "seasons": seasons_data,
        })

    return histories


def build_seed_grid(league: League) -> dict:
    """Build a seed vs seed win/loss grid across all playoff series."""
    from collections import defaultdict
    # wins[row_seed][col_seed] = wins by row_seed over col_seed
    wins  = defaultdict(lambda: defaultdict(int))
    total = defaultdict(lambda: defaultdict(int))

    n_seeds = max(s.playoff_teams for s in league.seasons)
    for s in league.seasons:
        seed_of = {t: i + 1 for i, t in enumerate(s.regular_season_standings[:n_seeds])}
        for rnd in s.playoff_rounds:
            for series in rnd:
                t1, t2 = series.seed1, series.seed2
                if t1 not in seed_of or t2 not in seed_of:
                    continue
                s1, s2 = seed_of[t1], seed_of[t2]
                winner_seed = seed_of[series.winner]
                loser_seed  = s2 if winner_seed == s1 else s1
                wins[winner_seed][loser_seed]  += 1
                total[s1][s2] += 1
                total[s2][s1] += 1

    return {"wins": wins, "total": total, "n": n_seeds}


# ── HTML rendering ────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #0c0d10;
  --bg2: #13141a;
  --bg3: #1c1e27;
  --border: #2a2d3a;
  --gold: #2ab5a5;
  --gold2: #67dfd3;
  --text: #e8eaf0;
  --muted: #8890a8;
  --red: #ff6b6b;
  --green: #69db7c;
  --blue: #74c0fc;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 15px;
  line-height: 1.6;
}
a { color: var(--gold); text-decoration: none; }
a:hover { color: var(--gold2); text-decoration: underline; }

/* ── Nav ── */
nav {
  position: sticky; top: 0; z-index: 100;
  background: rgba(12,13,16,0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  display: flex; gap: 2rem; align-items: center;
  height: 52px;
}
nav .brand { font-weight: 700; font-size: 1rem; color: var(--gold); letter-spacing: 0.05em; }
nav a { font-size: 0.85rem; color: var(--muted); transition: color 0.15s; }
nav a:hover { color: var(--text); text-decoration: none; }

/* ── Hero ── */
.hero {
  background: linear-gradient(135deg, #0c0d10 0%, #13141a 50%, #0f1118 100%);
  border-bottom: 1px solid var(--border);
  padding: 5rem 2rem 4rem;
  text-align: center;
}
.hero h1 {
  font-size: clamp(2.2rem, 5vw, 3.8rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--gold) 0%, var(--gold2) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 0.75rem;
}
.hero .subtitle {
  font-size: 1.1rem;
  color: var(--muted);
  max-width: 600px;
  margin: 0 auto 1.5rem;
}
.hero .badge {
  display: inline-block;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.3rem 1rem;
  font-size: 0.8rem;
  color: var(--muted);
  font-family: 'SF Mono', 'Fira Code', monospace;
}
.hero .badge span { color: var(--gold); }

/* ── Sections ── */
section {
  max-width: 1400px;
  margin: 0 auto;
  padding: 4rem 2rem;
}
section.full-bleed {
  max-width: none;
  padding: 4rem 2rem;
}
section.alt { background: var(--bg2); max-width: none; }
section.alt > .inner { max-width: 1400px; margin: 0 auto; }
.section-title {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--gold);
  letter-spacing: -0.01em;
  margin-bottom: 0.5rem;
}
.section-sub {
  color: var(--muted);
  margin-bottom: 2.5rem;
  font-size: 0.95rem;
}

/* ── Story ── */
.story-text {
  max-width: 780px;
  font-size: 1rem;
  line-height: 1.8;
  color: #c8cadb;
}
.story-text p { margin-bottom: 1.25rem; }
.story-text strong { color: var(--text); }

/* ── Code cards ── */
.code-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.25rem;
  margin-top: 0.5rem;
}
.code-card {
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.5rem;
}
.code-card .filename {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
  color: var(--gold);
  margin-bottom: 0.5rem;
  letter-spacing: 0.05em;
}
.code-card h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; }
.code-card p { font-size: 0.875rem; color: var(--muted); line-height: 1.6; }
.code-card ul { font-size: 0.875rem; color: var(--muted); padding-left: 1.2rem; line-height: 1.7; }

/* ── Stats grid ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 3rem;
}
.stat-card {
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
}
.stat-card .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 0.4rem; }
.stat-card .value { font-size: 1.6rem; font-weight: 700; color: var(--gold); }
.stat-card .sub { font-size: 0.8rem; color: var(--muted); margin-top: 0.2rem; }

/* ── Season table ── */
.table-wrap {
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
}
.table-scroll {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.8rem;
  font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace;
  white-space: nowrap;
}
table thead th {
  background: var(--bg3);
  color: var(--muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.75rem 0.9rem;
  text-align: left;
  border-bottom: 2px solid var(--border);
}
table thead th:first-child { width: 3rem; text-align: center; }
table tbody tr { border-bottom: 1px solid var(--border); }
table tbody tr:hover { background: var(--bg3); }
table tbody td {
  padding: 0.55rem 0.9rem;
  vertical-align: middle;
}
table tbody td:first-child { text-align: center; color: var(--muted); font-size: 0.75rem; }
.champ-cell { color: var(--gold); font-weight: 600; }
.repeat-star { color: var(--gold2); margin-right: 0.15rem; }
.seed { color: var(--muted); font-size: 0.7rem; }
.cell-sub { font-size: 0.68rem; color: var(--muted); margin-top: 0.15rem; }
.era-off { font-size: 0.65rem; color: var(--green); }
.era-def { font-size: 0.65rem; color: var(--blue); }
.era-neu { font-size: 0.65rem; color: var(--muted); }
.era-shock { font-size: 0.65rem; color: var(--gold2); }
.fin-score { text-align: center; color: var(--muted); }
.moves-cell { color: var(--blue); font-size: 0.75rem; }
#toc { border-bottom: 1px solid var(--border); }
.toc-link { display:flex; align-items:center; gap:0.6rem; padding:0.5rem 0.75rem; border-radius:6px; text-decoration:none; color:var(--text); font-size:0.9rem; transition:background 0.15s; }
.toc-link:hover { background:var(--bg3); color:var(--gold); }
.toc-num { font-size:0.7rem; color:var(--muted); font-variant-numeric:tabular-nums; min-width:1.4rem; }
.hi-ppg { color: var(--green); }
.lo-ppg { color: var(--red); }
.avg-cell { color: var(--muted); }

/* ── Championships bar chart ── */
.champ-list { display: flex; flex-direction: column; gap: 0.5rem; max-width: 700px; }
.champ-row { display: flex; align-items: center; gap: 1rem; }
.champ-name { width: 200px; font-size: 0.9rem; flex-shrink: 0; }
.champ-bar-wrap { flex: 1; background: var(--bg3); border-radius: 4px; height: 22px; overflow: hidden; }
.champ-bar { height: 100%; background: linear-gradient(90deg, var(--gold) 0%, var(--gold2) 100%); border-radius: 4px; display: flex; align-items: center; padding-left: 8px; }
.champ-count { font-size: 0.8rem; font-weight: 700; color: var(--bg); }

/* ── Two-col layout ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 3rem; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }

/* ── Small tables ── */
.data-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.data-table th {
  text-align: left;
  color: var(--muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
}
.data-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--bg3); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.gold { color: var(--gold); }

/* ── Sub-section headers ── */
.sub-header {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text);
  margin: 2.5rem 0 1rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--border);
}
.sub-header:first-child { margin-top: 0; }

/* ── Relocation list ── */
.reloc-list { font-size: 0.85rem; columns: 2; column-gap: 2rem; }
@media (max-width: 700px) { .reloc-list { columns: 1; } }
.reloc-item { padding: 0.3rem 0; border-bottom: 1px solid var(--border); break-inside: avoid; }
.reloc-item .sn { color: var(--muted); font-size: 0.75rem; margin-right: 0.5rem; }
.arrow { color: var(--gold); margin: 0 0.4rem; }

/* ── Series dist ── */
.series-dist { display: flex; flex-direction: column; gap: 0.6rem; max-width: 400px; }
.series-row { display: flex; align-items: center; gap: 1rem; font-size: 0.875rem; }
.series-label { width: 160px; flex-shrink: 0; }
.series-bar-wrap { flex: 1; background: var(--bg3); border-radius: 4px; height: 20px; overflow: hidden; }
.series-bar { height: 100%; background: var(--bg); border-radius: 4px; }
.series-pct { width: 50px; text-align: right; color: var(--muted); font-size: 0.8rem; }

/* ── Footer ── */
footer {
  background: var(--bg2);
  border-top: 1px solid var(--border);
  padding: 2rem;
  text-align: center;
  font-size: 0.8rem;
  color: var(--muted);
}
footer a { color: var(--muted); }
footer a:hover { color: var(--gold); }
"""


def season_table_html(rows: list[dict]) -> str:
    header = """
    <thead>
      <tr>
        <th>#</th>
        <th>Champion</th>
        <th>Runner-up</th>
        <th>FIN</th>
        <th>Clincher</th>
        <th>Regular Season Champion</th>
        <th>Last Place</th>
      </tr>
    </thead>"""
    body_rows = []
    for r in rows:
        repeat = '<span class="repeat-star">★</span>' if r["repeat"] else ""
        c_scored, c_allowed = r["champ_pts"]
        f_scored, f_allowed = r["finalist_pts"]
        rs_scored, rs_allowed = r["rs_leader_pts"]
        lp_scored, lp_allowed = r["last_pts"]
        c_titles = r["champ_titles"]
        c_finals = r["champ_finals"]
        f_finals = r["finalist_finals"]
        c_title_str = f"{c_titles} title{'s' if c_titles != 1 else ''}"
        c_sub = f'<div class="cell-sub">({c_title_str}, {c_finals} finals) · PS/PA: {c_scored} / {c_allowed}</div>'
        f_sub = f'<div class="cell-sub">({f_finals} finals) · PS/PA: {f_scored} / {f_allowed}</div>'
        rs_t = r["rs_leader_titles"]
        lp_c = r["last_place_count"]
        rs_t_str = f"{rs_t} title{'s' if rs_t != 1 else ''}"
        lp_c_str = f"{lp_c}x last"
        rs_sub = f'<div class="cell-sub">({rs_t_str}) · PS/PA: {rs_scored} / {rs_allowed}</div>'
        lp_sub = f'<div class="cell-sub">({lp_c_str}) · PS/PA: {lp_scored} / {lp_allowed}</div>'
        meta = r["meta"]
        ppg = f'{r["avg_ppg"]:.1f}'
        if meta > 0.04:
            era_html = f'<div class="era-off">▲ OFF · {ppg}</div>'
        elif meta < -0.04:
            era_html = f'<div class="era-def">▼ DEF · {ppg}</div>'
        else:
            era_html = f'<div class="era-neu">– NEU · {ppg}</div>'
        if r.get("meta_shock"):
            era_html += f'<div class="era-shock">⚡ RULE CHG</div>'
        tc = r.get("team_count", "")
        lp = r.get("league_pop")
        if tc:
            era_html += f'<div style="font-size:0.65rem;color:var(--muted);margin-top:2px">{tc} teams · {lp:.0%} pop</div>' if lp is not None else f'<div style="font-size:0.65rem;color:var(--muted);margin-top:2px">{tc} teams</div>'
        body_rows.append(f"""
      <tr>
        <td>{r["season"]}{era_html}</td>
        <td class="champ-cell">{repeat}{r["champ"]} <span class="seed">({r["champ_seed"]} seed)</span> {r["champ_w"]}–{r["champ_l"]}{c_sub}</td>
        <td>{r["finalist"]} <span class="seed">({r["finalist_seed"]} seed)</span> {r["finalist_w"]}–{r["finalist_l"]}{f_sub}</td>
        <td class="fin-score">{r["fin"]}</td>
        <td class="fin-score">{r["clinch"]}</td>
        <td>{r["rs_leader"]} {r["rs_leader_w"]}–{r["rs_leader_l"]}{rs_sub}</td>
        <td>{r["last"]} {r["last_w"]}–{r["last_l"]}{lp_sub}</td>
      </tr>""")
    return f"<table>\n{header}\n<tbody>{''.join(body_rows)}\n</tbody>\n</table>"


def champ_bar_chart(data: list[tuple]) -> str:
    max_val = data[0][1] if data else 1
    rows = []
    for name, count, seasons in data:
        pct = count / max_val * 100
        rate = f"{count/seasons:.3f}" if seasons else "—"
        rows.append(f"""
    <div class="champ-row">
      <div class="champ-name">{name}<span style="color:var(--muted);font-size:0.72rem;margin-left:0.5rem">({seasons} seasons · {rate}/yr)</span></div>
      <div class="champ-bar-wrap">
        <div class="champ-bar" style="width:{pct}%">
          <span class="champ-count">{count}</span>
        </div>
      </div>
    </div>""")
    return f'<div class="champ-list">{"".join(rows)}</div>'


def finals_table(data: list) -> str:
    rows = []
    for name, apps, w, l, seasons in data:
        win_pct = w / apps if apps else 0
        rate = f"{apps/seasons:.3f}" if seasons else "—"
        rows.append(f"""
    <tr>
      <td>{name}</td>
      <td class="num">{apps}</td>
      <td class="num gold">{w}</td>
      <td class="num">{l}</td>
      <td class="num">{win_pct:.0%}</td>
      <td class="num" style="color:var(--muted)">{seasons} <span style="font-size:0.72rem">({rate}/yr)</span></td>
    </tr>""")
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">App</th><th class="num">W</th><th class="num">L</th><th class="num">Win%</th><th class="num">Seasons</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def rs_titles_table(data: list) -> str:
    rows = []
    for name, count, seasons in data:
        rate = f"{count/seasons:.3f}" if seasons else "—"
        rows.append(
            f'<tr><td>{name}</td><td class="num gold">{count}</td>'
            f'<td class="num" style="color:var(--muted)">{seasons} <span style="font-size:0.72rem">({rate}/yr)</span></td></tr>'
        )
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">RS Titles</th><th class="num">Seasons</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def streaks_table(data: list) -> str:
    rows = []
    for length, start, end, name in data:
        label = f"S{start}" if start == end else f"S{start}–S{end}"
        rows.append(f'<tr><td>{name}</td><td class="num gold">{length}</td><td class="num">{label}</td></tr>')
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">Length</th><th class="num">Seasons</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def droughts_table(data: list) -> str:
    rows = []
    for length, start, end, name, never in data:
        label = "(never won)" if never else f"S{start}–S{end}"
        rows.append(f'<tr><td>{name}</td><td class="num">{length}</td><td class="num">{label}</td></tr>')
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">Seasons</th><th class="num">Period</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def series_dist_html(counts: dict, n: int) -> str:
    total = sum(counts.values())
    bars = []
    labels = {4: "Sweep (4–0)", 5: "5 games", 6: "6 games", 7: "7 games"}
    for g in sorted(counts):
        c = counts[g]
        pct = c / total * 100
        label = labels.get(g, f"{g} games")
        bars.append(f"""
  <div class="series-row">
    <div class="series-label">{label}</div>
    <div class="series-bar-wrap">
      <div class="series-bar" style="width:{100-pct:.0f}%; float:right; background:var(--bg3)"></div>
      <div style="position:absolute; height:20px; width:{pct:.0f}%; background:linear-gradient(90deg,var(--gold),var(--gold2)); border-radius:4px;"></div>
    </div>
    <div class="series-pct">{c}x ({pct:.0f}%)</div>
  </div>""")
    return f'<div class="series-dist" style="position:relative">{"".join(bars)}</div>'


def rivalries_html(data: list, label: str) -> str:
    rows = []
    for a, b, meetings, record in data:
        # Extract win counts from record string to display inline
        parts = record.split(" leads ")
        if len(parts) == 2:
            wins_str = parts[1]          # e.g. "5–3"
            wa, wb = wins_str.split("–")
        else:
            # Tied — parse from "Tied X–Y"
            wins_str = record.replace("Tied ", "")
            wa, wb = wins_str.split("–")
        rows.append(
            f'<tr>'
            f'<td style="color:var(--text)">{a} <span style="color:var(--muted);font-size:0.82em">({wa})</span></td>'
            f'<td style="color:var(--muted);padding:0 0.4rem">vs</td>'
            f'<td style="color:var(--text)">{b} <span style="color:var(--muted);font-size:0.82em">({wb})</span></td>'
            f'<td class="num gold">{meetings}</td>'
            f'</tr>'
        )
    return f"""<table class="data-table">
  <thead><tr><th colspan="3">Matchup</th><th class="num">{label}</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def seed_grid_html(grid: dict) -> str:
    n = grid["n"]
    wins  = grid["wins"]
    total = grid["total"]
    seeds = list(range(1, n + 1))

    header_cells = '<th></th>' + ''.join(f'<th class="num">vs {s}</th>' for s in seeds)
    rows = []
    for row in seeds:
        cells = [f'<td style="color:var(--gold);font-weight:600">{row} seed</td>']
        for col in seeds:
            if row == col:
                cells.append('<td style="color:var(--muted);text-align:center">—</td>')
            else:
                t = total[row][col]
                if t == 0:
                    cells.append('<td style="color:var(--muted);text-align:center">–</td>')
                else:
                    w = wins[row][col]
                    pct = w / t
                    pct_str = f"{pct:.0%}"
                    rec_str = f'<div style="font-size:0.7rem;color:var(--muted)">{w}–{t-w}</div>'
                    if pct >= 0.60:
                        color = "var(--green)"
                    elif pct <= 0.40:
                        color = "var(--red)"
                    else:
                        color = "var(--text)"
                    cells.append(
                        f'<td style="text-align:center;color:{color}">'
                        f'{pct_str}{rec_str}</td>'
                    )
        rows.append(f'<tr>{"".join(cells)}</tr>')

    return f"""<table class="data-table">
  <thead><tr>{header_cells}</tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def popularity_table_html(rows: list[dict]) -> str:
    _label_color = {
        "Champion":  "var(--gold)",
        "Finals":    "var(--gold2)",
        "Playoffs":  "var(--green)",
        "Last Place":"var(--red)",
        "Bottom 2":  "#ff9966",
    }
    header = '<tr><th class="num">Season</th>' + ''.join(f'<th>#{i+1}</th>' for i in range(5)) + '</tr>'
    body_rows = []
    for r in rows:
        cells = [f'<td class="num" style="color:var(--muted)">{r["season"]}</td>']
        for name, val, label in r["top5"]:
            pct = f"{val:.0%}"
            label_html = ""
            if label:
                color = _label_color.get(label, "var(--muted)")
                label_html = f' <span style="color:{color};font-size:0.7rem">{label}</span>'
            cells.append(f'<td>{escape(name)}{label_html} <span style="color:var(--muted);font-size:0.75rem">({pct})</span></td>')
        body_rows.append(f'<tr>{"".join(cells)}</tr>')
    return f'<table class="data-table"><thead>{header}</thead><tbody>{"".join(body_rows)}</tbody></table>'


def team_history_html(histories: list) -> str:
    blocks = []
    for h in histories:
        name = h["current_name"]
        aka_html = ""
        rows = []
        for r in h["seasons"]:
            if r.get("expansion"):
                entry_type = r.get("entry_type", "expansion")
                if entry_type == "merger":
                    kind = "rival merger (shared market)" if r["is_secondary"] else "rival merger"
                    color = "var(--blue)"
                else:
                    kind = "second franchise in market" if r["is_secondary"] else "expansion franchise"
                    color = "var(--gold2)"
                msg = f'★ Entered league via {kind} ahead of Season {r["after_season"] + 1}'
                rows.append(
                    f'<tr><td colspan="8" style="text-align:center;font-style:italic;'
                    f'color:{color};font-size:0.78rem;padding:0.35rem 1rem;'
                    f'background:var(--bg2);border-top:1px solid var(--border);'
                    f'border-bottom:1px solid var(--border)">{msg}</td></tr>'
                )
                continue
            if r.get("relocation"):
                if r["direction"] == "away":
                    msg = f'➜ Relocated to <strong>{r["dest"]}</strong> after Season {r["after_season"]}'
                else:
                    msg = f'➜ Relocated from <strong>{r["dest"]}</strong> ahead of Season {r["after_season"] + 1}'
                rows.append(
                    f'<tr><td colspan="8" style="text-align:center;font-style:italic;'
                    f'color:var(--muted);font-size:0.78rem;padding:0.35rem 1rem;'
                    f'background:var(--bg2);border-top:1px solid var(--border);'
                    f'border-bottom:1px solid var(--border)">{msg}</td></tr>'
                )
                continue
            margin_color = "var(--green)" if r["margin"] >= 0 else "var(--red)"
            win_rank = r.get("win_rank")
            win_rank_html = f'<span style="color:var(--muted);font-size:0.78rem"> (#{win_rank})</span>' if win_rank else ""

            pop = r["pop"]
            pop_rank = r.get("pop_rank")
            if pop is not None:
                pop_rank_html = f'<span style="color:var(--muted);font-size:0.78rem"> (#{pop_rank})</span>' if pop_rank else ""
                pop_html = f'{pop:.0%}{pop_rank_html}'
            else:
                pop_html = "—"

            seed_html = f'<span style="color:var(--gold2)">{r["seed"]}</span>' if r["seed"] else '<span style="color:var(--muted)">—</span>'

            # Build playoff matchup string: "W 4-0 vs. Team A · L 2-4 vs. Team B"
            matchups = r.get("matchups", [])
            if matchups:
                parts = []
                for m in matchups:
                    w_or_l = "W" if m["won"] else "L"
                    color = "var(--green)" if m["won"] else "var(--red)"
                    parts.append(
                        f'<span style="color:{color}">{w_or_l} {m["tw"]}–{m["tl"]}</span>'
                        f'<span style="color:var(--muted)"> vs. {m["opp"]}</span>'
                    )
                playoff_html = ' <span style="color:var(--border)">·</span> '.join(parts)
            else:
                playoff_html = '<span style="color:var(--muted)">—</span>'

            rows.append(
                f'<tr>'
                f'<td class="num" style="color:var(--muted)">{r["season"]}</td>'
                f'<td class="num">{r["rw"]}–{r["rl"]}{win_rank_html}</td>'
                f'<td class="num">{r["ps_g"]:.1f}</td>'
                f'<td class="num">{r["pa_g"]:.1f}</td>'
                f'<td class="num" style="color:{margin_color}">{r["margin"]:+.1f}</td>'
                f'<td class="num">{seed_html}</td>'
                f'<td style="white-space:nowrap">{playoff_html}</td>'
                f'<td class="num">{pop_html}</td>'
                f'</tr>'
            )
        table = (
            f'<table class="data-table" style="font-size:0.82rem">'
            f'<thead><tr>'
            f'<th class="num">Season</th><th class="num">Record</th>'
            f'<th class="num">PS/G</th><th class="num">PA/G</th><th class="num">Margin</th>'
            f'<th class="num">Seed</th><th>Playoff Results</th><th class="num">Popularity</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            f'</table>'
        )
        blocks.append(
            f'<details style="margin-bottom:1rem;border:1px solid var(--border);border-radius:8px;overflow:hidden">'
            f'<summary style="padding:0.75rem 1rem;cursor:pointer;background:var(--bg2);list-style:none;display:flex;align-items:center;gap:0.5rem">'
            f'<span style="color:var(--gold);font-weight:600">{name}</span>{aka_html}'
            f'</summary>'
            f'<div style="overflow-x:auto">{table}</div>'
            f'</details>'
        )
    return "".join(blocks)


def merger_html(mergers: list) -> str:
    if not mergers:
        return '<p style="color:var(--muted);font-style:italic">No mergers this simulation.</p>'
    # Group by season (each wave is one merger event)
    from collections import defaultdict
    waves: dict[int, list] = defaultdict(list)
    for sn, fname, is_secondary in mergers:
        waves[sn].append((fname, is_secondary))
    items = []
    for sn in sorted(waves):
        teams_in_wave = waves[sn]
        names_html = " · ".join(
            f'<span style="color:var(--gold2)">{fname}</span>'
            + (f'<span style="color:var(--muted);font-size:0.73rem"> (shared mkt)</span>' if is_sec else "")
            for fname, is_sec in teams_in_wave
        )
        items.append(
            f'<div class="reloc-item">'
            f'<span class="sn">After S{sn}</span>'
            f'⚡ Rival merger · {names_html}'
            f'</div>'
        )
    return f'<div class="reloc-list">{"".join(items)}</div>'


def expansion_html(expansions: list) -> str:
    if not expansions:
        return '<p style="color:var(--muted);font-style:italic">No expansion events this simulation.</p>'
    items = []
    for sn, fname, is_secondary in expansions:
        kind = '<span style="color:var(--muted);font-size:0.75rem">second franchise</span>' if is_secondary else '<span style="color:var(--muted);font-size:0.75rem">new market</span>'
        items.append(
            f'<div class="reloc-item">'
            f'<span class="sn">After S{sn}</span>'
            f'<span style="color:var(--gold2)">★ {fname}</span> entered the league · {kind}'
            f'</div>'
        )
    return f'<div class="reloc-list">{"".join(items)}</div>'


def reloc_html(relocations: list) -> str:
    items = []
    for sn, old, new, ls, b2, pop in relocations:
        if pop >= 0.60:
            pop_color = "var(--green)"
        elif pop >= 0.40:
            pop_color = "var(--text)"
        else:
            pop_color = "var(--red)"
        pop_html = f'<span style="color:{pop_color};font-size:0.75rem">popularity: {pop:.0%}</span>'
        items.append(
            f'<div class="reloc-item">'
            f'<span class="sn">After S{sn}</span>'
            f'{old}<span class="arrow">→</span>{new}'
            f'<span class="sn" style="margin-left:0.5rem">({ls} losing, {b2} bot-2)</span>'
            f' · {pop_html}'
            f'</div>'
        )
    return f'<div class="reloc-list">{"".join(items)}</div>'


def generate_html(rows: list[dict], alltime: dict, rivalries: dict, seed_grid: dict = None, pop_rows: list = None, team_histories: list = None) -> str:
    n = alltime["n"]
    best = alltime["best"]
    worst = alltime["worst"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ronjan Basketball League — 100-Season Simulation</title>
  <style>{CSS}</style>
</head>
<body>

<nav>
  <span class="brand">RBL</span>
  <a href="#season-results">Results</a>
  <a href="#all-time">All-Time</a>
  <a href="#rivalries">Rivalries</a>
  <a href="#seed-grid">Playoff Analysis</a>
  <a href="#popularity">Popularity</a>
  <a href="#relocations">Moves</a>
  <a href="#team-history">Team History</a>
  <a href="#how-it-works">How It Works</a>
</nav>

<div class="hero">
  <h1>Ronjan Basketball League</h1>
  <p style="font-size:0.85rem; color:var(--muted); margin-bottom:0.5rem; letter-spacing:0.08em;">EST. 1998</p>
  <p class="subtitle">A 100-season simulation recreating a program originally written in Visual Basic in 1998.</p>
  <span class="badge">seed: <span>{SEED}</span> &nbsp;·&nbsp; seasons: <span>{n}</span> &nbsp;·&nbsp; teams: <span>20</span></span>
</div>

<!-- ── Table of Contents ───────────────────────────────────── -->
<section id="toc">
  <div class="inner">
    <div class="section-title" style="font-size:1.1rem;margin-bottom:1.25rem">Contents</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:0.5rem 1.5rem">
      <a href="#season-results" class="toc-link">
        <span class="toc-num">01</span>
        <span>100-Season Results</span>
      </a>
      <a href="#all-time" class="toc-link">
        <span class="toc-num">02</span>
        <span>All-Time Records</span>
      </a>
      <a href="#rivalries" class="toc-link">
        <span class="toc-num">03</span>
        <span>Rivalries</span>
      </a>
      <a href="#seed-grid" class="toc-link">
        <span class="toc-num">04</span>
        <span>Playoff Analysis</span>
      </a>
      <a href="#popularity" class="toc-link">
        <span class="toc-num">05</span>
        <span>Team Popularity</span>
      </a>
      <a href="#relocations" class="toc-link">
        <span class="toc-num">06</span>
        <span>Franchise Moves</span>
      </a>
      <a href="#team-history" class="toc-link">
        <span class="toc-num">07</span>
        <span>Team History</span>
      </a>
      <a href="#how-it-works" class="toc-link">
        <span class="toc-num">08</span>
        <span>How It Works</span>
      </a>
    </div>
  </div>
</section>

<!-- ── Quick stats ─────────────────────────────────────────── -->
<section id="season-results">
  <div class="section-title">{n}-Season Results</div>
  <p class="section-sub">Seed {SEED} · {n} seasons · {len(rows)} seasons played · league grew from {rows[0]["team_count"]} to {rows[-1]["team_count"]} teams</p>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">Most Championships</div>
      <div class="value">{alltime["championships"][0][1]}</div>
      <div class="sub">{alltime["championships"][0][0]}</div>
      <div class="sub" style="font-size:0.72rem;margin-top:0.3rem;white-space:normal;line-height:1.7">{" · ".join(f"S{sn}" for sn in alltime["champ_seasons"].get(alltime["championships"][0][0], []))}</div>
    </div>
    <div class="stat-card">
      <div class="label">Longest Streak</div>
      <div class="value">{alltime["streaks"][0][0] if alltime["streaks"] else 0}</div>
      <div class="sub">{alltime["streaks"][0][3] if alltime["streaks"] else "—"}</div>
      <div class="sub" style="font-size:0.72rem;margin-top:0.3rem">S{alltime["streaks"][0][1]}–S{alltime["streaks"][0][2]}</div>
    </div>
    <div class="stat-card">
      <div class="label">Longest Drought</div>
      <div class="value">{alltime["droughts"][0][0]}</div>
      <div class="sub">{alltime["droughts"][0][3]}</div>
      <div class="sub" style="font-size:0.72rem;margin-top:0.3rem">{"(never won)" if alltime["droughts"][0][4] else f"S{alltime['droughts'][0][1]}–S{alltime['droughts'][0][2]}"}</div>
    </div>
    <div class="stat-card">
      <div class="label">Best Season</div>
      <div class="value">{best[0]}–{best[1]}</div>
      <div class="sub">{best[3]}</div>
      <div class="sub" style="font-size:0.72rem;margin-top:0.3rem">S{best[2]}</div>
    </div>
    <div class="stat-card">
      <div class="label">Worst Season</div>
      <div class="value">{worst[0]}–{worst[1]}</div>
      <div class="sub">{worst[3]}</div>
      <div class="sub" style="font-size:0.72rem;margin-top:0.3rem">S{worst[2]}</div>
    </div>
    <div class="stat-card">
      <div class="label">Franchise Moves</div>
      <div class="value">{alltime["total_relocations"]}</div>
      <div class="sub">{alltime["total_expansions"]} exp · {alltime["merger_waves"]} merger{"s" if alltime["merger_waves"] != 1 else ""} · {alltime["total_relocations"]} reloc</div>
    </div>
  </div>

  <div class="table-wrap">
    <div class="table-scroll">
      {season_table_html(rows)}
    </div>
  </div>
  <p style="font-size:0.75rem; color:var(--muted); margin-top:0.75rem;">
    ★ = repeat champion &nbsp;·&nbsp; seed in parentheses = playoff seeding &nbsp;·&nbsp; FIN = finals series score &nbsp;·&nbsp; Avg = league pts/game
  </p>
</section>

<!-- ── All-time records ────────────────────────────────────── -->
<section id="all-time" class="alt">
  <div class="inner">
    <div class="section-title">All-Time Records</div>
    <p class="section-sub">Cumulative stats across all {n} seasons</p>

    <div class="sub-header">Championships</div>
    {champ_bar_chart(alltime["championships"])}

    <div class="two-col" style="margin-top:3rem">
      <div>
        <div class="sub-header">Finals Appearances</div>
        {finals_table(alltime["finals"])}
      </div>
      <div>
        <div class="sub-header">Regular Season Titles</div>
        {rs_titles_table(alltime["rs_titles"])}
      </div>
    </div>

    <div class="two-col" style="margin-top:3rem">
      <div>
        <div class="sub-header">Longest Championship Streaks</div>
        {streaks_table(alltime["streaks"])}
      </div>
      <div>
        <div class="sub-header">Longest Championship Droughts</div>
        {droughts_table(alltime["droughts"])}
      </div>
    </div>

    <div class="two-col" style="margin-top:2.5rem">
      <div>
        <div class="sub-header">Longest Playoff Streaks</div>
        <table class="data-table">
          <thead><tr><th>Franchise</th><th class="num">Seasons</th><th class="num">Window</th><th class="num">Titles</th><th class="num">Finals</th></tr></thead>
          <tbody>{"".join(
            f'<tr><td>{nm}</td><td class="num">{l}</td>'
            f'<td class="num" style="color:var(--muted)">S{s}–S{e}</td>'
            f'<td class="num">{"★ " * t if t else "–"}</td>'
            f'<td class="num">{f}</td></tr>'
            for l, s, e, nm, t, f in alltime["playoff_streaks"]
          )}</tbody>
        </table>
      </div>
      <div>
        <div class="sub-header">Longest Playoff Droughts</div>
        <table class="data-table">
          <thead><tr><th>Franchise</th><th class="num">Seasons</th><th class="num">Window</th></tr></thead>
          <tbody>{"".join(
            f'<tr><td>{nm}</td><td class="num">{l}</td>'
            f'<td class="num" style="color:var(--muted)">S{s}–S{e}</td></tr>'
            for l, s, e, nm in alltime["playoff_droughts"]
          )}</tbody>
        </table>
      </div>
    </div>

    <div style="margin-top:3rem">
      <div class="sub-header" style="margin-bottom:1rem">Best Single Seasons (Overall Record incl. Postseason)</div>
      <table class="data-table">
        <thead><tr><th class="num">Season</th><th>Team</th><th class="num">Overall Record</th><th class="num">Win%</th><th class="num">RS Record</th><th class="num">RS Win%</th><th class="num">PS/G</th><th class="num">PA/G</th><th class="num">Margin</th><th></th></tr></thead>
        <tbody>{"".join(
          f'<tr>'
          f'<td class="num" style="color:var(--muted)">{r["season"]}</td>'
          f'<td>{r["name"]}</td>'
          f'<td class="num">{r["total_w"]}–{r["total_l"]}</td>'
          f'<td class="num">{r["total_pct"]:.1%}</td>'
          f'<td class="num" style="color:var(--muted)">{r["rw"]}–{r["rl"]}</td>'
          f'<td class="num" style="color:var(--muted)">{r["reg_pct"]:.1%}</td>'
          f'<td class="num">{r["total_ps"] / (r["total_w"] + r["total_l"]):.1f}</td>'
          f'<td class="num">{r["total_pa"] / (r["total_w"] + r["total_l"]):.1f}</td>'
          f'<td class="num" style="color:var(--green)">+{r["total_margin"]:.1f}</td>'
          f'<td>{"★" if r["is_champ"] else ""}</td>'
          f'</tr>'
          for r in alltime["best_teams"]
        )}</tbody>
      </table>
    </div>

    <div style="margin-top:2rem">
      <div class="sub-header" style="margin-bottom:1rem">Worst Single Seasons (Regular Season Record)</div>
      <table class="data-table">
        <thead><tr><th class="num">Season</th><th>Team</th><th class="num">Record</th><th class="num">Win%</th><th class="num">PS/G</th><th class="num">PA/G</th><th class="num">Margin</th></tr></thead>
        <tbody>{"".join(
          f'<tr>'
          f'<td class="num" style="color:var(--muted)">{r["season"]}</td>'
          f'<td>{r["name"]}</td>'
          f'<td class="num">{r["rw"]}–{r["rl"]}</td>'
          f'<td class="num">{r["reg_pct"]:.1%}</td>'
          f'<td class="num">{r["reg_ps"] / (r["rw"] + r["rl"]):.1f}</td>'
          f'<td class="num">{r["reg_pa"] / (r["rw"] + r["rl"]):.1f}</td>'
          f'<td class="num" style="color:var(--red)">{r["reg_margin"]:+.1f}</td>'
          f'</tr>'
          for r in alltime["worst_teams"]
        )}</tbody>
      </table>
    </div>

  </div>
</section>

<!-- ── Rivalries ─────────────────────────────────────────── -->
<section id="rivalries" class="alt">
  <div class="inner">
    <div class="section-title">Rivalries</div>
    <p class="section-sub">Most frequent matchups across all {n} seasons</p>
    <div class="two-col">
      <div>
        <div class="sub-header">Most Common Regular Season Matchups</div>
        {rivalries_html(rivalries["rs"], "RS Games")}
      </div>
      <div>
        <div class="sub-header">Most Games Played (All-Time)</div>
        {rivalries_html(rivalries["all_games"], "Total Games")}
      </div>
    </div>
    <div class="two-col" style="margin-top:2.5rem">
      <div>
        <div class="sub-header">Most Common Playoff Series Matchups</div>
        {rivalries_html(rivalries["playoff"], "Series")}
      </div>
      <div>
        <div class="sub-header">Most Common Finals Matchups</div>
        {rivalries_html(rivalries["finals"], "Finals")}
      </div>
    </div>
  </div>
</section>

<!-- ── Seed Grid ──────────────────────────────────────────── -->
<section id="seed-grid">
  <div class="inner">
    <div class="section-title">Playoff Analysis</div>
    <p class="section-sub">Seed matchup win % and series length breakdown across all {n} seasons</p>
    <div class="sub-header" style="margin-bottom:0.75rem">Seed vs. Seed Win %</div>
    <p style="font-size:0.8rem;color:var(--muted);margin-bottom:1rem">green ≥ 60% · red ≤ 40%</p>
    {seed_grid_html(seed_grid) if seed_grid else ""}
    <div class="sub-header" style="margin-top:2.5rem;margin-bottom:1rem">Series Length by Round</div>
    {(lambda rounds, rnames: f'''<table class="data-table">
      <thead><tr>
        <th>Round</th>
        {"".join(f'<th class="num">{"Sweep" if g==4 else f"{g} games"}</th>' for g in sorted(set(g for c in rounds for g in c)))}
      </tr></thead>
      <tbody>{"".join(f'<tr><td style="color:var(--gold2)">{name}</td>' + "".join(
        f'<td class="num">{counts.get(g,0)}x <span style="color:var(--muted);font-size:0.75rem">({counts.get(g,0)/sum(counts.values())*100:.0f}%)</span></td>'
        for g in sorted(set(g for c in rounds for g in c))
      ) + '</tr>'
      for name, counts in zip(rnames, rounds) if counts
      )}</tbody>
    </table>''')(alltime["series_counts_by_round"], alltime["series_round_names"])}
  </div>
</section>

<!-- ── Popularity ─────────────────────────────────────────── -->
<section id="popularity" class="alt">
  <div class="inner">
    <div class="section-title">Team Popularity</div>
    <p class="section-sub">Top 5 most popular teams each season · influenced by market size and success</p>
    {popularity_table_html(pop_rows) if pop_rows else ""}
  </div>
</section>

<!-- ── Relocations ────────────────────────────────────────── -->
<section id="relocations">
  <div class="section-title">Franchise Moves</div>
  <p class="section-sub">{alltime["total_expansions"]} expansions · {alltime["merger_waves"]} merger wave{"s" if alltime["merger_waves"] != 1 else ""} ({alltime["total_mergers"]} teams) · {alltime["total_relocations"]} relocations across {n} seasons</p>
  <div class="sub-header" style="margin-bottom:0.75rem">Expansions</div>
  {expansion_html(alltime["expansions"])}
  <div class="sub-header" style="margin-top:2rem;margin-bottom:0.75rem">Rival Mergers</div>
  {merger_html(alltime["mergers"])}
  <div class="sub-header" style="margin-top:2rem;margin-bottom:0.75rem">Relocations</div>
  {reloc_html(alltime["relocations"])}
</section>

<!-- ── Team History ───────────────────────────────────────── -->
<section id="team-history">
  <div class="inner">
    <div class="section-title">Team History</div>
    <p class="section-sub">Season-by-season record, scoring, playoff results, and popularity for all 20 franchises · click to expand</p>
    {team_history_html(team_histories) if team_histories else ""}
  </div>
</section>

<!-- ── How It Works ───────────────────────────────────────── -->
<section id="how-it-works" class="alt">
  <div class="inner">
    <div class="section-title">How It Works</div>
    <p class="section-sub">A 100-season basketball universe — six Python files, ~900 lines, built with Claude Code</p>
    <div class="code-grid">

      <div class="code-card">
        <h3>Competitive balance over time</h3>
        <p>No team stays dominant forever. Every win and loss shifts a team's quality rating up or down, creating in-season momentum. Each offseason, playoff teams reset to quality levels reflecting how far they went — a 7-game semifinal exit is worth more than a sweep. Non-playoff teams drift randomly, with big-market teams having a slight upward pull (talent magnet) and small-market teams a slight downward one. This produces realistic cycles of dynasty, decline, and rebuilding.</p>
      </div>

      <div class="code-card">
        <h3>Offensive and defensive identities</h3>
        <p>Every team has an identity — a value from 0 (pure defense) to 1 (pure offense) — that affects how games are scored. Winning stabilizes that identity; losing makes a team more willing to change its approach. Champions entrench their style; perennial losers search for answers. A league-wide meta nudge means teams gradually absorb the style of whatever era they're playing in, making winning styles temporarily self-reinforcing.</p>
      </div>

      <div class="code-card">
        <h3>League eras and rule changes</h3>
        <p>The league cycles through offensive and defensive eras organically — driven by what style of team is winning championships. Offensive eras play at a higher tempo (~110 ppg), defensive eras slow down (~90 ppg). Eras are self-reinforcing but naturally reverse via momentum decay and spring reversion. If an era runs too extreme for too long, a rule-change shock fires — yanking the meta back toward neutral, sometimes overcorrecting into the opposite extreme, just like the real game.</p>
      </div>

      <div class="code-card">
        <h3>Market forces and relocation</h3>
        <p>Cities have market sizes that shape long-run team trajectories. Big markets attract talent and recover from down years more reliably. Small-market teams can compete and win, but sustained failure is harder to reverse. After 8+ consecutive losing seasons with repeated bottom-2 finishes, a team becomes eligible to relocate — blocked only by championship protection (20 seasons) or finals protection (10 seasons). Teams can't move to a city smaller than half their current market.</p>
      </div>

      <div class="code-card">
        <h3>Fanbase and popularity</h3>
        <p>Every team has a popularity score anchored to its market baseline. Winning pushes it above that baseline — a small-market champion can build a national following far larger than their city would predict, like the real-world Green Bay effect. But sustained losing erodes it, progressively faster the longer the drought continues. Crucially, the miss-playoffs penalty only applies to teams already above their baseline: disappointment requires expectation. Teams that relocate carry 60% of their fanbase to the new city.</p>
      </div>

      <div class="code-card">
        <h3>Playoff seeding and series dynamics</h3>
        <p>The top 8 teams enter a seeded bracket (1v8, 2v7, etc.) in best-of-7 series. Higher seeds earn a constant bonus in every game — not just home games — rewarding regular-season performance. Series length is tracked across all three rounds, producing realistic distributions of sweeps, 6-game series, and 7-game classics. The seed-vs-seed win grid reveals how much the bracket rewards or punishes regular-season position over the full 100-season run.</p>
      </div>

    </div>
  </div>
</section>

<footer>
  <p>Built with <a href="https://claude.ai/claude-code">Claude Code</a> · Python · ~900 lines · seed {SEED}</p>
  <p style="margin-top:0.4rem">Recreating a Visual Basic program from 1998, one season at a time.</p>
</footer>

</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    random.seed(SEED)
    cfg = Config(num_seasons=NUM_SEASONS)
    league = League(cfg)
    league.simulate()

    rows = build_season_rows(league)
    alltime = build_alltime(league)
    rivalries = build_rivalries(league)
    seed_grid = build_seed_grid(league)
    pop_rows      = build_popularity_rows(league)
    team_histories = build_team_histories(league)
    html = generate_html(rows, alltime, rivalries, seed_grid, pop_rows, team_histories)

    out = "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Wrote {out}  ({len(html):,} bytes)")
