import sqlite3

connection = sqlite3.connect('music_recs.db') 
cursor = connection.cursor()
def save_track_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT OR IGNORE INTO track_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))
  
  connection.commit()

def save_album_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT OR IGNORE INTO album_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))
  
  connection.commit()

def save_artist_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT OR IGNORE INTO artist_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))

def save_track(user_id, track_id):
  query = "INSERT OR IGNORE INTO listened_tracks (user_id, track_id) VALUES (?, ?)"
  cursor.execute(query, (user_id, track_id))
  connection.commit()

def get_user_ratings(user_id):
  ratings = {}
  
  # получение рейтингов пользователя из всех таблиц 
  
  return ratings
