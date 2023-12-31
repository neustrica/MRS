#################
## PREPARATION ##
#################

# Import modules
import sys
sys.path.append("../spotify_api_web_app")
import src.authorization as authorization
import pandas as pd
from tqdm import tqdm
import time

# Authorize and call access object "sp"
sp = authorization.authorize()

# Get all genres
genres = sp.recommendation_genre_seeds()

# Set number of recommendations per genre
n_recs = 15

# Initiate a dictionary with all the information you want to crawl
data_dict = {"id":[], "genre":[], "track_name":[], "artist_name":[],
             "valence":[], "energy":[], "danceability":[], "liveness":[],
             "acousticness":[], "speechiness":[]}

################
## CRAWL DATA ##
################

# Get recs for every genre
for g in tqdm(genres):
    
    # Get n recommendations
    recs = sp.recommendations(genres = [g], limit = n_recs)
    # json-like string to dict
    recs = eval(recs.model_dump_json().replace("null", "-999").replace("false", "False").replace("true", "True"))["tracks"]
    
    # Crawl data from each track
    for track in recs:
        # ID and Genre
        data_dict["id"].append(track["id"])
        data_dict["genre"].append(g)
        # Metadata
        track_meta = sp.track(track["id"])
        data_dict["track_name"].append(track_meta.name)
        data_dict["artist_name"].append(track_meta.album.artists[0].name)
        # Valence and energy
        track_features = sp.track_audio_features(track["id"])
        data_dict["valence"].append(track_features.valence)
        data_dict["energy"].append(track_features.energy)
        data_dict["danceability"].append(track_features.danceability)
        data_dict["liveness"].append(track_features.liveness)
        data_dict["acousticness"].append(track_features.acousticness)
        data_dict["speechiness"].append(track_features.speechiness)
        
        # Wait 0.2 seconds per track so that the api doesnt overheat
        time.sleep(0.2)
        
##################
## PROCESS DATA ##
##################

# Store data in dataframe
df = pd.DataFrame(data_dict)

# Drop duplicates
df.drop_duplicates(subset = "id", keep = "first", inplace = True)
df.to_csv("valence_arousal_datasetv2.csv", index = False)