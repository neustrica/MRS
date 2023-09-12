from authorization import authorize, bot, youtube
from telegram_bot import start
import asyncio
from aiogram import Dispatcher
import pandas as pd
import models
from sklearn.metrics.pairwise import cosine_similarity
from database import get_ratings, get_top_rated_tracks
import yt_dlp
import os


sp = authorize()
def get_track_info(track_id):
  track_info = sp.track(track_id)
  track_name = track_info.name
  artists = track_info.artists
  artist_names = [artist.name for artist in artists]
      
  # Создание словаря с информацией о треке
  track_data = {
    'track_name': track_name,
    'artist_names': artist_names,
    'track_id': track_id
  }
  return track_data

def search_track(query):

  res = sp.search(query, limit=1)
  
  if res[0].items:
    track = res[0].items[0]
    return {
      'id': track.id,
      'name': track.name,  
      'artist': track.artists[0].name
    }

def get_similar(track_id):
  results = sp.recommendations(track_ids=track_id, limit=1)
  recommended_tracks = []
  
  for track in results.tracks:
    recommended_tracks.append({
      'id': track.id
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

# Функция для получения похожих пользователей
def find_similar_users(df, user_id, user_sim, k=5):
  user_index = df[df['user_id'] == user_id].index[0]
  user_sim_scores = user_sim[user_index]
  top_similar_users = user_sim_scores.argsort()[::-1][:k]
  similar_user_ids = df.iloc[top_similar_users]['user_id'].tolist()
  return similar_user_ids

# Функция для генерации рекомендаций
def generate_recs(user_id, k=5):
  # Загружаем данные из БД 
  df = get_ratings()
  top_tracks = get_top_rated_tracks(user_id=user_id)

  similar_tracks = []
  for track in top_tracks:
    similar_tracks += get_similar(track) 
  user_id = int(user_id)

  # Преобразуем в матрицу пользователей-треков
  pivot_table = df.pivot(index='user_id', columns='track_id', values='rating').fillna(0)
  # Вычисляем матрицу сходства    
  user_sim = cosine_similarity(pivot_table)
  # Находим похожих пользователей
  similar_users = find_similar_users(df, user_id, user_sim, k)  
  # Среднее рейтингов похожих пользователей 
  scores = pivot_table.loc[similar_users].mean(axis=0)
  # Сортируем и возвращаем топ-5
  scores = scores.sort_values(ascending=False)[:5].index.values
  # Сортируем и сохраняем рекомендации в словарь с популярностью
  recommendations = {}
  for track in scores:
    popularity = sp.track(track).popularity
    recommendations[track] = popularity

  # Добавляем похожие треки в словарь рекомендаций
  for track in similar_tracks:
    track = track['id']
    popularity = sp.track(track_id=track).popularity
    recommendations[track] = popularity

  # Сортируем словарь по популярности и выбираем топовые рекомендации
  top_recommendations = sorted(recommendations.items(), key=lambda x: x[1], reverse=True)[:5]
  recs = []

  for track_id, popularity in top_recommendations:
      track_data = get_track_info(track_id)
      # Добавление информации в список top_recommendations
      recs.append(track_data)
  return recs
dp = Dispatcher(bot)
start(bot, dp)
if __name__ == '__main__':
  asyncio.run(dp.start_polling())