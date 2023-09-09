import sqlite3

connection = sqlite3.connect('music_recs.db')
cursor = connection.cursor()
cursor.execute('''
  CREATE TABLE IF NOT EXISTS listened_tracks (
    track_id integer,
    user_id integer,
    rating integer
  )
''')

cursor.execute('''
  CREATE TABLE IF NOT EXISTS track_ratings (
    track_id TEXT, 
    user_id TEXT,
    rating INTEGER
  )
''')

cursor.execute('''
  CREATE TABLE IF NOT EXISTS album_ratings (
    album_id TEXT,
    user_id TEXT, 
    rating INTEGER
  )  
''')

cursor.execute('''
  CREATE TABLE IF NOT EXISTS artist_ratings (
    artist_id TEXT,
    user_id TEXT,
    rating INTEGER
  )
''')
cursor.execute(''' 
  CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks ON listened_tracks(user_id, track_id)
''')

cursor.execute('''
  CREATE UNIQUE INDEX IF NOT EXISTS idx_track_ratings ON track_ratings(user_id, track_id)  
''')

# и т.д. для каждой таблицы
connection.commit()
connection.close()