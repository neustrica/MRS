from authorization import authorize, bot, youtube
from telegram_bot import start
import asyncio
from aiogram import Dispatcher
import yt_dlp
import os

sp = authorize()

def search_track(query):

  res = sp.search(query, limit=1)
  
  if res[0].items:
    track = res[0].items[0]
    return {
      'id': track.id,
      'name': track.name,  
      'artist': track.artists[0].name
    }

def get_recommendations(track_id):
  results = sp.recommendations(seed_tracks=[track_id], limit=5)
  recommended_tracks = []
  
  for track in results.tracks:
    recommended_tracks.append({
      'id': track.id,
      'name': track.name,
      'artist': track.artists[0].name
    })

  return recommended_tracks


def youtube_search(query):

  request = youtube.search().list(part="snippet", q=query, maxResults=1)

  response = request.execute()
  
  return response['items'][0]


def download_audio(url):

  ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': 'temp.%(ext)s', 
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192', 
    }],
    'keepvideo': True 
  }
  
  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=True)

  title = info['title']
  os.rename('temp.mp3', f'{title}.mp3')

  return f'{title}.mp3'
# возвращает путь до скачанного файла

dp = Dispatcher(bot)
start(bot, dp)
if __name__ == '__main__':
  asyncio.run(dp.start_polling())