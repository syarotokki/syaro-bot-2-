import discord
from discord.ext import commands, tasks
import requests
import json
import os
import asyncio
from datetime import datetime, timezone

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
config = {}
last_video_ids = {}

# 設定ファイルの読み書き
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 起動時処理
@bot.event
async def on_ready():
    global config
    config = load_config()
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")
    check_new_videos.start()

# /subscribe コマンド
@bot.tree.command(name="subscribe", description="YouTubeチャンネルの通知設定をする")
@discord.app_commands.describe(
    youtube_channel_id="通知したいYouTubeチャンネルのID",
    notify_channel="通知を送るDiscordチャンネル"
)
async def subscribe(interaction: discord.Interaction, youtube_channel_id: str, notify_channel: discord.TextChannel):
    guild_id = str(interaction.guild_id)
    config[guild_id] = {
        "channel_id": youtube_channel_id,
        "notify_channel": notify_channel.id
    }
    save_config(config)
    await interaction.response.send_message(
        f"✅ 通知設定完了！\nYouTubeチャンネルID: `{youtube_channel_id}`\n通知先: {notify_channel.mention}",
        ephemeral=True
    )

# 動画詳細取得（動画かライブか判別）
def get_video_details(video_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?key={YOUTUBE_API_KEY}&id={video_id}&part=snippet,liveStreamingDetails"
    )
    res = requests.get(url).json()
    if "items" not in res or not res["items"]:
        return None
    item = res["items"][0]
    is_live = "liveStreamingDetails" in item
    start_time = item.get("liveStreamingDetails", {}).get("actualStartTime")
    title = item["snippet"]["title"]
    return {
        "video_id": video_id,
        "title": title,
        "is_live": is_live,
        "start_time": start_time
    }

# 通知送信処理
async def send_video_notification(channel, video_info):
    video_url = f"https://www.youtube.com/watch?v={video_info['video_id']}"
    if video_info["is_live"]:
        # ライブ配信通知
        start_time = video_info.get("start_time")
        if start_time:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).astimezone(timezone.utc)
            formatted_time = dt.strftime('%Y-%m-%d %H:%M UTC')
            await channel.send(f"🔴 ライブ配信が始まりました！\n**{video_info['title']}**\n開始時刻: {formatted_time}\n{video_url}")
        else:
            await channel.send(f"🔴 ライブ配信が始まりました！\n**{video_info['title']}**\n{video_url}")
    else:
        # 通常動画通知
        await channel.send(f"🎥 新しい動画が公開されました！\n**{video_info['title']}**\n{video_url}")

# 最新動画ID取得
def get_latest_video_id(channel_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id"
        f"&order=date&maxResults=1&type=video"
    )
    res = requests.get(url).json()
    if "items" not in res or not res["items"]:
        raise Exception("動画が見つかりません")
    video = res["items"][0]
    return video["id"]["videoId"]

# 定期チェック
@tasks.loop(minutes=5)
async def check_new_videos():
    for guild_id, settings in config.items():
        channel_id = settings["channel_id"]
        notify_channel_id = settings["notify_channel"]
        try:
            video_id = get_latest_video_id(channel_id)
            if last_video_ids.get(guild_id) != video_id:
                last_video_ids[guild_id] = video_id
                video_info = get_video_details(video_id)
                if video_info:
                    channel = bot.get_channel(notify_channel_id)
                    if channel:
                        await send_video_notification(channel, video_info)
        except Exception as e:
            print(f"[エラー] Guild {guild_id}: {e}")

# /notify_past コマンド
@bot.tree.command(name="notify_past", description="過去の動画・配信を一括通知（最大500件）")
async def notify_past(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id not in config:
        await interaction.response.send_message("⚠️ このサーバーではまだ `/subscribe` で通知設定がされていません。", ephemeral=True)
        return

    await interaction.response.send_message("📤 通知を開始します。大量のメッセージが送信される可能性があります。", ephemeral=True)

    channel_id = config[guild_id]["channel_id"]
    notify_channel_id = config[guild_id]["notify_channel"]
    notify_channel = bot.get_channel(notify_channel_id)

    all_videos = []
    page_token = None
    max_total = 500
    while True:
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id"
            f"&order=date&maxResults=50&type=video"
        )
        if page_token:
            url += f"&pageToken={page_token}"

        response = requests.get(url).json()
        items = response.get("items", [])
        page_token = response.get("nextPageToken")

        for item in items:
            if "videoId" not in item["id"]:
                continue
            video_id = item["id"]["videoId"]
            detail = get_video_details(video_id)
            if detail:
                all_videos.append(detail)

        if not page_token or len(all_videos) >= max_total:
            break

    for video in reversed(all_videos):
        await send_video_notification(notify_channel, video)
        await asyncio.sleep(1)

    await notify_channel.send(f"✅ 通知完了（{len(all_videos)}件）")

# 実行
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)


