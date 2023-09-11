import sqlite3
import pandas as pd
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

def get_ratings():
  query = 'SELECT user_id, track_id, rating FROM track_ratings'
  df = pd.DataFrame(cursor.execute(query).fetchall(), 
                      columns=['user_id', 'track_id', 'rating'])
  connection.commit()
    
  return df

def get_top_rated_tracks(user_id):
  top_rated_tracks = cursor.execute('''
    SELECT track_id FROM track_ratings WHERE user_id = ? AND rating >= 4
  ''', (user_id,))
  connection.commit()
  return top_rated_tracks
