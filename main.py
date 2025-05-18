import discord
from discord.ext import commands, tasks
import requests
import json
import os
from datetime import datetime, timezone

# Botの設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 環境変数からAPIキーとトークンを取得
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

# スラッシュコマンド: /subscribe
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

# スラッシュコマンド: /notify_past
@bot.tree.command(name="notify_past", description="過去の動画を一括で通知する")
async def notify_past(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id not in config:
        await interaction.response.send_message("❌ このサーバーには通知設定がされていません。", ephemeral=True)
        return

    youtube_channel_id = config[guild_id]["channel_id"]
    notify_channel = bot.get_channel(config[guild_id]["notify_channel"])

    url = (
        f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}"
        f"&channelId={youtube_channel_id}&part=snippet,id&type=video&order=date&maxResults=5"
    )
    response = requests.get(url).json()
    if "items" not in response:
        await interaction.response.send_message("❌ 動画情報の取得に失敗しました。", ephemeral=True)
        return

    await interaction.response.send_message("🕐 過去の動画を通知中...", ephemeral=True)

    for item in reversed(response["items"]):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        is_live = "liveBroadcastContent" in item["snippet"] and item["snippet"]["liveBroadcastContent"] == "live"
        if is_live:
            published_at = item["snippet"]["publishedAt"]
            dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            jst = dt.astimezone(timezone.utc).astimezone()
            await notify_channel.send(f"🔴 ライブ配信が始まりました！\n**{title}**\n開始時刻: {jst.strftime('%Y/%m/%d %H:%M')}\nhttps://www.youtube.com/watch?v={video_id}")
        else:
            await notify_channel.send(f"🎥 過去の動画: **{title}**\nhttps://www.youtube.com/watch?v={video_id}")

# 最新動画を取得
def get_latest_video_id(channel_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id"
        f"&order=date&maxResults=1&type=video"
    )
    response = requests.get(url).json()
    if "items" not in response or not response["items"]:
        raise Exception("動画が見つかりません")
    video = response["items"][0]
    video_id = video["id"]["videoId"]
    title = video["snippet"]["title"]
    is_live = "liveBroadcastContent" in video["snippet"] and video["snippet"]["liveBroadcastContent"] == "live"
    published_at = video["snippet"].get("publishedAt", None)
    return video_id, title, is_live, published_at

# 定期的に動画をチェック
@tasks.loop(minutes=5)
async def check_new_videos():
    for guild_id, settings in config.items():
        channel_id = settings["channel_id"]
        notify_channel_id = settings["notify_channel"]
        try:
            video_id, title, is_live, published_at = get_latest_video_id(channel_id)
            if last_video_ids.get(guild_id) != video_id:
                last_video_ids[guild_id] = video_id
                channel = bot.get_channel(notify_channel_id)
                if channel:
                    if is_live:
                        dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        jst = dt.astimezone()
                        await channel.send(f"🔴 ライブ配信が始まりました！\n**{title}**\n開始時刻: {jst.strftime('%Y/%m/%d %H:%M')}\nhttps://www.youtube.com/watch?v={video_id}")
                    else:
                        await channel.send(f"🎥 新しい動画が公開されました！\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
        except Exception as e:
            print(f"[エラー] Guild {guild_id}: {e}")

# 実行
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)



