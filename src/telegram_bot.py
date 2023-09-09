import re
import os
import models 
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from database import save_track_rating, save_track

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
            track_id = track['id']
            save_track(message.chat.id, track_id) 
            if track:
                await message.reply("Ищем")
                youtube_query = f"{track['name']} {track['artist']}"
                video = youtube_search(youtube_query)
                await message.reply("Скачиваем")
                url = f"https://youtu.be/{video['id']['videoId']}"
                audio_path = download_audio(url)
                await bot.send_message(chat_id=message.chat.id, text = "Отправляем")
                btn = InlineKeyboardButton("Оценить трек", callback_data=f"rate1_{track_id}") 
                keyboard = InlineKeyboardMarkup().add(btn)
                await bot.send_audio(chat_id=message.chat.id, audio=open(audio_path, 'rb'), reply_markup=keyboard)
                os.remove(audio_path)
            else:
                await message.reply("Трек не найден")

    @dp.callback_query_handler(lambda call: call.data.startswith("rate1"))
    async def callback_rate(callback: types.CallbackQuery):
        track_id = callback.data.split("_")[1]
        buttons = [
            InlineKeyboardButton(text, callback_data=f"rate_{track_id}_{text}") 
            for text in ["1", "2", "3", "4", "5"]  
        ]
        keyboard = InlineKeyboardMarkup()
        keyboard.row(*buttons)
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text="Оцените от 1 до 5",
            reply_markup=keyboard
        )

    @dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
    async def rate_track(callback: types.CallbackQuery):
        track_id = callback.data.split("_")[1]
        user_id = callback.from_user.id
        rating = int(re.search('\d+', callback.data).group()) 
        save_track_rating(user_id, track_id, rating)
        await bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id, 
            message_id=callback.message.message_id,
            reply_markup=None
        )
        await bot.send_message(
            callback.message.chat.id, 
            'Спасибо за оценку! /start'  
        )

