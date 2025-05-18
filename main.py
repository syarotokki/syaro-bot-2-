from flask import Flask
import threading
import discord
from discord.ext import tasks
from discord import app_commands
import requests
import os

TOKEN = os.environ["DISCORD_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

flask_thread = threading.Thread(target=run_flask)
flask_thread.start()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

subscriptions = {}
latest_video_ids = {}

def get_latest_video(channel_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id"
        f"&order=date&maxResults=1"
    )
    response = requests.get(url).json()
    if "items" not in response or not response["items"]:
        return None, None
    video = response["items"][0]
    video_id = video["id"].get("videoId")
    title = video["snippet"]["title"]
    return video_id, title

@tree.command(name="notify", description="このチャンネルにYouTubeの新着動画を通知します")
async def notify(interaction: discord.Interaction, youtube_channel_id: str):
    channel_id = interaction.channel_id
    subscriptions[channel_id] = youtube_channel_id
    await interaction.response.send_message(f"✅ 通知を登録しました！（{youtube_channel_id}）")

@tasks.loop(minutes=5)
async def check_new_videos():
    for discord_channel_id, youtube_channel_id in subscriptions.items():
        video_id, title = get_latest_video(youtube_channel_id)
        if not video_id:
            continue
        if latest_video_ids.get(discord_channel_id) == video_id:
            continue

        latest_video_ids[discord_channel_id] = video_id
        channel = client.get_channel(discord_channel_id)
        if channel:
            await channel.send(
                f"🎥 新しい動画が公開されました！\n**{title}**\nhttps://www.youtube.com/watch?v={video_id}"
            )

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is ready as {client.user}")
    check_new_videos.start()

client.run(TOKEN)
