import re
import os
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

recs = []
current_track = None
rated_tracks = []
def start(bot, dp):

    @dp.message_handler(commands=['start'])
    async def cmd_start(message: types.Message):
        buttons = [
            types.KeyboardButton(text="Получить рекомендации"), 
            types.KeyboardButton(text="Найти трек")
        ]

        keyboard = types.ReplyKeyboardMarkup()
        keyboard.add(*buttons)

        await message.reply("Выберите действие", reply_markup=keyboard)

    @dp.message_handler(text="Найти трек")
    async def find_track(message: types.Message):
        await message.reply("Введите название трека")

        @dp.message_handler()
        async def search_track(message: types.Message):
            await message.reply("Подождите, ищем трек")
            from app import search_track, youtube_search, download_audio
            track = search_track(message.text)

            if track:
                await message.reply("Ищеи видео")
                youtube_query = f"{track['name']} {track['artist']}"
                video = youtube_search(youtube_query)
                await message.reply("Скачиваем")
                url = f"https://youtu.be/{video['id']['videoId']}"
                audio_path = download_audio(url)
                await bot.send_message(chat_id=message.chat.id, text = "отправляю")
                btn = InlineKeyboardButton("Оценить трек", callback_data="rate")
                keyboard = InlineKeyboardMarkup().add(btn)
                await bot.send_audio(chat_id=message.chat.id, audio=open(audio_path, 'rb'), reply_markup=keyboard)
                os.remove(audio_path)
            else:
                await message.reply("Трек не найден")

    @bot.callback_query_handler(func=lambda call: call.data == "rate")
    async def callback_rate(call):
        buttons = [
            InlineKeyboardButton("1", callback_data=str(1)),
            InlineKeyboardButton("2", callback_data=str(2)),
            InlineKeyboardButton("3", callback_data=str(3)),
            InlineKeyboardButton("4", callback_data=str(4)),
            InlineKeyboardButton("5", callback_data=str(5))
        ]
        
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.callback_query_handler(func=lambda call: call.data in ["1", "2", "3", "4", "5"])  
    async def process_rate(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        track_id = callback.data # id трека
        rating = int(callback.data)
        from database import save_track_rating
        save_track_rating(user_id, track_id, rating)

        await callback.answer()

    @dp.message_handler(text="Оценить трек")
    async def rate_tracks(message):

        global current_track
        global msg

        if not current_track:  
            current_track = recs[0]

        buttons = [
            types.InlineKeyboardButton(text, callback_data=f"rate_{text}") 
            for text in ["1", "2", "3", "4", "5"]
        ]

        keyboard = types.InlineKeyboardMarkup().add(*buttons)

        msg = await message.reply(f"Оцените трек: {current_track['track_name']}", reply_markup=keyboard) 

    @dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
    async def rate_track(callback: types.CallbackQuery):

        global current_track
        global rated_tracks
        global msg

        # сохраняем рейтинг
        rating = int(callback.data.split("_")[1])
        from src.app import save_rating
        save_rating(callback.from_user.id, current_track, rating) 

        rated_tracks.append(current_track['id'])  
        
        buttons = [
            types.InlineKeyboardButton(text, callback_data=f"rate_{text}") 
            for text in ["1", "2", "3", "4", "5"]
        ]
        keyboard = types.InlineKeyboardMarkup().add(*buttons)
            
        current_index = recs.index(current_track)
        if current_index < len(recs) - 1:
            current_track = recs[current_index + 1]
            await msg.edit_text(f"Оцените трек: {current_track['track_name']}")
            await msg.edit_reply_markup(reply_markup=keyboard)

        else:
            await callback.message.reply("Оценка завершена! /start")


