import os
import discord
import requests
from dotenv import load_dotenv  # use dotenv to read .env

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
    data, err = _fetch_odds_raw(nba_url)  # NEW: call with NBA URL
    if err:
        return f"Error fetching NBA odds: {err}"
    if not data:
        return "No live NBA games or odds available right now."

    # no need for team matching; API already filters NBA games
    return _render_games(data, "NBA Odds (US Only):")  # render NBA data directly

def get_college_odds() -> str:
    # use specific College Basketball endpoint instead of team-name filtering
    college_url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"  # direct NCAA odds endpoint
    data, err = _fetch_odds_raw(college_url)  # NEW: call with NCAA URL
    if err:
        return f"Error fetching College Basketball odds: {err}"
    if not data:
        return "No live College Basketball games or odds available right now."

    # no team filtering; endpoint already returns only NCAA games, this beats previously hardcoding the team names
    return _render_games(data, "College Basketball Odds (US Only):")  # render NCAA data directly


# Events
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    content = (message.content or "").strip()
    if not content.startswith("!"):
        return

    # commands
    if content.lower() == "!ping":
        return await message.channel.send("Pong!")

    if content.lower() == "!luke":
        return await message.channel.send("He a bitch ong :sob:! ")

    if content.lower() == "!clara":
        return await message.channel.send(
            "FUCK YOU! is what I would say if you weren't the most angelic woman around ever!"
        )

    if content.lower() == "!song":
        return await message.channel.send("This shit hard asf :fire:!")

    if content.lower() == "!commands":
        return await message.channel.send("ping, luke, clara, nba_odds, college_odds!")

    if content.lower() == "!odds":
        msg = get_all_basketball_odds()
        return await send_long_message(message.channel, msg)  # use splitter helper

    if content.lower() == "!nba_odds":
        msg = get_nba_odds()
        return await send_long_message(message.channel, msg)

    if content.lower() == "!college_odds":
        msg = get_college_odds()
        return await send_long_message(message.channel, msg)

# Start the client
client.run(DISCORD_TOKEN)