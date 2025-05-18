import discord
from discord.ext import commands, tasks
import requests
import datetime

# Botの初期設定
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# YouTube APIの設定
YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY"
NOTIFY_CHANNELS = {}  # guild_id: {"channel_id": int, "youtube_channel_id": str}
LAST_VIDEO_IDS = {}   # guild_id: 最後に通知した動画ID

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_latest_videos.start()

# 通知先とYouTubeチャンネルIDを設定するコマンド
@bot.slash_command(name="set_notification", description="通知先チャンネルとYouTubeチャンネルIDを登録")
async def set_notification(ctx: discord.ApplicationContext, youtube_channel_id: str):
    NOTIFY_CHANNELS[ctx.guild.id] = {
        "channel_id": ctx.channel.id,
        "youtube_channel_id": youtube_channel_id,
    }
    await ctx.respond(f"✅ 通知設定完了！\nYouTubeチャンネルID: `{youtube_channel_id}`\n通知チャンネル: <#{ctx.channel.id}>")

# 過去の動画を一括通知するコマンド
@bot.slash_command(name="notify_past", description="過去の動画を一括で通知")
async def notify_past(ctx: discord.ApplicationContext):
    guild_id = ctx.guild.id
    if guild_id not in NOTIFY_CHANNELS:
        await ctx.respond("❗ まず /set_notification で通知設定をしてください。")
        return

    youtube_channel_id = NOTIFY_CHANNELS[guild_id]["youtube_channel_id"]
    videos = fetch_youtube_videos(youtube_channel_id, max_results=5)

    if not videos:
        await ctx.respond("動画が見つかりませんでした。")
        return

    await ctx.respond("📢 過去動画を通知します！")
    channel = bot.get_channel(NOTIFY_CHANNELS[guild_id]["channel_id"])

    for video in reversed(videos):
        if is_live_video(video["id"]):
            start_time = get_live_start_time(video["id"])
            await channel.send(
                f"🔴 **ライブ配信が始まりました！**\nタイトル: {video['title']}\n開始時刻: {start_time}\nURL: https://youtu.be/{video['id']}"
            )
        else:
            await channel.send(
                f"📺 **動画公開**\nタイトル: {video['title']}\n公開日: {video['published_at']}\nURL: https://youtu.be/{video['id']}"
            )

# 定期的に最新動画をチェック
@tasks.loop(minutes=5)
async def check_latest_videos():
    for guild_id, settings in NOTIFY_CHANNELS.items():
        youtube_channel_id = settings["youtube_channel_id"]
        channel = bot.get_channel(settings["channel_id"])

        videos = fetch_youtube_videos(youtube_channel_id, max_results=1)
        if not videos:
            continue

        latest = videos[0]
        latest_id = latest["id"]

        if LAST_VIDEO_IDS.get(guild_id) == latest_id:
            continue  # 同じ動画は通知しない

        LAST_VIDEO_IDS[guild_id] = latest_id

        if is_live_video(latest_id):
            start_time = get_live_start_time(latest_id)
            await channel.send(
                f"🔴 **ライブ配信が始まりました！**\nタイトル: {latest['title']}\n開始時刻: {start_time}\nURL: https://youtu.be/{latest_id}"
            )
        else:
            await channel.send(
                f"📢 **新着動画**\nタイトル: {latest['title']}\n公開日: {latest['published_at']}\nURL: https://youtu.be/{latest_id}"
            )

# YouTube API から動画情報取得
def fetch_youtube_videos(channel_id, max_results=1):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "channelId": channel_id,
        "part": "snippet",
        "order": "date",
        "maxResults": max_results,
        "type": "video",
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print("YouTube API error:", response.text)
        return []

    items = response.json().get("items", [])
    return [
        {
            "id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
        }
        for item in items
    ]

# ライブ配信かどうかを判定
def is_live_video(video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YOUTUBE_API_KEY,
        "id": video_id,
        "part": "liveStreamingDetails",
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return False
    items = response.json().get("items", [])
    return "liveStreamingDetails" in items[0] if items else False

# ライブ配信の開始時間を取得
def get_live_start_time(video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YOUTUBE_API_KEY,
        "id": video_id,
        "part": "liveStreamingDetails",
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return "不明"

    items = response.json().get("items", [])
    if not items:
        return "不明"

    details = items[0].get("liveStreamingDetails", {})
    start = details.get("actualStartTime")
    if start:
        try:
            dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return start
    return "不明"

# Botの起動（環境変数や秘密情報はRenderで設定）
bot.run("YOUR_DISCORD_BOT_TOKEN")

