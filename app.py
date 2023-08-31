import csv
import asyncio
from aiogram import Dispatcher
from decimal import Decimal
import authorization
import dynamo_get_table
import telegram_bot
from Bot import bot


sp = authorization.authorize()

# Функция для получения данных
def get_data():
    table    = dynamo_get_table.get_dynamodb_table()
    response = table.scan()
    data     = response['Items']
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        data.extend(response['Items'])
    return data  

# Функция для получения рекомендаций
def recommend(track_ids, n_recs=5):
    data        = get_data()
    total_diffs = [0] * len(data)
    for track_id in track_ids:
        track_features = sp.track_audio_features(track_id)
        track_valence = Decimal(str(track_features.valence))
        track_energy = Decimal(str(track_features.energy))

        for i, item in enumerate(data):
            diff_valence    = abs(track_valence - item['mood_vec'][0])
            diff_energy     = abs(track_energy - item['mood_vec'][1])  
            total_diffs[i] += diff_valence + diff_energy

    for i, item in enumerate(data):
        item['total_diffs'] = total_diffs[i]

    sorted_data = sorted(data, key=lambda item: item['total_diffs'])[:n_recs]

    return sorted_data

def build_matrix():
  data = []

  with open('ratings.csv', 'r') as f:
      reader = csv.reader(f)
      for row in reader:
        user_id, track_id, rating = row
        data.append(row)
  users = set([row[0] for row in data]) 
  tracks = set([row[1] for row in data])
  matrix = [[0 for t in tracks] for u in users]
  for row in data:
    user_id, track_id, rating = row
    
    user_idx = list(users).index(user_id)
    track_idx = list(tracks).index(track_id)

    matrix[user_idx][track_idx] = rating
  return matrix

  # Сохранение оценки в CSV
def save_rating(user_id, track, rating):
    with open('ratings.csv', 'a') as f: 
      writer = csv.writer(f)
      writer.writerow([user_id, track['id'], rating])

dp = Dispatcher(bot)
dp = telegram_bot.start(bot, dp)

if __name__ == "__main__":
  asyncio.run(dp.start_polling())
