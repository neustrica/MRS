import sqlite3

connection = sqlite3.connect('music_recs.db')  
cursor = connection.cursor()
def save_track_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT INTO track_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))
  
  connection.commit()
def save_album_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT INTO album_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))
  
  connection.commit()
def save_artist_rating(user_id, track_id, rating):
  cursor.execute('''
    INSERT INTO artist_ratings (user_id, track_id, rating)
    VALUES (?, ?, ?)
  ''', (user_id, track_id, rating))

def get_user_ratings(user_id):
  ratings = {}
  
  # получение рейтингов пользователя из всех таблиц 
  
  return ratings
