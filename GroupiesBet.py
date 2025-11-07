import os
import discord
import requests
from dotenv import load_dotenv  # use dotenv to read .env
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

load_dotenv()  # load variables from a .env file in this folder

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # required to read messages 
client = discord.Client(intents=intents)

# pull secrets from environment 
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
ODDS_API_KEY   = os.environ.get("ODDS_API_KEY")

# fail early with a clear message if secrets are missing
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set. Put it in .env or your environment.")
if not ODDS_API_KEY:
    raise RuntimeError("ODDS_API_KEY is not set. Put it in .env or your environment.")

BASE_URL = "https://api.the-odds-api.com/v4/sports/basketball/odds"


# Helpers 
async def send_long_message(channel: discord.abc.Messageable, text: str):
    """Send text split into <=2000 char chunks (Discord limit)."""
    if not text:  # guard against empty strings
        text = "No data available."

    if text.startswith("```") and text.endswith("```"): 
        body = text[3:-3]
        # 1900 leaves room to re-add ``` on each chunk without hitting 2000
        while body:
            chunk = body[:1900]
            await channel.send(f"```{chunk}```")  # wrap each chunk in its own code fence
            body = body[1900:]
        return

    # plain-text splitting 
    while text:
        await channel.send(text[:2000])
        text = text[2000:]

def _render_games(games, title: str) -> str:
    """Render a list of game dicts into a Discord-friendly code block."""
    lines = [f"```{title}"]
    added = 0
    for game in games:
        home = game.get("home_team", "Unknown Home")
        away = game.get("away_team", "Unknown Away")
        bookmakers = game.get("bookmakers") or []
        if not bookmakers:
            continue
        try:
            market = bookmakers[0]["markets"][0]
            outcomes = market["outcomes"]
            home_odds = outcomes[0]["price"]
            away_odds = outcomes[1]["price"]
        except (KeyError, IndexError, TypeError):
            continue

        lines.append(f"\n🏀 {home} 🆚 {away}")
        lines.append(f"➡ {home}: {home_odds} | {away}: {away_odds}")
        added += 1
        if added >= 15:  # keep messages readable
            break

    lines.append("```")
    rendered = "\n".join(lines)
    return rendered if rendered.strip() != f"```{title}```" else "No games/odds available at the moment."

def _fetch_odds_raw(sport_url=BASE_URL):  # parameter for specific sport endpoints
    """Synchronous HTTP call (kept requests for minimal changes)."""
    # pass sensitive values via params
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h"} 
    try:
        resp = requests.get(sport_url, params=params, timeout=15)  # timeout + params
    except requests.RequestException as e:
        return None, f"Network error contacting Odds API: {e}"
    if resp.status_code != 200:
        return None, f"Odds API error: HTTP {resp.status_code}"
    try:
        return resp.json(), None
    except ValueError:
        return None, "Odds API returned invalid JSON."

# parse commence_time safely and localize to America/Chicago
def _parse_start(ts: str) -> datetime:
    """Convert ISO timestamp from API to timezone-aware datetime (UTC).""" 
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def _format_local(dt_utc: datetime) -> str:
    """Format a UTC datetime in America/Chicago for display."""
    local = dt_utc.astimezone(ZoneInfo("America/Chicago"))
    return local.strftime("%a %b %d, %I:%M %p")

def _filter_and_group_by_day(data, days_ahead: int = 3, title: str = "Games"):
    """
    Build a compact schedule for today + next N-1 days.
    Shows 'LIVE' for games that already started; otherwise shows local start time.
    """
    if not data:
        return "No games found."

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    # group: date_key -> list of (label, away, home)
    buckets = {}
    for g in data:
        ts = g.get("commence_time")
        if not ts:
            continue
        start = _parse_start(ts)
        if start > end:
            continue

        away = g.get("away_team", "Away")
        home = g.get("home_team", "Home")

        label = "LIVE" if start <= now else _format_local(start)
        day_key = _format_local(start).split(",")[0]  # e.g., "Thu" 

        buckets.setdefault(day_key, []).append((label, away, home))

    if not buckets:
        return "No games within the next 3 days."

    # render nicely with day headers
    lines = [f"```{title} (Today + 2 days)"]
    for day in buckets:
        lines.append(f"\n=== {day} ===")
        for label, away, home in buckets[day]:
            prefix = "🔴" if label == "LIVE" else "🕒"
            lines.append(f"{prefix} {away} @ {home} — {label}")
    lines.append("```")
    return "\n".join(lines)

def get_all_basketball_odds() -> str:
    data, err = _fetch_odds_raw()
    if err:
        return f"Error fetching odds: {err}"
    if not data:
        return "No live basketball games or odds available right now."
    return _render_games(data, "Basketball Odds (US Only):")

def get_nba_odds() -> str:
    # use specific NBA endpoint instead of team-name filtering
    nba_url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"  # direct NBA odds endpoint
    data, err = _fetch_odds_raw(nba_url)  # call with NBA URL
    if err:
        return f"Error fetching NBA odds: {err}"
    if not data:
        return "No live NBA games or odds available right now."

    # no need for team matching; API already filters NBA games
    return _render_games(data, "NBA Odds (US Only):")  # render NBA data directly

def get_college_odds() -> str:
    # use specific College Basketball endpoint instead of team-name filtering
    college_url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"  # direct NCAA odds endpoint
    data, err = _fetch_odds_raw(college_url)  # call with NCAA URL
    if err:
        return f"Error fetching College Basketball odds: {err}"
    if not data:
        return "No live College Basketball games or odds available right now."

    # no team filtering; endpoint already returns only NCAA games
    return _render_games(data, "College Basketball Odds (US Only):")  # render NCAA data directly

# schedule helpers (3-day window)
def get_all_games_window(days: int = 3) -> str:
    data, err = _fetch_odds_raw()  # all basketball
    if err:
        return f"Error fetching games: {err}"
    return _filter_and_group_by_day(data, days_ahead=days, title="Basketball Schedule")

def get_nba_games_window(days: int = 3) -> str:
    url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds" 
    data, err = _fetch_odds_raw(url) 
    if err:
        return f"Error fetching NBA games: {err}"
    return _filter_and_group_by_day(data, days_ahead=days, title="NBA Schedule")

def get_college_games_window(days: int = 3) -> str:
    url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
    data, err = _fetch_odds_raw(url)
    if err:
        return f"Error fetching College games: {err}"
    return _filter_and_group_by_day(data, days_ahead=days, title="College Basketball Schedule")

# Events
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    content = (message.content or "").strip()
    if not content.startswith("!G"):
        return

    # commands
    if content.lower() == "!G ping":
        return await message.channel.send("Pong!")

    if content.lower() == "!G commands":
        return await message.channel.send("ping, games, nba_games, college_games, nba_odds, college_odds! (make sure to add a space between !G and the command you run)")

    if content.lower() == "!G odds":
        msg = get_all_basketball_odds()
        return await send_long_message(message.channel, msg)  # use splitter helper

    if content.lower() == "!G nba_odds":
        msg = get_nba_odds()
        return await send_long_message(message.channel, msg)

    if content.lower() == "!G college_odds":
        msg = get_college_odds()
        return await send_long_message(message.channel, msg)

    # calendars (3-day window). Shows LIVE + upcoming with local times (America/Chicago).
    if content.lower() == "!G games":
        msg = get_all_games_window(days=3)
        return await send_long_message(message.channel, msg)

    if content.lower() == "!G nba_games":
        msg = get_nba_games_window(days=3) 
        return await send_long_message(message.channel, msg)

    if content.lower() == "!G college_games":
        msg = get_college_games_window(days=3) 
        return await send_long_message(message.channel, msg) 

# Start the client
client.run(DISCORD_TOKEN)