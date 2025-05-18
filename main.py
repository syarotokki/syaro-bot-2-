import discord
from discord.ext import commands, tasks
import os
import json
import requests
import asyncio

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
guild_obj = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DATA_FILE = "data.json"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# データの読み書き
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# YouTube API から動画を取得
def get_latest_videos(channel_id, max_results=5):
    url = (
        f"https://www.googleapis.com/youtube/v3/search?"
        f"key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults={max_results}"
    )
    response = requests.get(url)
    if response.status_code != 200:
        return []

    items = response.json().get("items", [])
    videos = []
    for item in items:
        video_id = item["id"].get("videoId")
        kind = item["id"]["kind"]
        if kind != "youtube#video":
            continue
        snippet = item["snippet"]
        title = snippet["title"]
        published = snippet["publishedAt"]
        videos.append({"id": video_id, "title": title, "published": published})
    return videos

# 新着動画の監視タスク
@tasks.loop(minutes=5)
async def check_new_videos():
    await bot.wait_until_ready()
    data = load_data()

    for guild_id, config in data.items():
        yt_channel_id = config.get("youtube_channel_id")
        notify_channel_id = config.get("notify_channel_id")
        last_video_id = config.get("last_video_id")

        if not yt_channel_id or not notify_channel_id:
            continue

        videos = get_latest_videos(yt_channel_id, max_results=1)
        if not videos:
            continue

        latest_video = videos[0]
        if latest_video["id"] != last_video_id:
            channel = bot.get_channel(int(notify_channel_id))
            if channel:
                is_live = "ライブ" in latest_video["title"] or "live" in latest_video["title"].lower()
                msg = (
                    f"📢 **ライブ配信が始まりました！**\n"
                    if is_live else "🎬 **新しい動画が投稿されました！**\n"
                )
                msg += f"{latest_video['title']}\nhttps://youtu.be/{latest_video['id']}"
                await channel.send(msg)

                data[guild_id]["last_video_id"] = latest_video["id"]
                save_data(data)

# Bot 起動時
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await tree.sync(guild=guild_obj if guild_obj else None)
        print("Slash commands synced.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    check_new_videos.start()

# /notify 設定コマンド
@tree.command(name="notify", description="通知するYouTubeチャンネルと通知先を設定します", guild=guild_obj if guild_obj else None)
async def notify(interaction: discord.Interaction, youtube_channel_id: str, notify_channel: discord.TextChannel):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        data[guild_id] = {}

    data[guild_id]["youtube_channel_id"] = youtube_channel_id
    data[guild_id]["notify_channel_id"] = str(notify_channel.id)
    data[guild_id]["last_video_id"] = ""

    save_data(data)

    await interaction.response.send_message(f"✅ 通知設定を保存しました。\nYouTubeチャンネル: `{youtube_channel_id}`\n通知先: {notify_channel.mention}")

# /notify_past 過去動画一括通知コマンド
@tree.command(name="notify_past", description="YouTubeチャンネルの過去の動画を一括通知します", guild=guild_obj if guild_obj else None)
async def notify_past(interaction: discord.Interaction):
    await interaction.response.defer()
    data = load_data()
    guild_id = str(interaction.guild.id)

    config = data.get(guild_id)
    if not config:
        await interaction.followup.send("⚠️ 通知設定がされていません。まず `/notify` コマンドで設定してください。")
        return

    yt_channel_id = config.get("youtube_channel_id")
    notify_channel_id = config.get("notify_channel_id")

    if not yt_channel_id or not notify_channel_id:
        await interaction.followup.send("⚠️ YouTubeチャンネルIDまたは通知チャンネルIDが設定されていません。")
        return

    videos = get_latest_videos(yt_channel_id, max_results=5)
    if not videos:
        await interaction.followup.send("⚠️ 動画が取得できませんでした。")
        return

    channel = bot.get_channel(int(notify_channel_id))
    if not channel:
        await interaction.followup.send("⚠️ 通知先のチャンネルが見つかりません。")
        return

    for video in reversed(videos):
        is_live = "ライブ" in video["title"] or "live" in video["title"].lower()
        msg = (
            f"📢 **ライブ配信が始まりました！**\n"
            if is_live else "🎬 **動画の紹介**\n"
        )
        msg += f"{video['title']}\nhttps://youtu.be/{video['id']}"
        await channel.send(msg)

    await interaction.followup.send(f"✅ 最新{len(videos)}件の動画を通知しました。")

bot.run(TOKEN)
