import discord
from discord.ext import tasks
import requests
import json
import os

# Botの設定（discord.Botを使用）
intents = discord.Intents.default()
bot = discord.Bot(intents=intents)

# 環境変数からAPIキーとトークンを取得（名前は固定）
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

# 起動時
@bot.event
async def on_ready():
    global config
    config = load_config()
    await bot.sync_commands()
    print(f"✅ Logged in as {bot.user}")
    check_new_videos.start()

# スラッシュコマンド: /subscribe
@bot.slash_command(description="YouTubeチャンネルの通知設定をする")
async def subscribe(ctx, youtube_channel_id: str, notify_channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    config[guild_id] = {
        "channel_id": youtube_channel_id,
        "notify_channel": notify_channel.id
    }
    save_config(config)
    await ctx.respond(
        f"✅ 通知設定完了！\nYouTubeチャンネルID: `{youtube_channel_id}`\n通知先: {notify_channel.mention}",
        ephemeral=True
    )

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
    return video["id"]["videoId"], video["snippet"]["title"]

# 定期的に動画をチェック
@tasks.loop(minutes=5)
async def check_new_videos():
    for guild_id, settings in config.items():
        channel_id = settings["channel_id"]
        notify_channel_id = settings["notify_channel"]
        try:
            video_id, title = get_latest_video_id(channel_id)
            if last_video_ids.get(guild_id) != video_id:
                last_video_ids[guild_id] = video_id
                channel = bot.get_channel(notify_channel_id)
                if channel:
                    await channel.send(f"🎥 新しい動画が公開されました！\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
        except Exception as e:
            print(f"[エラー] Guild {guild_id}: {e}")

# Bot起動
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)



