import discord
from discord.ext import commands, tasks
import requests
import json
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

config = load_config()
last_video_ids = {}

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

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

def get_latest_video_id(channel_id):
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
    response = requests.get(url).json()
    video = response['items'][0]
    return video['id']['videoId'], video['snippet']['title']

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
            print(f"エラー（{guild_id}）:", e)

check_new_videos.start()

bot.run(os.environ["DISCORD_TOKEN"])
