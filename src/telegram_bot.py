import asyncio
import os
import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ParseMode
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted, MessageNotModified

# Используем инициализированный bot и клиенты API из authorization.py
from authorization import bot, sp, youtube, lastfm_network # sp, youtube, lastfm_network могут быть None

# Импортируем классы-агенты и основную функцию рекомендаций из app.py
from app import (
    SpotifyAgent, 
    YouTubeAgent,
    generate_recommendations, 
)
from database import (
    save_track_rating,      # Принимает Spotify ID
    check_user_has_ratings,
    add_user_mapping,
)

logger = logging.getLogger(__name__)

storage = MemoryStorage()

# Определяем состояния FSM
class UserActions(StatesGroup):
    waiting_for_track_name = State()
    waiting_for_search_selection = State() 

# --- Создаем экземпляры агентов ---
spotify_agent = SpotifyAgent(sp) 
youtube_agent = YouTubeAgent(youtube)

# --- Вспомогательная функция для основной клавиатуры ---
def get_main_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        KeyboardButton(text="🎧 Получить рекомендации"),
        KeyboardButton(text="🔍 Найти трек")
    ]
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False) 
    keyboard.add(*buttons)
    return keyboard

# --- Вспомогательная функция для безопасного удаления сообщения ---
async def safe_delete_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except (MessageToDeleteNotFound, MessageCantBeDeleted) as e_del:
        logger.warning(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e_del}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при удалении сообщения {message_id} в чате {chat_id}: {e}")

# --- Функции отправки сообщений и обработки ---

async def send_audio_with_rating_prompt(chat_id: int, track_spotify_id: str, track_name: str, artist_name: str):
    """Отправляет аудиофайл и кнопку для оценки, используя Spotify ID."""
    loading_msg = None
    try:
        loading_msg = await bot.send_message(chat_id, "Загружаю аудио, это может занять некоторое время...")
        
        video_info = await youtube_agent.search_video(track_name, artist_name)

        if not video_info or 'id' not in video_info or 'videoId' not in video_info['id']:
            await bot.send_message(chat_id, "К сожалению, не удалось найти аудио для этого трека на YouTube.")
            logger.warning(f"YouTubeAgent: Видео не найдено для запроса: {track_name} - {artist_name}")
            return

        video_id = video_info['id']['videoId']
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        audio_file_path = await youtube_agent.download_audio(youtube_url)

        if audio_file_path and os.path.exists(audio_file_path):
            logger.info(f"Аудио '{audio_file_path}' скачано. Отправка пользователю {chat_id}.")
            try:
                with open(audio_file_path, 'rb') as audio_file:
                    rate_button = InlineKeyboardButton("⭐️ Оценить трек", callback_data=f"rateprompt_{track_spotify_id}")
                    keyboard = InlineKeyboardMarkup().add(rate_button)
                    await bot.send_audio(chat_id, audio_file, 
                                         reply_markup=keyboard, 
                                         caption=f"🎧 **{track_name}**\n_{artist_name}_",
                                         parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Аудио для Spotify ID {track_spotify_id} отправлено пользователю {chat_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке аудиофайла {audio_file_path} пользователю {chat_id}: {e}")
                await bot.send_message(chat_id, "Произошла ошибка при отправке аудио.")
            finally:
                logger.debug(f"Удаление временного аудиофайла: {audio_file_path}")
                try:
                    os.remove(audio_file_path)
                except OSError as e_os:
                    logger.warning(f"Не удалось удалить файл {audio_file_path}: {e_os}")
        else:
            logger.warning(f"Аудиофайл не был скачан или не найден для YouTube URL: {youtube_url}")
            await bot.send_message(chat_id, "Не удалось загрузить аудио для этого трека. Попробуйте другой.")
    finally:
        if loading_msg:
            await safe_delete_message(chat_id, loading_msg.message_id)


def register_handlers(dp: Dispatcher):
    logger.info("Регистрация хэндлеров...")

    @dp.message_handler(commands=['start', 'help'])
    async def cmd_start(message: types.Message):
        telegram_user_id = message.chat.id
        logger.info(f"Пользователь {telegram_user_id} запустил команду /start или /help")
        
        matrix_idx = await asyncio.to_thread(add_user_mapping, telegram_user_id) 
        if matrix_idx == -1:
            await message.reply("Произошла ошибка при инициализации вашего профиля. Пожалуйста, попробуйте позже.")
            return
        logger.info(f"Пользователь {telegram_user_id} (matrix_idx={matrix_idx}) инициализирован/зарегистрирован.")

        await message.reply("Привет! Я твой музыкальный рекомендательный бот.\n"
                            "Выбери действие:", reply_markup=get_main_keyboard())

    @dp.message_handler(text="🔍 Найти трек")
    async def find_track_command(message: types.Message):
        logger.info(f"Пользователь {message.chat.id} выбрал 'Найти трек'. Запрашиваем название.")
        await UserActions.waiting_for_track_name.set()
        await message.reply("Введите название трека (можно с исполнителем):", reply_markup=types.ReplyKeyboardRemove())

    @dp.message_handler(state=UserActions.waiting_for_track_name)
    async def process_track_name_input(message: types.Message, state: FSMContext):
        track_query = message.text
        # telegram_user_id = message.chat.id # Не используется здесь напрямую
        logger.info(f"Пользователь {message.chat.id} ищет трек по запросу: '{track_query}'")

        if not spotify_agent.sp: 
            await message.reply("К сожалению, сервис поиска музыки временно недоступен. Попробуйте позже.", reply_markup=get_main_keyboard())
            logger.error("Spotify клиент не был инициализирован, поиск невозможен.")
            await state.finish()
            return

        found_spotify_tracks = await spotify_agent.search_track(track_query, limit=5)

        if found_spotify_tracks: 
            await state.update_data(search_results=found_spotify_tracks) 
            
            inline_kb = InlineKeyboardMarkup(row_width=1)
            for i, track_info in enumerate(found_spotify_tracks):
                button_text = f"{track_info['name']} - {track_info['artist_name']}"
                callback_action = f"selectsearch_{i}"
                inline_kb.add(InlineKeyboardButton(text=button_text, callback_data=callback_action))
            
            inline_kb.add(InlineKeyboardButton(text="Отмена поиска", callback_data="cancel_search_selection"))
            
            sent_message_with_choices = await message.reply("Найдены следующие треки. Выберите один:", reply_markup=inline_kb)
            await state.update_data(choice_message_id=sent_message_with_choices.message_id)
            await UserActions.waiting_for_search_selection.set()
        else:
            logger.info(f"Трек по запросу '{track_query}' не найден в Spotify.")
            await message.reply(f"Трек по запросу '{track_query}' не найден. Попробуйте еще раз.", reply_markup=get_main_keyboard())
            await state.finish()

    @dp.callback_query_handler(lambda call: call.data.startswith("selectsearch_") or call.data == "cancel_search_selection", state=UserActions.waiting_for_search_selection)
    async def process_search_selection(callback: types.CallbackQuery, state: FSMContext):
        user_data = await state.get_data()
        choice_message_id = user_data.get('choice_message_id')

        if choice_message_id:
            await safe_delete_message(callback.message.chat.id, choice_message_id)
        elif callback.message: 
             try: 
                await bot.edit_message_reply_markup(callback.message.chat.id, callback.message.message_id, reply_markup=None)
                # Не удаляем само сообщение, если оно было от пользователя, а не от бота
                # await safe_delete_message(callback.message.chat.id, callback.message.message_id) 
             except MessageNotModified: 
                pass # Клавиатуры уже нет
                # await safe_delete_message(callback.message.chat.id, callback.message.message_id)
             except Exception as e_del_cb:
                logger.warning(f"Не удалось отредактировать/удалить сообщение с выбором трека (callback.message): {e_del_cb}")


        if callback.data == "cancel_search_selection":
            await bot.send_message(callback.from_user.id, "Поиск отменен.", reply_markup=get_main_keyboard())
            await state.finish()
            await callback.answer()
            return

        try:
            selected_index = int(callback.data.split("_")[1])
            search_results = user_data.get('search_results')

            if not search_results or selected_index >= len(search_results):
                await bot.send_message(callback.from_user.id, "Ошибка выбора трека. Попробуйте снова.", reply_markup=get_main_keyboard())
                await state.finish()
                await callback.answer("Ошибка выбора")
                return

            selected_track = search_results[selected_index] 
            track_spotify_id = selected_track['id']
            track_name = selected_track['name']
            artist_name = selected_track['artist_name'] 

            logger.info(f"Пользователь {callback.from_user.id} выбрал трек: {track_name} - {artist_name} (Spotify ID: {track_spotify_id}). Отправка аудио...")
            await send_audio_with_rating_prompt(callback.from_user.id, track_spotify_id, track_name, artist_name)
            await bot.send_message(callback.from_user.id, "Что делаем дальше?", reply_markup=get_main_keyboard())

        except Exception as e:
            logger.error(f"Ошибка при обработке выбора трека: {e}", exc_info=True)
            await bot.send_message(callback.from_user.id, "Произошла ошибка при выборе трека.", reply_markup=get_main_keyboard())
        finally:
            await state.finish()
            await callback.answer()


    @dp.callback_query_handler(lambda call: call.data.startswith("rateprompt_"))
    async def callback_prompt_rating(callback: types.CallbackQuery):
        track_spotify_id = callback.data.split("_")[1] 
        logger.info(f"Пользователь {callback.from_user.id} нажал 'Оценить трек' для Spotify ID={track_spotify_id}")

        # Убираем инлайн-клавиатуру с кнопки "Оценить трек" с аудио-сообщения
        if callback.message:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=None 
                )
            except MessageNotModified:
                logger.info("Сообщение с аудио уже не имело инлайн-клавиатуры или не было изменено.")
            except Exception as e_edit:
                logger.warning(f"Не удалось отредактировать reply_markup для аудио-сообщения: {e_edit}")
        
        buttons = [
            InlineKeyboardButton(str(num), callback_data=f"setrating_{track_spotify_id}_{num}")
            for num in range(1, 6)
        ]
        keyboard = InlineKeyboardMarkup(row_width=5).add(*buttons)
        
        # Отправляем новое сообщение с кнопками оценки
        await bot.send_message(
            chat_id=callback.from_user.id, 
            text="Пожалуйста, оцените трек от 1 до 5 (где 5 - отлично):",
            reply_markup=keyboard
        )
        await callback.answer()


    @dp.callback_query_handler(lambda call: call.data.startswith("setrating_"))
    async def callback_set_rating(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        track_spotify_id = parts[1] 
        rating = int(parts[2])
        telegram_user_id = callback.from_user.id

        logger.info(f"Пользователь {telegram_user_id} оценил Spotify ID='{track_spotify_id}' на {rating}")
        
        await asyncio.to_thread(save_track_rating, telegram_user_id, track_spotify_id, rating)

        # Удаляем сообщение с кнопками оценки ("Пожалуйста, оцените трек...")
        if callback.message:
            await safe_delete_message(callback.message.chat.id, callback.message.message_id)
        
        await callback.answer(f"Спасибо за вашу оценку ({rating})! 👍", show_alert=False)
        
        await bot.send_message(telegram_user_id, "Вы можете продолжить.", reply_markup=get_main_keyboard())


    @dp.message_handler(text="🎧 Получить рекомендации")
    async def get_recommendations_command(message: types.Message):
        telegram_user_id = message.chat.id
        logger.info(f"Пользователь {telegram_user_id} запросил рекомендации.")
        
        loading_msg = None
        try:
            if not await asyncio.to_thread(check_user_has_ratings, telegram_user_id):
                logger.info(f"У пользователя {telegram_user_id} нет оценок для генерации рекомендаций.")
                await message.reply("Сначала вам нужно найти и оценить хотя бы несколько треков.", reply_markup=get_main_keyboard())
                return

            loading_msg = await message.reply("Подбираю рекомендации для вас... Это может занять некоторое время. 🎶")
            
            recs = await generate_recommendations(telegram_user_id) 

            if not recs:
                logger.info(f"Для пользователя {telegram_user_id} не удалось сгенерировать рекомендации.")
                await message.reply("К сожалению, пока не удалось подобрать для вас рекомендации. Попробуйте оценить больше треков.", reply_markup=get_main_keyboard())
                return

            logger.info(f"Сгенерировано {len(recs)} рекомендаций для {telegram_user_id}.")
            await message.reply(f"Вот несколько треков, которые могут вам понравиться ({len(recs)} шт.):", reply_markup=get_main_keyboard())

            for i, track_data in enumerate(recs): 
                track_spotify_id = track_data['track_id'] 
                track_name = track_data['track_name']
                artist_display_name = ", ".join(track_data.get('artist_names', ["Неизвестный исполнитель"]))
                spotify_url = track_data.get('spotify_url', '')
                
                caption = f"✨ **{track_name}**\n👤 _{artist_display_name}_"
                if spotify_url and spotify_url != "N/A":
                    caption += f"\n[Слушать на Spotify]({spotify_url})"

                play_button = InlineKeyboardButton("🎵 Прослушать и оценить", callback_data=f"playrecom_{track_spotify_id}")
                keyboard = InlineKeyboardMarkup().add(play_button)
                
                await bot.send_message(message.chat.id, caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                if i < len(recs) - 1:
                    await asyncio.sleep(0.5)
        finally:
            if loading_msg:
                await safe_delete_message(message.chat.id, loading_msg.message_id)


    @dp.callback_query_handler(lambda call: call.data.startswith("playrecom_"))
    async def callback_play_recommended_track(callback: types.CallbackQuery):
        track_spotify_id = callback.data.split("_")[1] 
        telegram_user_id = callback.from_user.id
        logger.info(f"Пользователь {telegram_user_id} выбрал прослушать рекомендованный Spotify ID='{track_spotify_id}'")

        if callback.message: # Удаляем сообщение с рекомендованным треком
             await safe_delete_message(callback.message.chat.id, callback.message.message_id)

        if not spotify_agent.sp: 
            await bot.send_message(telegram_user_id, "Сервис музыки временно недоступен.", reply_markup=get_main_keyboard())
            await callback.answer("Сервис недоступен")
            return

        track_details = await spotify_agent.get_track_basic_info(track_spotify_id)

        if track_details:
            await send_audio_with_rating_prompt(
                telegram_user_id,
                track_spotify_id, 
                track_details['name'],
                track_details['artist_name'] 
            )
        else:
            logger.warning(f"Не удалось получить детали с Spotify для рекомендованного ID='{track_spotify_id}'")
            await bot.send_message(telegram_user_id, "Не удалось получить информацию об этом треке.", reply_markup=get_main_keyboard())
        
        await callback.answer()

    logger.info("Регистрация хэндлеров завершена.")


async def main():
    if not bot:
        logger.critical("Экземпляр бота не инициализирован в authorization.py! Выход.")
        return
    
    if not sp:
        logger.warning("Клиент Spotify (sp) не инициализирован в authorization.py.")
    if not youtube:
        logger.warning("Клиент YouTube (youtube) не инициализирован в authorization.py.")
    if not lastfm_network: 
        logger.warning("Клиент Last.fm (lastfm_network) не инициализирован в authorization.py.")

    dp = Dispatcher(bot, storage=storage)
    register_handlers(dp)

    logger.info("Запуск polling...")
    try:
        await dp.start_polling()
    finally:
        logger.info("Остановка бота.")
        await dp.storage.close()
        await dp.storage.wait_closed()
        session = await bot.get_session()
        if session:
            await session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)

