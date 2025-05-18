import discord
from discord.ext import commands, tasks
import requests
import json
import os

# Botの設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 環境変数からAPIキーとトークンを取得
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
config = {}
last_video_ids = {}  # 最新動画IDを保持（ギルド毎）

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

# /unsubscribe - 通知解除
@bot.tree.command(name="unsubscribe", description="YouTube通知設定を解除する")
async def unsubscribe(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id in config:
        del config[guild_id]
        save_config(config)
        await interaction.response.send_message("✅ 通知設定を解除しました。", ephemeral=True)
    else:
        await interaction.response.send_message("⚠ 通知設定が存在しません。", ephemeral=True)

# /list - 登録チャンネル表示
@bot.tree.command(name="list", description="現在通知設定されているYouTubeチャンネルを確認する")
async def list_subscriptions(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id in config:
        channel_id = config[guild_id]["channel_id"]
        notify_channel_id = config[guild_id]["notify_channel"]
        await interaction.response.send_message(
            f"🔔 登録チャンネルID: `{channel_id}`\n通知チャンネル: <#{notify_channel_id}>", ephemeral=True
        )
    else:
        await interaction.response.send_message("⚠ 通知設定がありません。", ephemeral=True)

# /notify_all - 最新10件を一気に通知
@bot.tree.command(name="notify_all", description="最新のYouTube動画を一気に通知する")
async def notify_all(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    if guild_id not in config:
        await interaction.followup.send("⚠ 通知設定が存在しません。", ephemeral=True)
        return

    settings = config[guild_id]
    channel_id = settings["channel_id"]
    notify_channel_id = settings["notify_channel"]
    try:
        videos = get_latest_videos(channel_id, max_results=10)
        channel = bot.get_channel(notify_channel_id)
        if channel:
            for video_id, title, live_status in reversed(videos):
                if live_status == "live":
                    await channel.send(f"🔴 **ライブ配信開始！**\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
                elif live_status == "upcoming":
                    await channel.send(f"🟠 **ライブ配信予定！**\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
                else:
                    await channel.send(f"🎥 新しい動画が公開されました！\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
            last_video_ids[guild_id] = videos[0][0]  # 最新IDを保存
        await interaction.followup.send("✅ 一括通知が完了しました。", ephemeral=True)
    except Exception as e:
        print(f"[エラー] notify_all: {e}")
        await interaction.followup.send("❌ 通知中にエラーが発生しました。", ephemeral=True)

# 最新動画を取得
def get_latest_videos(channel_id, max_results=1):
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id"
        f"&order=date&maxResults={max_results}&type=video"
    )
    response = requests.get(url).json()
    if "items" not in response or not response["items"]:
        raise Exception("動画が見つかりません")
    videos = []
    for item in response["items"]:
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        live_status = item["snippet"].get("liveBroadcastContent", "none")  # live, upcoming, none のどれか
        videos.append((video_id, title, live_status))
    return videos

# 定期的に動画をチェック
@tasks.loop(minutes=5)
async def check_new_videos():
    for guild_id, settings in config.items():
        channel_id = settings["channel_id"]
        notify_channel_id = settings["notify_channel"]
        try:
            videos = get_latest_videos(channel_id)
            video_id, title, live_status = videos[0]
            if last_video_ids.get(guild_id) != video_id:
                last_video_ids[guild_id] = video_id
                channel = bot.get_channel(notify_channel_id)
                if channel:
                    if live_status == "live":
                        await channel.send(f"🔴 **ライブ配信開始！**\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
                    elif live_status == "upcoming":
                        await channel.send(f"🟠 **ライブ配信予定！**\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
                    else:
                        await channel.send(f"🎥 新しい動画が公開されました！\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}")
        except Exception as e:
            print(f"[エラー] Guild {guild_id}: {e}")

# 実行
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

