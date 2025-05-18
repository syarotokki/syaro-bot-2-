import discord
from discord.ext import tasks, commands
from discord import app_commands
import requests
import json
import os

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(bot)

# 保存用ファイル
SETTINGS_FILE = "settings.json"
NOTIFIED_FILE = "notified.json"

# 初期化
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump({}, f)
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def load_notified():
    if not os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE, 'w') as f:
            json.dump({}, f)
    with open(NOTIFIED_FILE, 'r') as f:
        return json.load(f)

def save_notified(data):
    with open(NOTIFIED_FILE, 'w') as f:
        json.dump(data, f, indent=4)

settings = load_settings()
notified = load_notified()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# 通知登録コマンド
@tree.command(name="set_notification", description="通知先チャンネルとYouTubeチャンネルIDを登録")
@app_commands.describe(channel="通知先チャンネル", youtube_channel_id="YouTubeのチャンネルID")
async def set_notification(interaction: discord.Interaction, channel: discord.TextChannel, youtube_channel_id: str):
    settings[str(interaction.guild.id)] = {
        "channel_id": channel.id,
        "youtube_channel_id": youtube_channel_id
    }
    save_settings(settings)
    await interaction.response.send_message(f"通知設定を保存しました。通知先: {channel.mention}、YouTubeチャンネルID: `{youtube_channel_id}`")

# 過去動画を一括通知
@tree.command(name="notify_past", description="過去の動画を一括で通知")
async def notify_past(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in settings:
        await interaction.response.send_message("このサーバーでは通知設定がされていません。まず /set_notification を使用してください。")
        return

    channel_id = settings[guild_id]["channel_id"]
    youtube_channel_id = settings[guild_id]["youtube_channel_id"]
    channel = bot.get_channel(channel_id)
    
    videos = get_latest_videos(youtube_channel_id, count=5)
    for video in reversed(videos):
        video_id = video['id']['videoId']
        if video['id']['kind'] == 'youtube#video':
            await channel.send(f"新しい動画が投稿されました！\nhttps://www.youtube.com/watch?v={video_id}")
        elif video['id']['kind'] == 'youtube#liveBroadcast':
            live_time = video['snippet'].get('publishedAt', '不明')
            await channel.send(f"ライブ配信が始まりました！🟢\n開始時刻: {live_time}\nhttps://www.youtube.com/watch?v={video_id}")
        notified.setdefault(guild_id, []).append(video_id)
    save_notified(notified)
    await interaction.response.send_message("過去動画の通知を完了しました。")

# 動画取得関数
def get_latest_videos(channel_id, count=1):
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults={count}"
    response = requests.get(url)
    return response.json().get("items", [])

# 定期チェック
@tasks.loop(minutes=5)
async def check_new_videos():
    for guild_id, config in settings.items():
        channel = bot.get_channel(config["channel_id"])
        videos = get_latest_videos(config["youtube_channel_id"], count=1)
        for video in videos:
            video_id = video['id'].get('videoId')
            if not video_id or video_id in notified.get(guild_id, []):
                continue

            if video['id']['kind'] == 'youtube#video':
                await channel.send(f"新しい動画が投稿されました！\nhttps://www.youtube.com/watch?v={video_id}")
            elif video['id']['kind'] == 'youtube#liveBroadcast':
                live_time = video['snippet'].get('publishedAt', '不明')
                await channel.send(f"ライブ配信が始まりました！🟢\n開始時刻: {live_time}\nhttps://www.youtube.com/watch?v={video_id}")

            notified.setdefault(guild_id, []).append(video_id)
        save_notified(notified)

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    await tree.sync()
    check_new_videos.start()

bot.run(os.getenv("DISCORD_TOKEN"))
