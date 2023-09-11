import random
import database
import models
from authorization import authorize

# Массив для хранения id треков  
track_ids = [] 
spotify = authorize()

# Генерируем случайные запросы
queries = ['%25a%25', '%25b%25', '%25c%25', '%25z%25', '%25e%25', '%25o%25', '%25i%25', '%25d%25', '%25x%25', '%25l%25', '%25r%25', '%25n%25',]

for query in queries:
  offset = random.randint(0, 1000)
  results = spotify.search(query, offset=offset, limit=50)[0]

  for track in results.items:
    if track.id not in track_ids:
      track_ids.append(track.id)

# Обрезаем до 500 элементов    
track_ids = track_ids[:500] 

# Генерируем данные
for track_id in track_ids:
  user_id = random.randint(0, 99)
  rating = random.randint(1, 5)
  database.save_track_rating(user_id=user_id, track_id=track_id, rating=rating)

