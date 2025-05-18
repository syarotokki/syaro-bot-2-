import discord
from discord.ext import tasks, commands
from discord import app_commands
import requests
import json
import os

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(bot)

# 設定保存用
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump({}, f)

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

# チャンネルごとの最新動画ID記録
last_video_ids = {}

YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY"  # ←★ここにYouTube APIキーを入れてください

@tree.command(name="set_notification", description="通知先チャンネルとYouTubeチャンネルIDを登録")
@app_commands.describe(channel="通知先チャンネル", youtube_channel_id="YouTubeチャンネルID")
async def set_notification(interaction: discord.Interaction, channel: discord.TextChannel, youtube_channel_id: str):
    config = load_config()
    config[str(interaction.guild.id)] = {
        "channel_id": channel.id,
        "youtube_channel_id": youtube_channel_id
    }
    save_config(config)
    await interaction.response.send_message(f"通知先チャンネルを {channel.mention} に設定しました。", ephemeral=True)

@tree.command(name="notify_past", description="過去の動画を一括で通知")
async def notify_past(interaction: discord.Interaction):
    config = load_config()
    guild_config = config.get(str(interaction.guild.id))
    if not guild_config:
        await interaction.response.send_message("まずは /set_notification で通知先を設定してください。", ephemeral=True)
        return

    youtube_channel_id = guild_config["youtube_channel_id"]
    channel = bot.get_channel(guild_config["channel_id"])

    video_infos = fetch_videos(youtube_channel_id)
    if not video_infos:
        await interaction.response.send_message("動画が見つかりませんでした。", ephemeral=True)
        return

    for video in reversed(video_infos):
        await channel.send(format_video_message(video))
    await interaction.response.send_message("過去の動画を通知しました。", ephemeral=True)

def fetch_videos(channel_id, max_results=5):
    url = (
        f"https://www.googleapis.com/youtube/v3/search?"
        f"key={YOUTUBE_API_KEY}&channelId={channel_id}"
        f"&part=snippet,id&order=date&maxResults={max_results}"
    )
    response = requests.get(url)
    if response.status_code != 200:
        return []

    data = response.json()
    videos = []
    for item in data.get("items", []):
        video_id = item["id"].get("videoId")
        if not video_id:
            continue
        title = item["snippet"]["title"]
        published_at = item["snippet"]["publishedAt"]
        is_live = "[ライブ]" in title or "ライブ" in title or "live" in title.lower()
        videos.append({
            "id": video_id,
            "title": title,
            "published_at": published_at,
            "is_live": is_live
        })
    return videos

def format_video_message(video):
    url = f"https://www.youtube.com/watch?v={video['id']}"
    if video["is_live"]:
        return f"🔴 **ライブ配信が始まりました！**\n{video['title']}\n開始時刻: <t:{int(parse_published_at(video['published_at']))}:F>\n{url}"
    else:
        return f"📢 **新しい動画が投稿されました！**\n{video['title']}\n{url}"

def parse_published_at(iso_time):
    import datetime
    dt = datetime.datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    return int(dt.timestamp())

@tasks.loop(minutes=3)
async def check_new_videos():
    config = load_config()
    for guild_id, info in config.items():
        youtube_channel_id = info["youtube_channel_id"]
        channel = bot.get_channel(info["channel_id"])
        if not channel:
            continue

        videos = fetch_videos(youtube_channel_id, max_results=1)
        if not videos:
            continue

        latest_video = videos[0]
        if last_video_ids.get(guild_id) != latest_video["id"]:
            last_video_ids[guild_id] = latest_video["id"]
            await channel.send(format_video_message(latest_video))

@bot.event
async def on_ready():
    await tree.sync()
    print(f"ログインしました: {bot.user}")
    check_new_videos.start()

bot.run("YOUR_DISCORD_TOKEN")  # ←★ここにDiscord Bot Tokenを入れてください
