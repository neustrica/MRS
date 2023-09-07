import sqlite3

connection = sqlite3.connect('music_recs.db')

cursor = connection.cursor()

cursor.execute('''
  CREATE TABLE track_ratings (
    track_id TEXT, 
    user_id TEXT,
    rating INTEGER
  )
''')

cursor.execute('''
  CREATE TABLE album_ratings (
    album_id TEXT,
    user_id TEXT, 
    rating INTEGER
  )  
''')

cursor.execute('''
  CREATE TABLE artist_ratings (
    artist_id TEXT,
    user_id TEXT,
    rating INTEGER
  )
''')

connection.commit()
connection.close()