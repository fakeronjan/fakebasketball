"""Generate index.html — a self-contained website for the Ronjan Basketball League simulation."""

import random
from html import escape

from config import Config
from league import League
from season import Season


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

    champ_seasons_by_name: dict[str, list[int]] = defaultdict(list)
    finals_wins_by_name:   dict[str, int] = defaultdict(int)
    finals_apps_by_name:   dict[str, int] = defaultdict(int)
    rs_by_name:            dict[str, int] = defaultdict(int)

    for s in seasons:
        c_name = s.champion.franchise_at(s.number).name
        r_name = _runner_up(s).franchise_at(s.number).name
        rs_name = s.regular_season_standings[0].franchise_at(s.number).name
        champ_seasons_by_name[c_name].append(s.number)
        finals_wins_by_name[c_name] += 1
        finals_apps_by_name[c_name] += 1
        finals_apps_by_name[r_name] += 1
        rs_by_name[rs_name] += 1

    champ_count = {name: len(wins) for name, wins in champ_seasons_by_name.items()}

    championships = sorted(champ_count.items(), key=lambda x: -x[1])
    finals_list = sorted(
        [(name, finals_apps_by_name[name], finals_wins_by_name[name],
          finals_apps_by_name[name] - finals_wins_by_name[name])
         for name in finals_apps_by_name],
        key=lambda x: -x[1]
    )
    rs_list = sorted(rs_by_name.items(), key=lambda x: -x[1])

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

    # Active season ranges for each franchise name
    # (a name can appear for multiple teams in different eras)
    franchise_ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for team in teams:
        hist = team.franchise_history
        for i, (start, franchise) in enumerate(hist):
            end = hist[i + 1][0] - 1 if i + 1 < len(hist) else n
            franchise_ranges[franchise.name].append((start, end))

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

    series_counts = {}
    for s in seasons:
        g = len(s.playoff_rounds[-1][0].games)
        series_counts[g] = series_counts.get(g, 0) + 1

    best = (0, 0, None, 0)
    worst_rec = (999, 0, None, 0)
    for s in seasons:
        for team in s.teams:
            w, l = s.reg_wins(team), s.reg_losses(team)
            if w > best[0]:
                best = (w, s.number, team, l)
            if w < worst_rec[0]:
                worst_rec = (w, s.number, team, l)

    return {
        "championships": [(escape(name), c) for name, c in championships],
        "finals": [(escape(name), apps, w, l) for name, apps, w, l in finals_list],
        "rs_titles": [(escape(name), c) for name, c in rs_list],
        "streaks": [(length, start, end, escape(name))
                    for length, start, end, name in streaks[:8]],
        "droughts": [(length, start, end, escape(fname), never)
                     for length, start, end, fname, never in droughts[:8]],
        "series_counts": series_counts,
        "best": (best[0], best[3], best[1], escape(best[2].franchise_at(best[1]).name)),
        "worst": (worst_rec[0], worst_rec[3], worst_rec[1], escape(worst_rec[2].franchise_at(worst_rec[1]).name)),
        "relocations": [(sn, escape(o), escape(nn), ls, b2) for sn, o, nn, ls, b2 in league.relocation_log],
        "total_relocations": len(league.relocation_log),
        "n": n,
    }


def build_rivalries(league: League) -> dict:
    from collections import defaultdict

    # meetings[(a, b)] = {'total': int, 'wins': {name: int}}
    # pair key is always alphabetically sorted so (A, B) == (B, A)
    playoff_data = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})
    finals_data  = defaultdict(lambda: {"total": 0, "wins": defaultdict(int)})

    for s in league.seasons:
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

    def _format(pair, data):
        a, b = pair
        wa = data["wins"].get(a, 0)
        wb = data["wins"].get(b, 0)
        total = data["total"]
        if wa > wb:
            record = f"{escape(a)} leads {wa}–{wb}"
        elif wb > wa:
            record = f"{escape(b)} leads {wb}–{wa}"
        else:
            record = f"Tied {wa}–{wb}"
        return (escape(a), escape(b), total, record)

    playoff_list = sorted(playoff_data.items(), key=lambda x: -x[1]["total"])
    finals_list  = sorted(finals_data.items(),  key=lambda x: -x[1]["total"])

    return {
        "playoff": [_format(p, d) for p, d in playoff_list[:15]],
        "finals":  [_format(p, d) for p, d in finals_list[:10]],
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #0c0d10;
  --bg2: #13141a;
  --bg3: #1c1e27;
  --border: #2a2d3a;
  --gold: #f0b429;
  --gold2: #ffd166;
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
.fin-score { text-align: center; color: var(--muted); }
.moves-cell { color: var(--blue); font-size: 0.75rem; }
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
        body_rows.append(f"""
      <tr>
        <td>{r["season"]}</td>
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
    for name, count in data:
        pct = count / max_val * 100
        rows.append(f"""
    <div class="champ-row">
      <div class="champ-name">{name}</div>
      <div class="champ-bar-wrap">
        <div class="champ-bar" style="width:{pct}%">
          <span class="champ-count">{count}</span>
        </div>
      </div>
    </div>""")
    return f'<div class="champ-list">{"".join(rows)}</div>'


def finals_table(data: list) -> str:
    rows = []
    for name, apps, w, l in data:
        win_pct = w / apps if apps else 0
        rows.append(f"""
    <tr>
      <td>{name}</td>
      <td class="num">{apps}</td>
      <td class="num gold">{w}</td>
      <td class="num">{l}</td>
      <td class="num">{win_pct:.0%}</td>
    </tr>""")
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">App</th><th class="num">W</th><th class="num">L</th><th class="num">Win%</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def rs_titles_table(data: list) -> str:
    rows = []
    for name, count in data:
        rows.append(f'<tr><td>{name}</td><td class="num gold">{count}</td></tr>')
    return f"""<table class="data-table">
  <thead><tr><th>Team</th><th class="num">RS Titles</th></tr></thead>
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
        rows.append(
            f'<tr>'
            f'<td>{a}</td>'
            f'<td style="color:var(--muted);padding:0 0.4rem">vs</td>'
            f'<td>{b}</td>'
            f'<td class="num gold">{meetings}</td>'
            f'<td style="color:var(--muted);font-size:0.82em">{record}</td>'
            f'</tr>'
        )
    return f"""<table class="data-table">
  <thead><tr><th colspan="3">Matchup</th><th class="num">{label}</th><th>Series Record</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def reloc_html(relocations: list) -> str:
    items = []
    for sn, old, new, ls, b2 in relocations:
        items.append(
            f'<div class="reloc-item">'
            f'<span class="sn">After S{sn}</span>'
            f'{old}<span class="arrow">→</span>{new}'
            f'<span class="sn" style="margin-left:0.5rem">({ls} losing, {b2} bot-2)</span>'
            f'</div>'
        )
    return f'<div class="reloc-list">{"".join(items)}</div>'


def generate_html(rows: list[dict], alltime: dict, rivalries: dict) -> str:
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
  <a href="#relocations">Moves</a>
  <a href="#how-it-works">How It Works</a>
</nav>

<div class="hero">
  <h1>Ronjan Basketball League</h1>
  <p style="font-size:0.85rem; color:var(--muted); margin-bottom:0.5rem; letter-spacing:0.08em;">EST. 1998</p>
  <p class="subtitle">A 100-season simulation recreating a program originally written in Visual Basic in 1998.</p>
  <span class="badge">seed: <span>{SEED}</span> &nbsp;·&nbsp; seasons: <span>{n}</span> &nbsp;·&nbsp; teams: <span>20</span></span>
</div>

<!-- ── Quick stats ─────────────────────────────────────────── -->
<section id="season-results">
  <div class="section-title">100-Season Results</div>
  <p class="section-sub">Seed {SEED} · Every season played, every franchise move logged</p>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">Most Championships</div>
      <div class="value">{alltime["championships"][0][1]}</div>
      <div class="sub">{alltime["championships"][0][0]}</div>
    </div>
    <div class="stat-card">
      <div class="label">Longest Streak</div>
      <div class="value">{alltime["streaks"][0][0] if alltime["streaks"] else 0}</div>
      <div class="sub">{alltime["streaks"][0][3] if alltime["streaks"] else "—"} (S{alltime["streaks"][0][1]}–S{alltime["streaks"][0][2]})</div>
    </div>
    <div class="stat-card">
      <div class="label">Longest Drought</div>
      <div class="value">{alltime["droughts"][0][0]}</div>
      <div class="sub">{alltime["droughts"][0][3]}</div>
    </div>
    <div class="stat-card">
      <div class="label">Best Season</div>
      <div class="value">{best[0]}–{best[1]}</div>
      <div class="sub">{best[3]} (S{best[2]})</div>
    </div>
    <div class="stat-card">
      <div class="label">Worst Season</div>
      <div class="value">{worst[0]}–{worst[1]}</div>
      <div class="sub">{worst[3]} (S{worst[2]})</div>
    </div>
    <div class="stat-card">
      <div class="label">Franchise Moves</div>
      <div class="value">{alltime["total_relocations"]}</div>
      <div class="sub">across 100 seasons</div>
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
    <p class="section-sub">Cumulative stats across all 100 seasons</p>

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

    <div style="margin-top:3rem">
      <div class="sub-header">Finals by Series Length</div>
      <div style="display:flex; gap:1rem; flex-wrap:wrap; align-items:center">
        {"".join(
          f'<div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:1rem 1.5rem;text-align:center">'
          f'<div style="font-size:1.4rem;font-weight:700;color:var(--gold)">{counts[g]}x</div>'
          f'<div style="font-size:0.75rem;color:var(--muted);margin-top:0.2rem">'
          f'{"Sweep (4–0)" if g==4 else f"{g} games"}</div>'
          f'<div style="font-size:0.75rem;color:var(--muted)">{counts[g]/n*100:.0f}%</div>'
          f'</div>'
          for g, counts in [("g", alltime["series_counts"])]
          for g in sorted(counts)
        )}
      </div>
    </div>
  </div>
</section>

<!-- ── Rivalries ─────────────────────────────────────────── -->
<section id="rivalries" class="alt">
  <div class="inner">
    <div class="section-title">Rivalries</div>
    <p class="section-sub">Most frequent matchups across all 100 seasons</p>
    <div class="two-col">
      <div>
        <div class="sub-header">Most Common Playoff Matchups</div>
        {rivalries_html(rivalries["playoff"], "Meetings")}
      </div>
      <div>
        <div class="sub-header">Most Common Finals Matchups</div>
        {rivalries_html(rivalries["finals"], "Finals")}
      </div>
    </div>
  </div>
</section>

<!-- ── Relocations ────────────────────────────────────────── -->
<section id="relocations">
  <div class="section-title">Franchise Moves</div>
  <p class="section-sub">{alltime["total_relocations"]} relocations across 100 seasons</p>
  {reloc_html(alltime["relocations"])}
</section>

<!-- ── How It Works ───────────────────────────────────────── -->
<section id="how-it-works" class="alt">
  <div class="inner">
    <div class="section-title">How It Works</div>
    <p class="section-sub">Six Python files, ~500 lines total</p>
    <div class="code-grid">
      <div class="code-card">
        <div class="filename">config.py</div>
        <h3>All the knobs</h3>
        <p>A single dataclass with every tunable parameter: team count, possessions per game, min/max strength, strength delta, home advantage, playoff bracket size, series length, relocation thresholds, and championship protection windows.</p>
      </div>
      <div class="code-card">
        <div class="filename">game.py</div>
        <h3>The possession engine</h3>
        <p>The heart of the simulation. Each possession yields <code>floor(random() × strength)</code> points. Play 100 possessions per team, break ties with sudden-death possessions, then adjust both teams' strength by ±0.03 (bounded at 3.0–3.3). Home court adds a configurable bonus to the home team's effective strength.</p>
      </div>
      <div class="code-card">
        <div class="filename">season.py</div>
        <h3>Schedule + playoffs</h3>
        <p>Generates a full home-and-away round robin (38 games per team). Snapshots records after the regular season so playoff wins don't inflate standings. Runs seeded bracket playoffs — 1v8, 2v7, etc. — in best-of-7 series with the proper home court pattern.</p>
      </div>
      <div class="code-card">
        <div class="filename">franchises.py</div>
        <h3>Cities and nicknames</h3>
        <p>Defines 20 active franchises (New York Empires through Las Vegas Dealers) and 18 reserve cities — each with a metro population used to enforce relocation market-size rules. No team can move to a market smaller than half its current city.</p>
      </div>
      <div class="code-card">
        <div class="filename">team.py</div>
        <h3>Franchise history</h3>
        <p>Each team object tracks its full franchise history as a list of (season, Franchise) pairs. The <code>franchise_at(season)</code> method returns the correct city and nickname for any point in history — so the 100-season table shows what teams were <em>actually called</em> when they won.</p>
      </div>
      <div class="code-card">
        <div class="filename">league.py</div>
        <h3>Multi-season + relocation</h3>
        <p>Orchestrates all 100 seasons. After each season, checks every team for relocation eligibility: 8 consecutive losing seasons, at least 3 bottom-2 finishes, no championship/finals protection, a viable destination market — and a 50% coin flip. Champions earn 20 seasons of protection; finalists earn 10.</p>
      </div>
    </div>
  </div>
</section>

<footer>
  <p>Built with <a href="https://claude.ai/claude-code">Claude Code</a> · Python · ~500 lines · seed {SEED}</p>
  <p style="margin-top:0.4rem">Recreating a Visual Basic program from 1998, one season at a time.</p>
</footer>

</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    random.seed(SEED)
    cfg = Config(num_seasons=NUM_SEASONS, quality_delta=0.03)
    league = League(cfg)
    league.simulate()

    rows = build_season_rows(league)
    alltime = build_alltime(league)
    rivalries = build_rivalries(league)
    html = generate_html(rows, alltime, rivalries)

    out = "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Wrote {out}  ({len(html):,} bytes)")
