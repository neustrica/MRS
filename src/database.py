import psycopg2
import psycopg2.extras 
import pandas as pd
import logging
import os

from authorization import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

def get_db_connection():
    """Устанавливает соединение с базой данных PostgreSQL."""
    try:
        # Используем импортированные переменные
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        logger.error(f"Проверьте, что сервер PostgreSQL запущен и доступен по адресу {DB_HOST}:{DB_PORT}.")
        logger.error(f"Убедитесь, что база данных '{DB_NAME}' существует, и у пользователя '{DB_USER}' есть права на подключение.")
        logger.error(f"Также проверьте правильность пароля (задан в authorization.py или переменных окружения).")
        raise
    except Exception as e: 
        logger.error(f"Непредвиденная ошибка при подключении к PostgreSQL: {e}")
        raise 

def create_tables_if_not_exists():
    """Создает таблицы в БД PostgreSQL, если они еще не существуют. track_id теперь Spotify ID."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS track_ratings (
                    user_id BIGINT NOT NULL,
                    track_id TEXT NOT NULL, -- Spotify ID
                    rating INTEGER NOT NULL,
                    rated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_id)
                )
            ''')
            logger.info("Таблица 'track_ratings' (с Spotify ID) проверена/создана.")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS listened_tracks (
                    user_id BIGINT NOT NULL,
                    track_id TEXT NOT NULL, -- Spotify ID
                    listened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_id)
                )
            ''')
            logger.info("Таблица 'listened_tracks' (с Spotify ID) проверена/создана.")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_mapping (
                    user_id BIGINT PRIMARY KEY, 
                    user_num SERIAL UNIQUE NOT NULL, 
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Таблица 'user_mapping' проверена/создана.")
            conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Ошибка при создании таблиц PostgreSQL (с Spotify ID): {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def save_track_rating(user_id: int, track_spotify_id: str, rating: int):
    logger.info(f"Сохранение оценки: user_id={user_id}, track_spotify_id='{track_spotify_id}', rating={rating}")
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO track_ratings (user_id, track_id, rating, rated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, track_id) DO UPDATE SET
                    rating = EXCLUDED.rating,
                    rated_at = CURRENT_TIMESTAMP
            ''', (user_id, track_spotify_id, rating))
            conn.commit()
            logger.info("Оценка трека (Spotify ID) успешно сохранена.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка сохранения оценки трека (Spotify ID) в PostgreSQL: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def save_listened_track(user_id: int, track_spotify_id: str):
    logger.info(f"Сохранение прослушанного трека: user_id={user_id}, track_spotify_id='{track_spotify_id}'")
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO listened_tracks (user_id, track_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, track_id) DO NOTHING
            ''', (user_id, track_spotify_id))
            conn.commit()
            logger.info("Прослушанный трек (Spotify ID) успешно сохранен (или уже существовал).")
    except psycopg2.Error as e:
        logger.error(f"Ошибка сохранения прослушанного трека (Spotify ID) в PostgreSQL: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def get_ratings() -> pd.DataFrame:
    logger.info("Запрос всех оценок (с Spotify ID) из БД PostgreSQL.")
    conn = None
    try:
        conn = get_db_connection()
        query = '''
            SELECT um.user_num, tr.track_id, tr.rating
            FROM track_ratings tr
            JOIN user_mapping um ON tr.user_id = um.user_id
        '''
        df = pd.read_sql_query(query, conn)
        if 'user_num' in df.columns:
             df.rename(columns={'user_num': 'user_id'}, inplace=True) 
        logger.info(f"Загружено {len(df)} оценок (с Spotify ID) из PostgreSQL.")
        return df
    except (psycopg2.Error, pd.io.sql.DatabaseError) as e: 
        logger.error(f"Ошибка при загрузке всех оценок (с Spotify ID) из PostgreSQL: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def get_top_rated_tracks(user_id: int, min_rating: int = 4) -> list:
    logger.info(f"Запрос высоко оцененных треков (Spotify ID) для user_id={user_id} (min_rating={min_rating}) из PostgreSQL.")
    conn = None
    track_spotify_ids = []
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute('''
                SELECT track_id FROM track_ratings
                WHERE user_id = %s AND rating >= %s
                ORDER BY rated_at DESC
            ''', (user_id, min_rating))
            rows = cursor.fetchall()
            track_spotify_ids = [row['track_id'] for row in rows] 
            logger.info(f"Найдено {len(track_spotify_ids)} высоко оцененных треков (Spotify ID) в PostgreSQL.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при запросе высоко оцененных треков (Spotify ID) из PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()
    return track_spotify_ids

def check_user_has_ratings(user_id: int) -> bool:
    logger.info(f"Проверка наличия оценок у user_id={user_id} в PostgreSQL.")
    conn = None
    count = 0
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM track_ratings WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            if result:
                count = result[0]
            logger.info(f"Пользователь {user_id} имеет {count} оценок в PostgreSQL.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при проверке наличия оценок в PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()
    return count > 0

def add_user_mapping(user_id: int) -> int:
    logger.info(f"Добавление/получение user_mapping для user_id={user_id} в PostgreSQL.")
    conn = None
    user_num = -1 
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT user_num FROM user_mapping WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if row:
                user_num = row['user_num']
                logger.info(f"Пользователь {user_id} уже существует с user_num={user_num}.")
            else:
                cursor.execute("INSERT INTO user_mapping (user_id) VALUES (%s) RETURNING user_num", (user_id,))
                new_user_row = cursor.fetchone()
                if new_user_row:
                    user_num = new_user_row['user_num']
                    conn.commit() 
                    logger.info(f"Новый пользователь {user_id} добавлен с user_num={user_num}.")
                else:
                    logger.error(f"Не удалось вставить нового пользователя {user_id} и получить user_num (RETURNING был пуст).")
                    if conn: conn.rollback()
    except psycopg2.Error as e:
        logger.error(f"Ошибка psycopg2 при добавлении/получении user_mapping для user_id={user_id}: {e}")
        if conn: conn.rollback() 
        user_num = -1 
    except Exception as e: 
        logger.error(f"Неожиданная ошибка при добавлении/получении user_mapping для user_id={user_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        user_num = -1 
    finally:
        if conn:
            conn.close()
    return user_num

def get_user_to_idx_map() -> dict:
    logger.info("Запрос сопоставления user_id -> user_num из PostgreSQL.")
    conn = None
    user_map = {}
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT user_id, user_num FROM user_mapping")
            rows = cursor.fetchall()
            user_map = {row['user_id']: row['user_num'] for row in rows}
            logger.info(f"Загружено {len(user_map)} сопоставлений user_id -> user_num из PostgreSQL.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при запросе сопоставления user_id -> user_num из PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()
    return user_map

def get_internal_user_id(telegram_user_id: int) -> int:
    logger.info(f"Запрос внутреннего user_num для telegram_user_id={telegram_user_id} из PostgreSQL.")
    conn = None; user_num = -1
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT user_num FROM user_mapping WHERE user_id = %s", (telegram_user_id,))
            row = cursor.fetchone()
            if row: user_num = row['user_num']
            else: logger.warning(f"Внутренний user_num не найден для telegram_user_id={telegram_user_id}.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при запросе внутреннего user_num: {e}")
    finally:
        if conn:
            conn.close()
    return user_num

if __name__ == "__main__":
    logger.info("Проверка/создание таблиц PostgreSQL (с Spotify ID) при прямом запуске database.py...")
    try:
        logger.info("Проверка соединения с PostgreSQL...")
        conn_test = get_db_connection() 
        conn_test.close()
        logger.info("Соединение с PostgreSQL успешно установлено.")
        
        logger.info("Создание таблиц (если не существуют)...")
        create_tables_if_not_exists()
        logger.info("Проверка/создание таблиц PostgreSQL (с Spotify ID) завершено успешно.")
    except psycopg2.OperationalError as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ к PostgreSQL: {e}")
        logger.error("ПОЖАЛУЙСТА, ПРОВЕРЬТЕ ПАРАМЕТРЫ ПОДКЛЮЧЕНИЯ (в authorization.py или переменных окружения) И СОСТОЯНИЕ СЕРВЕРА/БД.")
    except Exception as e:
        logger.error(f"Не удалось инициализировать базу данных PostgreSQL (с Spotify ID): {e}")
else:
    # При обычном импорте модуля (например, из app.py или telegram_bot.py)
    # таблицы будут создаваться автоматически, если раскомментировать следующую строку.
    # Это удобно для первого запуска.
    # create_tables_if_not_exists() 
    pass
