"""Scrapes Premier League standings + top scorers (BBC Sport, ESPN as backup)."""
import re
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from io import StringIO

import numpy as np
import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent / "data"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BBC_TABLE = "https://www.bbc.com/sport/football/premier-league/table"
BBC_SCORERS = "https://www.bbc.com/sport/football/premier-league/top-scorers"
ESPN_TABLE = "https://www.espn.com/soccer/standings/_/league/eng.1"

COLMAP = {
    "team": "Team", "club": "Team",
    "played": "P", "p": "P", "gp": "P",
    "won": "W", "w": "W", "drawn": "D", "d": "D", "lost": "L", "l": "L",
    "for": "GF", "f": "GF", "gf": "GF", "against": "GA", "a": "GA", "ga": "GA",
    "goal difference": "GD", "goal diff": "GD", "goals for": "GF", "goals against": "GA", "gd": "GD", "points": "Pts", "pts": "Pts", "p.1": "Pts",
}


KNOWN_TEAMS = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea",
    "Crystal Palace", "Everton", "Fulham", "Leeds United", "Leeds", "Liverpool", "Man City",
    "Manchester City", "Man Utd", "Manchester United", "Newcastle United", "Newcastle",
    "Nottingham Forest", "Nott'm Forest", "Sunderland", "Tottenham Hotspur", "Tottenham",
    "West Ham United", "West Ham", "Wolverhampton Wanderers", "Wolves", "Leicester City",
    "Ipswich Town", "Southampton", "Luton Town", "Sheffield United", "Watford",
    "Hull City", "Coventry City", "Brighton & Hove Albion"]


def _dedupe(s):
    """BBC cells repeat their text ('ArsenalArsenal'); keep one copy."""
    s = str(s).strip()
    h = len(s) // 2
    return s[:h] if len(s) % 2 == 0 and s[:h] == s[h:] else s


def _split_player_team(s):
    s = _dedupe(s)
    for t in sorted(KNOWN_TEAMS, key=len, reverse=True):
        if s.endswith(t):
            return s[: -len(t)].strip(), t
    return s, ""


def _get_tables(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return pd.read_html(StringIO(r.content.decode("utf-8", errors="replace")))


PREFIXES = [("goal difference", "GD"), ("goal diff", "GD"), ("goals for", "GF"), ("goals against", "GA"),
            ("points", "Pts"), ("played", "P"), ("won", "W"), ("drawn", "D"), ("lost", "L"), ("team", "Team")]


def _map_col(c):
    k = str(c).strip().lower()
    if k in COLMAP:
        return COLMAP[k]
    # BBC glues the abbreviation on, e.g. 'PlayedP', 'Goals ForGF'
    for pre, name in PREFIXES:
        if k.startswith(pre):
            return name
    return str(c)


def _normalize(df):
    df = df.copy()
    df.columns = [_map_col(c[-1] if isinstance(c, tuple) else c) for c in df.columns]
    return df


def _finish_table(df):
    need = ["Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"]
    if not all(c in df.columns for c in need):
        raise ValueError(f"Missing columns, got {list(df.columns)}")
    df = df[need].copy()
    df["Team"] = df["Team"].astype(str).str.replace(r"^\d+\s*", "", regex=True).apply(_dedupe)
    for c in need[1:]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace("+", "", regex=False), errors="coerce")
    df = df.dropna(subset=["Pts"]).astype({c: int for c in need[1:]})
    if len(df) != 20 or df["Team"].nunique() != 20:
        raise ValueError("Expected 20 unique Premier League clubs")
    if not ((df.P == df.W + df.D + df.L) & (df.GD == df.GF - df.GA)).all():
        raise ValueError("Inconsistent standings statistics")
    df.insert(0, "Pos", range(1, len(df) + 1))
    return df.reset_index(drop=True)


def scrape_bbc_table():
    for t in _get_tables(BBC_TABLE):
        try:
            return _finish_table(_normalize(t))
        except Exception:
            continue
    raise ValueError("BBC table not found")


def scrape_espn_table():
    # ESPN splits the table in two: team names + stats
    tables = _get_tables(ESPN_TABLE)
    names, stats = tables[0], tables[1]
    names.columns = ["Team"]
    names["Team"] = names["Team"].astype(str).apply(
        lambda s: re.sub(r"^\d+", "", s).strip()
    ).str.replace(r"^[A-Z]{3}(?=[A-Z][a-z])|[A-Z]{3}$", "", regex=True).str.strip()
    df = pd.concat([names, _normalize(stats)], axis=1)
    return _finish_table(df)


def _scrape_players(stat, tables=None):
    """stat = 'goals' or 'assists'. BBC's top-scorers page holds one table per stat."""
    for t in tables if tables is not None else _get_tables(BBC_SCORERS):
        t = t.copy()
        t.columns = [str(c).strip().lower() for c in t.columns]
        name = next((c for c in t.columns if c.startswith(("name", "player"))), None)
        col = next((c for c in t.columns if c == stat or c == stat + stat[0]), None)
        if name and col:
            pt = t[name].apply(_split_player_team)
            out = pd.DataFrame({"Player": pt.str[0], "Team": pt.str[1]})
            team_col = next((c for c in t.columns if c in ("team", "club")), None)
            if team_col:
                out["Player"] = t[name].apply(_dedupe)
                out["Team"] = t[team_col].apply(_dedupe)
            label = stat.capitalize()
            out[label] = pd.to_numeric(t[col], errors="coerce")
            out = out.dropna(subset=[label]).astype({label: int})
            if out.empty or (out[label] < 0).any():
                raise ValueError("No valid player statistics")
            return out.sort_values(label, ascending=False).head(15).reset_index(drop=True)
    raise ValueError(f"{stat} table not found")


def scrape_scorers():
    return _scrape_players("goals")


def scrape_assists():
    return _scrape_players("assists")


def _sample_data():
    """Placeholder data so the dashboard still runs if scraping is blocked."""
    teams = ["Arsenal", "Man City", "Liverpool", "Chelsea", "Tottenham", "Newcastle", "Aston Villa",
             "Man Utd", "Brighton", "West Ham", "Fulham", "Brentford", "Crystal Palace", "Everton",
             "Wolves", "Bournemouth", "Nott'm Forest", "Leeds", "Burnley", "Sunderland"]
    rng = np.random.default_rng(42)
    rows = []
    for t in teams:
        w, d = int(rng.integers(2, 9)), int(rng.integers(1, 5))
        l = 10 - w - d if w + d < 10 else 0
        gf, ga = int(rng.integers(6, 22)), int(rng.integers(4, 18))
        rows.append([t, w + d + l, w, d, l, gf, ga, gf - ga, 3 * w + d])
    df = pd.DataFrame(rows, columns=["Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"])
    df = df.sort_values(["Pts", "GD", "GF"], ascending=False).reset_index(drop=True)
    df.insert(0, "Pos", range(1, 21))
    scorers = pd.DataFrame({
        "Player": [f"Player {i}" for i in range(1, 11)],
        "Team": teams[:10],
        "Goals": sorted(rng.integers(4, 12, 10).tolist(), reverse=True),
    })
    assists = pd.DataFrame({
        "Player": [f"Player {i}" for i in range(11, 21)],
        "Team": teams[:10],
        "Assists": sorted(rng.integers(2, 9, 10).tolist(), reverse=True),
    })
    return df, scorers, assists


def load_data():
    """Returns (table, scorers, assists, source_label)."""
    if os.environ.get("PL_DEMO") == "1":
        return (*_sample_data(), "DEMO — synthetic data, not actual results")
    table, source = None, None
    for fn, label in ((scrape_bbc_table, "BBC Sport"), (scrape_espn_table, "ESPN")):
        try:
            table, source = fn(), label
            break
        except Exception as e:
            print(f"[scraper] {label} failed: {e}")

    def safe(fn):
        try:
            return fn()
        except Exception as e:
            print(f"[scraper] {fn.__name__} failed: {e}")
            return None

    player_tables = safe(lambda: _get_tables(BBC_SCORERS))
    scorers = safe(lambda: _scrape_players("goals", player_tables)) if player_tables is not None else None
    assists = safe(lambda: _scrape_players("assists", player_tables)) if player_tables is not None else None
    frames, labels = [], []
    for key, frame, origin, columns in (
        ("table", table, source, ["Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"]),
        ("scorers", scorers, "BBC Sport", ["Player", "Team", "Goals"]),
        ("assists", assists, "BBC Sport", ["Player", "Team", "Assists"]),
    ):
        path = DATA_DIR / f"{key}.json"
        if frame is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            payload = {"source": origin, "fetched_at": stamp, "records": frame.to_dict("records")}
            try:
                DATA_DIR.mkdir(exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)
                frame.to_csv(DATA_DIR / f"{key}.csv", index=False, encoding="utf-8")
            except OSError as exc:
                print(f"[cache] Could not save {key}: {exc}")
            label = f"{key}: {origin}, fetched {stamp}"
        else:
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                frame = pd.DataFrame(cached["records"])[columns]
                if key == "table":
                    frame = _finish_table(frame)
                label = f"{key}: CACHED {cached['source']} ({cached['fetched_at']}); refresh failed"
            except (OSError, ValueError, KeyError, TypeError):
                frame = pd.DataFrame(columns=columns)
                label = f"{key}: unavailable — source could not be read"
        frames.append(frame)
        labels.append(label)
    return (*frames, " | ".join(labels))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        for u in (BBC_TABLE, BBC_SCORERS):
            try:
                for i, tb in enumerate(_get_tables(u)):
                    print(u, "table", i, list(tb.columns)); print(tb.head(3), "\n")
            except Exception as e:
                print(u, "ERROR", e)
        sys.exit()
    t, s, a, src = load_data()
    print(src); print(t.head()); print(s.head()); print(a.head())
