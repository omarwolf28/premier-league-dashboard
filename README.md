# Premier League Analytics

A Python web scraper and interactive Dash dashboard for the current Premier League standings and player statistics. Uses requests and pandas HTML parsing, with Plotly charts.

GitHub Actions runs the offline test suite on every push and pull request. GitHub displays this README automatically on the repository home page. The interactive dashboard requires a running Python server; GitHub Pages cannot run Dash applications.

## Run locally

Install Python 3.11 or newer from https://www.python.org/downloads/ first. In PowerShell, from this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:8050. On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` instead of the Windows executable path.

For a reproducible offline demonstration with **synthetic, fictional statistics**:

```powershell
$env:PL_DEMO = "1"
.\.venv\Scripts\python.exe app.py
```

Stop with Ctrl+C. Run `Remove-Item Env:PL_DEMO` before restarting to restore live scraping. Demo data is visibly labelled and is never written into the live cache.

## Dashboard features

- League table: sortable columns, column filters, and CSV export. Filters accept expressions such as `> 10` for points and team names for text.
- Top scorers: horizontal bar chart with a top-N slider and player/team hover details.
- Team points comparison: multi-select clubs; clearing the selection restores the top six.
- Goals by team: switch between scored, conceded, and goal difference.
- Bonus assists view and summary cards for the leader, points, goals, and club count.
- Responsive dark layout, source links, retrieval timestamps, and explicit unavailable/cached states.

## Scraping and data flow

[scraper.py](scraper.py) fetches [BBC standings](https://www.bbc.com/sport/football/premier-league/table), falling back to [ESPN standings](https://www.espn.com/soccer/standings/_/league/eng.1). It separately fetches the [BBC top-scorers page](https://www.bbc.com/sport/football/premier-league/top-scorers) once per refresh for goals and assists. If that page does not expose an assists table, that view shows unavailable.

The scraper normalizes columns, converts numerical fields, checks for 20 unique clubs, and validates played and goal-difference arithmetic. It preserves the source ranking and does not assume points always equal three times wins plus draws, since deductions are possible.

Successful datasets are stored individually as JSON with source/retrieval metadata and exported as CSV in `data/`. Failed requests use the last saved version of that dataset, clearly labelled cached with its original retrieval timestamp. Without a cache, that view is unavailable. Different datasets may have different retrieval times; timestamps describe retrieval, not the publisher's update time. The original root CSV files are legacy data with unverified provenance and are not used or overwritten.

[app.py](app.py) polls every 30 seconds while open. Network refreshes are limited to once every five minutes per server process, including manual checks. Requests have 15-second timeouts. Importing the app does not start a scraper or background thread. Use a single server process for this local project; multi-worker hosting requires a shared scheduler/cache lock.

Sources can change their HTML or block requests. Live availability is not guaranteed. Follow each site's current terms and robots guidance; this project does not bypass access restrictions. There is no season selector: live mode reads the current pages.

## Scraper and tests

```powershell
.\.venv\Scripts\python.exe scraper.py
.\.venv\Scripts\python.exe -m unittest -v
```

The offline tests cover standings validation, player parsing and ranking, cache preservation on failure, demo network isolation, the Dash layout, chart filtering, and empty-data behavior. Live scraping should also be checked locally because upstream markup can change.

Runtime validation was not performed in the authoring environment because no Python interpreter was installed.
