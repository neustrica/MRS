import asyncio
import os
import pandas as pd
import yt_dlp
from sklearn.metrics.pairwise import cosine_similarity
import logging
from typing import List, Dict, Optional, Any
import tekore as tk # Для обработки исключений Spotify
import pylast # Для обработки исключений Last.fm

# Импортируем инициализированные клиенты из authorization.py
from authorization import sp, youtube, lastfm_network 
from database import (
    get_ratings,
    get_top_rated_tracks, 
    get_user_to_idx_map,
)

logger = logging.getLogger(__name__)

async def _run_sync(func, *args):
    """Запускает синхронную функцию в отдельном потоке."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)

# --- Класс-агент для Spotify API ---
class SpotifyAgent:
    def __init__(self, sp_client):
        self.sp = sp_client

    async def search_track(self, query: str, limit: int = 5) -> Optional[List[Dict[str, Any]]]:
        logger.info(f"SpotifyAgent: Поиск по запросу: '{query}', limit={limit}")
        if not self.sp:
            logger.warning("SpotifyAgent: Клиент Spotify (sp) не инициализирован.")
            return None
        
        def _search_sync():
            try:
                tracks_paging, = self.sp.search(query, types=('track',), limit=limit)
                if tracks_paging and tracks_paging.items:
                    found_tracks = []
                    for track in tracks_paging.items:
                        if track and track.id and track.name and track.artists:
                            found_tracks.append({
                                'id': track.id,
                                'name': track.name,
                                'artist_name': track.artists[0].name, 
                                'artist_names': [a.name for a in track.artists],
                                'spotify_url': track.external_urls.get('spotify', "N/A")
                            })
                    logger.info(f"SpotifyAgent: Найдено {len(found_tracks)} треков по запросу '{query}'.")
                    return found_tracks
                else:
                    logger.info(f"SpotifyAgent: Треки не найдены по запросу: '{query}'")
                    return None
            except tk.HTTPError as e:
                status = getattr(e.response, 'status_code', 'N/A') if e.response else 'N/A'
                logger.error(f"SpotifyAgent: HTTP ошибка ({type(e).__name__}) при поиске '{query}': {status} - {e}", exc_info=True)
                return None
            except Exception as e:
                logger.error(f"SpotifyAgent: Общая ошибка при поиске '{query}': {e}", exc_info=True)
                return None
        return await _run_sync(_search_sync)

    async def get_track_basic_info(self, track_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"SpotifyAgent: Запрос базовой информации для track_id='{track_id}'")
        if not self.sp:
            logger.warning("SpotifyAgent: Клиент Spotify (sp) не инициализирован.")
            return None

        def _get_info_sync():
            try:
                track_info_data = self.sp.track(track_id)
                if not track_info_data:
                    logger.warning(f"SpotifyAgent: Информация о треке не найдена для track_id='{track_id}'")
                    return None
                artist_names = [artist.name for artist in track_info_data.artists]
                main_artist_id = track_info_data.artists[0].id if track_info_data.artists and track_info_data.artists[0].id else None
                return {
                    'id': track_info_data.id,
                    'name': track_info_data.name,
                    'artist_name': artist_names[0] if artist_names else "Unknown Artist",
                    'artist_names': artist_names,
                    'artist_id': main_artist_id, 
                    'spotify_url': track_info_data.external_urls.get('spotify', "N/A")
                }
            except tk.HTTPError as e:
                status = getattr(e.response, 'status_code', 'N/A') if e.response else 'N/A'
                if status == 404:
                     logger.warning(f"SpotifyAgent: Трек {track_id} не найден (404) при запросе базовой информации.")
                else:
                    logger.error(f"SpotifyAgent: HTTP ошибка ({type(e).__name__}) при получении базовой информации о треке {track_id}: {status} - {e}", exc_info=True)
                return None
            except Exception as e:
                logger.error(f"SpotifyAgent: Общая ошибка при получении базовой информации о треке {track_id}: {e}", exc_info=True)
                return None
        return await _run_sync(_get_info_sync)

    async def get_artist_top_tracks(self, artist_id: str, market: str = "US", limit: int = 3) -> List[Dict[str, Any]]:
        logger.info(f"SpotifyAgent: Запрос топ-{limit} треков для artist_id='{artist_id}', market='{market}'")
        if not self.sp or not artist_id:
            logger.warning("SpotifyAgent: Клиент Spotify не инициализирован или не передан artist_id.")
            return []
            
        def _get_top_tracks_sync():
            tracks_info_sync = []
            try:
                top_tracks_result = self.sp.artist_top_tracks(artist_id, market=market)
                if top_tracks_result:
                    for track in top_tracks_result[:limit]:
                        if track and track.id and track.name and track.artists:
                            tracks_info_sync.append({
                                'id': track.id,
                                'name': track.name,
                                'artist_names': [a.name for a in track.artists],
                                'spotify_url': track.external_urls.get('spotify', "N/A")
                            })
                    logger.info(f"SpotifyAgent: Найдено {len(tracks_info_sync)} топ-треков для artist_id='{artist_id}'.")
            except tk.HTTPError as e:
                status = getattr(e.response, 'status_code', 'N/A') if e.response else 'N/A'
                logger.error(f"SpotifyAgent: HTTP ошибка ({type(e).__name__}) при запросе топ-треков для artist_id {artist_id}: {status} - {e}", exc_info=True)
            except Exception as e:
                logger.error(f"SpotifyAgent: Общая ошибка при запросе топ-треков для artist_id {artist_id}: {e}", exc_info=True)
            return tracks_info_sync
        return await _run_sync(_get_top_tracks_sync)

# --- Класс-агент для Last.fm API ---
class LastFMAgent:
    def __init__(self, lastfm_client):
        self.lastfm = lastfm_client

    async def get_similar_tracks(self, track_title: str, artist_name: str, limit: int = 5) -> List[Dict[str, str]]:
        logger.info(f"LastFMAgent: Запрос похожих треков для '{track_title}' - '{artist_name}', limit={limit}")
        if not self.lastfm:
            logger.warning("LastFMAgent: Клиент Last.fm не инициализирован.")
            return []
        
        def _get_similar_sync():
            similar_tracks_info_sync = []
            try:
                track_obj_lfm = self.lastfm.get_track(artist=artist_name, title=track_title)
                if not track_obj_lfm or not hasattr(track_obj_lfm, 'title'):
                     logger.warning(f"LastFMAgent: Трек '{track_title}' - '{artist_name}' не найден на Last.fm для поиска похожих.")
                     return []
                
                logger.info(f"LastFMAgent: Найден сид-трек: {track_obj_lfm.title} (URL: {track_obj_lfm.get_url()})")
                similar_tracks_lastfm = track_obj_lfm.get_similar(limit=limit)

                if similar_tracks_lastfm:
                    for similar_match in similar_tracks_lastfm:
                        item = similar_match.item
                        if item and hasattr(item, 'title') and item.title and \
                           hasattr(item, 'artist') and item.artist and hasattr(item.artist, 'name') and item.artist.name:
                            similar_tracks_info_sync.append({
                                'name': item.title,
                                'artist_name': item.artist.name 
                            })
                    logger.info(f"LastFMAgent: Найдено {len(similar_tracks_info_sync)} похожих треков для '{track_title}'.")
                else:
                    logger.info(f"LastFMAgent: Похожие треки для '{track_title}' не найдены.")
            except pylast.WSError as e:
                logger.error(f"LastFMAgent: API ошибка (WSError) при поиске похожих треков для '{track_title}': {e.details if hasattr(e, 'details') else str(e)}")
            except pylast.TrackNotFound:
                 logger.warning(f"LastFMAgent: Трек '{track_title}' - '{artist_name}' не найден (TrackNotFound).")
            except Exception as e:
                logger.error(f"LastFMAgent: Общая ошибка при поиске похожих треков для '{track_title}': {e}", exc_info=True)
            return similar_tracks_info_sync
        return await _run_sync(_get_similar_sync)

# --- Класс-агент для YouTube API ---
class YouTubeAgent:
    def __init__(self, youtube_client):
        self.youtube = youtube_client

    async def search_video(self, track_name: str, artist_name: str) -> Optional[Dict[str, Any]]:
        query = f"{track_name} {artist_name}"
        if isinstance(artist_name, list): # Обработка, если artist_name - список
            artist_name_str = artist_name[0] if artist_name else ""
            query = f"{track_name} {artist_name_str}"
            
        logger.info(f"YouTubeAgent: Поиск видео: '{query}'")
        if not self.youtube: 
            logger.warning("YouTubeAgent: Клиент YouTube не инициализирован.")
            return None
        
        def _search_sync():
            try:
                request_obj = self.youtube.search().list(part="snippet", q=query, type="video", maxResults=1)
                response = request_obj.execute()
                if response and response.get('items'):
                    video_item = response['items'][0]
                    logger.info(f"YouTubeAgent: Найдено видео: {video_item['snippet']['title']}")
                    return video_item
                logger.info(f"YouTubeAgent: Видео не найдено по запросу: '{query}'")
                return None
            except Exception as e:
                logger.error(f"YouTubeAgent: Общая ошибка при поиске видео '{query}': {e}", exc_info=True)
                return None
        return await _run_sync(_search_sync)
    
    async def download_audio(self, video_url: str) -> Optional[str]:
        logger.info(f"YouTubeAgent: Запрос на скачивание аудио с {video_url}")
        if not video_url: return None
        temp_filename_base = "temp_audio_download"
        ydl_opts = {
            'format': 'bestaudio/best', 'outtmpl': f'{temp_filename_base}.%(ext)s', 
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'noplaylist': True, 'quiet': False, 'noprogress': True, 'ffmpeg_location': os.getenv('FFMPEG_PATH') 
        }
        
        def _download_sync():
            downloaded_mp3_path_sync, final_named_mp3_path_sync = None, None
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(video_url, download=True)
                
                temp_mp3_file_after_conversion = f"{temp_filename_base}.mp3"
                if os.path.exists(temp_mp3_file_after_conversion):
                    downloaded_mp3_path_sync = temp_mp3_file_after_conversion
                    title = info_dict.get('title', 'unknown_track')
                    safe_title = "".join(c if c.isalnum() or c in (' ','.','_','-') else '_' for c in title).strip() or "downloaded_audio"
                    final_named_mp3_path_sync = f"{safe_title}.mp3"
                    counter = 1
                    base_name, ext = os.path.splitext(final_named_mp3_path_sync)
                    while os.path.exists(final_named_mp3_path_sync):
                        final_named_mp3_path_sync = f"{base_name}_{counter}{ext}"; counter += 1
                    os.rename(downloaded_mp3_path_sync, final_named_mp3_path_sync)
                    logger.info(f"YouTubeAgent: Аудио скачано и переименовано в '{final_named_mp3_path_sync}'")
                    return final_named_mp3_path_sync, downloaded_mp3_path_sync # Возвращаем оба для finally
                else:
                    # Логирование ошибки, если mp3 не создан
                    original_download_ext = info_dict.get('ext') if info_dict else 'bin'
                    original_temp_file = f"{temp_filename_base}.{original_download_ext}"
                    if os.path.exists(original_temp_file):
                         logger.error(f"YouTubeAgent: Файл '{temp_mp3_file_after_conversion}' не найден после yt-dlp, но найден оригинальный '{original_temp_file}'.")
                    else:
                         logger.error(f"YouTubeAgent: Файл '{temp_mp3_file_after_conversion}' не найден после yt-dlp, и оригинальный файл (ext: {original_download_ext}) тоже не найден.")
                    return None, None
            except yt_dlp.utils.DownloadError as de_sync:
                logger.error(f"YouTubeAgent: yt-dlp ошибка скачивания: {de_sync}")
                return None, None
            except Exception as e_sync:
                logger.error(f"YouTubeAgent: Общая ошибка при скачивании аудио с {video_url}: {e_sync}", exc_info=True)
                return None, None
        
        final_named_mp3_path, downloaded_mp3_path = await _run_sync(_download_sync)
        
        if downloaded_mp3_path and os.path.exists(downloaded_mp3_path) and \
           (not final_named_mp3_path or downloaded_mp3_path != final_named_mp3_path) :
            try: 
                logger.debug(f"YouTubeAgent: Удаление временного файла (если остался): {downloaded_mp3_path}")
                os.remove(downloaded_mp3_path)
            except OSError as oe: 
                logger.warning(f"YouTubeAgent: Не удалось удалить временный файл {downloaded_mp3_path}: {oe}")
        return final_named_mp3_path


# --- Вспомогательная функция для коллаборативной фильтрации ---
def _find_similar_users_for_matrix(user_sim_matrix: pd.DataFrame, target_user_matrix_idx: int, k: int = 5) -> List[int]:
    logger.debug(f"Поиск похожих пользователей для matrix_idx={target_user_matrix_idx}, k={k}")
    if target_user_matrix_idx not in user_sim_matrix.index:
        logger.warning(f"Индекс пользователя {target_user_matrix_idx} отсутствует в матрице схожести.")
        return []
    user_sim_scores = user_sim_matrix.loc[target_user_matrix_idx]
    similar_users_indices = user_sim_scores.drop(target_user_matrix_idx).nlargest(k).index.tolist()
    logger.debug(f"Найдены похожие пользователи (matrix_indices): {similar_users_indices} для {target_user_matrix_idx}")
    return similar_users_indices

# --- Основная функция генерации рекомендаций ---

async def generate_recommendations(telegram_user_id: int, k_similar_users: int = 5, num_recs_to_return: int = 5) -> List[Dict[str, Any]]:
    logger.info(f"Генерация рекомендаций для telegram_user_id={telegram_user_id} (Spotify ID + Last.fm)")

    # Создаем экземпляры агентов
    spotify_agent = SpotifyAgent(sp)
    lastfm_agent = LastFMAgent(lastfm_network)
    # youtube_agent не нужен напрямую в generate_recommendations, он используется в telegram_bot.py

    if not sp and not lastfm_network: # Проверка на наличие хотя бы одного клиента
        logger.error("Клиенты Spotify и Last.fm не инициализированы.")
        return []

    user_to_idx_map = await _run_sync(get_user_to_idx_map)
    df_ratings_raw = await _run_sync(get_ratings) 

    if df_ratings_raw.empty:
        logger.warning("Нет данных об оценках в БД.")
        return []
    if not user_to_idx_map:
        logger.warning("Нет сопоставления пользователей.")
        return []
    
    target_user_matrix_idx = user_to_idx_map.get(telegram_user_id)
    if target_user_matrix_idx is None:
        logger.warning(f"Пользователь telegram_user_id={telegram_user_id} не найден в user_to_idx_map.")
        return [] 

    # 1. Коллаборативная фильтрация (основана на Spotify ID)
    logger.info("Этап коллаборативной фильтрации (Spotify ID)...")
    pivot_table = df_ratings_raw.pivot_table(
        index='user_id', columns='track_id', values='rating' 
    ).fillna(0)
    collaborative_recs_spotify_ids = []
    if not pivot_table.empty and target_user_matrix_idx in pivot_table.index:
        user_similarity_df = pd.DataFrame(cosine_similarity(pivot_table), index=pivot_table.index, columns=pivot_table.index)
        similar_user_indices = _find_similar_users_for_matrix(user_similarity_df, target_user_matrix_idx, k=k_similar_users)
        if similar_user_indices:
            valid_similar_indices = [idx for idx in similar_user_indices if idx in pivot_table.index]
            if valid_similar_indices:
                mean_scores = pivot_table.loc[valid_similar_indices].mean(axis=0)
                rated_by_target_user = pivot_table.loc[target_user_matrix_idx][pivot_table.loc[target_user_matrix_idx] > 0].index
                mean_scores = mean_scores.drop(rated_by_target_user, errors='ignore')
                collaborative_recs_spotify_ids = list(mean_scores.nlargest(num_recs_to_return * 2).index)
                logger.info(f"Найдено {len(collaborative_recs_spotify_ids)} потенциальных коллаборативных рекомендаций (Spotify ID).")
    else:
        logger.warning("Pivot_table пуста или текущий пользователь в ней отсутствует для коллаборативной фильтрации.")

    # 2. Контентные предложения
    logger.info("Этап контентных предложений...")
    content_based_candidates_spotify_info = [] 
    
    top_rated_spotify_ids_by_user = await _run_sync(get_top_rated_tracks, telegram_user_id, 4)
    
    liked_artist_spotify_ids = set()

    if top_rated_spotify_ids_by_user:
        logger.info(f"Найдено {len(top_rated_spotify_ids_by_user)} высоко оцененных треков пользователя (Spotify ID).")
        
        for seed_spotify_id in top_rated_spotify_ids_by_user[:2]: 
            seed_track_spotify_info = await spotify_agent.get_track_basic_info(seed_spotify_id)
            if seed_track_spotify_info and seed_track_spotify_info.get('name') and seed_track_spotify_info.get('artist_name'):
                track_title = seed_track_spotify_info['name']
                artist_name = seed_track_spotify_info['artist_name'] 
                
                if seed_track_spotify_info.get('artist_id'): 
                    liked_artist_spotify_ids.add(seed_track_spotify_info['artist_id'])

                logger.info(f"Ищем похожие треки на Last.fm для: '{track_title}' - '{artist_name}'")
                similar_lfm_tracks = await lastfm_agent.get_similar_tracks(track_title, artist_name, limit=3)
                
                if similar_lfm_tracks:
                    logger.info(f"Найдено на Last.fm: {len(similar_lfm_tracks)} похожих. Ищем их в Spotify...")
                    for lfm_track in similar_lfm_tracks:
                        query = f"track:{lfm_track['name']} artist:{lfm_track['artist_name']}" 
                        spotify_equivalents = await spotify_agent.search_track(query, limit=1)
                        if spotify_equivalents: 
                            logger.info(f"  Last.fm '{lfm_track['name']}' -> Spotify: {spotify_equivalents[0]['name']} (ID: {spotify_equivalents[0]['id']})")
                            content_based_candidates_spotify_info.append(spotify_equivalents[0]) 
            await asyncio.sleep(0.33) 

        if liked_artist_spotify_ids:
            logger.info(f"Ищем топ-треки для понравившихся исполнителей Spotify IDs: {list(liked_artist_spotify_ids)[:2]}...")
            for artist_id in list(liked_artist_spotify_ids)[:2]: 
                top_artist_tracks_spotify = await spotify_agent.get_artist_top_tracks(artist_id, "US", 2)
                if top_artist_tracks_spotify: 
                    logger.info(f"  Добавлены топ-треки ({len(top_artist_tracks_spotify)}) от исполнителя {artist_id}")
                    content_based_candidates_spotify_info.extend(top_artist_tracks_spotify)
                await asyncio.sleep(0.2)
    else:
        logger.info("У пользователя нет высоко оцененных треков для использования в качестве сидов.")

    logger.info(f"Собрано {len(content_based_candidates_spotify_info)} кандидатов из контентных источников.")

    # 3. Объединение и формирование финального списка
    final_recommendations_dict = {} 

    for sp_id in collaborative_recs_spotify_ids:
        if sp_id and sp_id not in final_recommendations_dict:
            track_info = await spotify_agent.get_track_basic_info(sp_id)
            if track_info:
                final_recommendations_dict[sp_id] = {
                    'track_id': sp_id, 
                    'track_name': track_info['name'],
                    'artist_names': track_info['artist_names'],
                    'spotify_url': track_info.get('spotify_url', "N/A"),
                    'source': 'collaborative' 
                }
            await asyncio.sleep(0.1)

    for candidate_info in content_based_candidates_spotify_info:
        sp_id = candidate_info.get('id')
        if sp_id and sp_id not in final_recommendations_dict:
            final_recommendations_dict[sp_id] = {
                'track_id': sp_id,
                'track_name': candidate_info['name'],
                'artist_names': candidate_info.get('artist_names', [candidate_info.get('artist_name', 'Unknown Artist')]),
                'spotify_url': candidate_info.get('spotify_url', "N/A"),
                'source': 'content_hybrid' 
            }
    
    all_rated_by_user_df = df_ratings_raw[df_ratings_raw['user_id'] == target_user_matrix_idx]
    all_rated_spotify_ids_by_user = set(all_rated_by_user_df['track_id'].unique()) if not all_rated_by_user_df.empty else set()

    filtered_recs_list = [
        rec for sp_id, rec in final_recommendations_dict.items()
        if sp_id not in all_rated_spotify_ids_by_user
    ]
    
    filtered_recs_list.sort(key=lambda x: (x['source'] != 'collaborative')) 
    
    final_recommendations_list = filtered_recs_list[:num_recs_to_return]
            
    logger.info(f"Сгенерировано {len(final_recommendations_list)} финальных рекомендаций для telegram_user_id={telegram_user_id}")
    return final_recommendations_list
