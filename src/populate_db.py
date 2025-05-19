import random
import logging
import asyncio 
from typing import Optional, List # Добавлен List

# Убедитесь, что app.py и database.py находятся в том же каталоге или доступны через PYTHONPATH
from database import save_track_rating, add_user_mapping, create_tables_if_not_exists, get_db_connection
# Импортируем SpotifyAgent и клиент sp из authorization
from app import SpotifyAgent # Класс-агент
from authorization import sp # Клиент tekore, который будет передан в SpotifyAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Создаем экземпляр SpotifyAgent ---
# sp импортируется из authorization.py и может быть None, если авторизация не удалась.
# Методы SpotifyAgent должны это учитывать.
spotify_agent = SpotifyAgent(sp)


SAMPLE_TELEGRAM_USER_IDS = [
    111111, 222222, 333333, 444444, 555555, 666666, 777777, 888888, 999999, 101010,
    121212, 131313, 141414, 151515, 161616, 171717, 181818, 191919, 202020, 212121,
    232323, 242424, 252525, 262626, 272727, 282828, 292929, 303030, 313131, 323232,
    733747545 # Ваш ID
]

# Примеры треков для поиска на Spotify (название, исполнитель)
SAMPLE_TRACK_QUERIES = [
    ("Bohemian Rhapsody", "Queen"), ("Stairway to Heaven", "Led Zeppelin"), ("Like a Rolling Stone", "Bob Dylan"),
    ("Imagine", "John Lennon"), ("Smells Like Teen Spirit", "Nirvana"), ("Billie Jean", "Michael Jackson"),
    ("Hotel California", "Eagles"), ("Hey Jude", "The Beatles"), ("Sweet Child O' Mine", "Guns N' Roses"),
    ("Wonderwall", "Oasis"), ("Blinding Lights", "The Weeknd"), ("Shape of You", "Ed Sheeran"),
    ("Levitating", "Dua Lipa"), ("bad guy", "Billie Eilish"), ("drivers license", "Olivia Rodrigo"),
    ("As It Was", "Harry Styles"), ("Lose Yourself", "Eminem"), ("HUMBLE.", "Kendrick Lamar"),
    ("Get Lucky", "Daft Punk"), ("Wake Me Up", "Avicii"), ("Uptown Funk", "Mark Ronson"),
    ("Crazy in Love", "Beyoncé"), ("Rolling in the Deep", "Adele"), ("Hallelujah", "Leonard Cohen"),
    ("No Woman, No Cry", "Bob Marley & The Wailers"), ("Yesterday", "The Beatles"), ("Let It Be", "The Beatles"),
    ("Stressed Out", "Twenty One Pilots"), ("Radioactive", "Imagine Dragons"), ("Counting Stars", "OneRepublic"),
    ("Without Me", "Eminem"), ("Skyscraper", "FRIENDLY THUG 52 NGG"), ("Bad Habits", "Ed Sheeran"),
    ("Shivers", "Ed Sheeran"), ("The Real Slim Shady", "Eminem"), ("In Da Club", "50 Cent"),
    # ("My Band", "D12"), # Этот трек может плохо искаться, если его нет в Spotify или название неточное
    # ("Forgot About Dre", "Dr. Dre"),
    ("Physical", "Dua Lipa"),
    ("Closer", "The Chainsmokers")
]

NUM_RATINGS_PER_USER = 10
MAX_SEARCH_RESULTS_TO_CONSIDER = 1 # Берем первый результат поиска Spotify

async def find_track_spotify_id(track_name: str, artist_name: str) -> Optional[str]:
    """Ищет трек на Spotify и возвращает его Spotify ID, если найден."""
    query = f"track:{track_name} artist:{artist_name}" # Более точный поиск
    
    # Используем spotify_agent.search_track
    found_tracks = await spotify_agent.search_track(query, limit=MAX_SEARCH_RESULTS_TO_CONSIDER)
    
    if found_tracks: # search_track возвращает список словарей
        track_info = found_tracks[0] # Берем первый результат
        if track_info.get('id'):
            logger.info(f"  Найден Spotify ID '{track_info['id']}' для '{track_info['name']}' - '{track_info['artist_name']}'")
            return track_info['id']
        else:
            logger.warning(f"  Spotify ID не найден для '{track_info['name']}' - '{track_info['artist_name']}' в результатах поиска Spotify.")
    else:
        logger.warning(f"  Трек '{track_name}' - '{artist_name}' не найден в Spotify по запросу '{query}'.")
    return None

async def populate():
    logger.info("Запуск скрипта для наполнения базы данных PostgreSQL (Spotify ID)...")
    
    if not sp:
        logger.error("Клиент Spotify (sp) не инициализирован в authorization.py. Наполнение БД невозможно.")
        return

    try:
        logger.info("Проверка соединения с БД и создание таблиц (если не существуют)...")
        conn_test = get_db_connection()
        if conn_test:
            conn_test.close()
            create_tables_if_not_exists() # Убедимся, что таблицы созданы (с Spotify ID)
            logger.info("Проверка/создание таблиц завершено.")
        else:
            logger.error("Не удалось установить соединение с БД. Наполнение прервано.")
            return
    except Exception as e:
        logger.error(f"Не удалось подключиться к БД или создать таблицы: {e}")
        return

    num_users_processed = 0
    num_ratings_added = 0
    
    track_spotify_id_cache = {}
    logger.info(f"Получение Spotify ID для {len(SAMPLE_TRACK_QUERIES)} тестовых треков...")
    for track_name, artist_name in SAMPLE_TRACK_QUERIES:
        logger.info(f"Ищем Spotify ID для: '{track_name}' - '{artist_name}'")
        spotify_id = await find_track_spotify_id(track_name, artist_name)
        if spotify_id:
            track_spotify_id_cache[(track_name, artist_name)] = spotify_id
        await asyncio.sleep(0.2) # Небольшая задержка между запросами к Spotify API

    valid_spotify_ids_to_rate = list(track_spotify_id_cache.values())
    if not valid_spotify_ids_to_rate:
        logger.error("Не удалось получить Spotify ID ни для одного из тестовых треков. Наполнение невозможно.")
        return
    logger.info(f"Успешно получено {len(valid_spotify_ids_to_rate)} Spotify ID для оценки.")

    for user_id in SAMPLE_TELEGRAM_USER_IDS:
        logger.info(f"Обработка пользователя с Telegram ID: {user_id}")
        user_num = add_user_mapping(user_id) # add_user_mapping синхронная
        if user_num == -1:
            logger.error(f"Не удалось добавить/получить user_mapping для user_id={user_id}. Пропускаем.")
            continue
        
        logger.info(f"Пользователь {user_id} (user_num={user_num}) обработан/добавлен.")
        num_users_processed += 1

        num_tracks_to_rate = min(NUM_RATINGS_PER_USER, len(valid_spotify_ids_to_rate))
        
        if len(valid_spotify_ids_to_rate) >= num_tracks_to_rate and num_tracks_to_rate > 0 :
            spotify_ids_for_this_user = random.sample(valid_spotify_ids_to_rate, num_tracks_to_rate)
        elif valid_spotify_ids_to_rate: 
            spotify_ids_for_this_user = valid_spotify_ids_to_rate
            logger.warning(f"  Запрошено {num_tracks_to_rate} оценок, но доступно только {len(valid_spotify_ids_to_rate)} Spotify ID.")
        else: 
            logger.warning(f"  Нет доступных Spotify ID для оценки пользователем {user_id}.")
            continue 
        
        for track_spotify_id in spotify_ids_for_this_user:
            rating = random.randint(1, 5) 
            logger.debug(f"  Сохранение оценки для user_id={user_id}, track_spotify_id='{track_spotify_id}', rating={rating}")
            try:
                save_track_rating(user_id, track_spotify_id, rating) # save_track_rating синхронная
                num_ratings_added +=1
            except Exception as e:
                logger.error(f"  Ошибка при сохранении оценки для user_id={user_id}, track_spotify_id='{track_spotify_id}': {e}")
            
    logger.info(f"Наполнение базы данных завершено. Обработано пользователей: {num_users_processed}. Добавлено оценок: {num_ratings_added}.")

async def main_populate():
    await populate()

if __name__ == "__main__":
    # Перед запуском убедитесь, что:
    # 1. Сервер PostgreSQL запущен.
    # 2. База данных (например, 'music_recs_db') создана.
    # 3. Пользователь PostgreSQL и пароль настроены в database.py.
    # 4. Ключи Spotify, Last.fm, YouTube, Telegram настроены в authorization.py.
    # 5. Ваш Telegram-бот (если он обращается к той же БД) остановлен.
    # 6. Таблицы в БД созданы с правильной структурой (Spotify ID) - это должно было произойти при запуске database.py.
    
    # Если вы хотите начать с абсолютно чистой базы данных (без старых таблиц и данных),
    # удалите таблицы вручную через psql или pgAdmin перед запуском этого скрипта.
    # Пример: DROP TABLE IF EXISTS track_ratings, listened_tracks, user_mapping CASCADE;
    
    if not sp: # Проверка, что клиент Spotify инициализирован перед запуском populate
        logger.critical("Критическая ошибка: Клиент Spotify (sp) не инициализирован в authorization.py. "
                        "Скрипт populate_db.py не может быть выполнен.")
    else:
        asyncio.run(main_populate())
