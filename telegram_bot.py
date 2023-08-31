import re

from aiogram import types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

recs = []
current_track = None
rated_tracks = []
def start(bot, dp):
    
    # Хэндлер на команду /start    
    @dp.message_handler(commands=['start'])
    async def cmd_start(message: types.Message):

        buttons = [
            types.KeyboardButton(text="Получить рекомендации"),
            types.KeyboardButton(text="Оценить трек")
        ]
        
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(*buttons)
    
        await message.reply("Выберите действие", reply_markup=keyboard)


    @dp.message_handler(text="Получить рекомендации")
    async def cmd_recommend(message: types.Message):
        buttons = [
        types.InlineKeyboardButton(text="На основе id", callback_data="get_recs"), 
        types.InlineKeyboardButton(text="На основе оценок", callback_data="by_rating")
        ]
    
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(*buttons)
        await message.reply("Как именно", reply_markup=keyboard)

    @dp.callback_query_handler(text="get_recs")
    async def get_recs(callback: types.CallbackQuery):
    
        await callback.message.reply("Пришли ID треков через запятую")

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
        from app import save_rating
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


    @dp.message_handler()
    async def process_tracks(message: types.Message):
        TRACK_ID_RE = re.compile(r'[a-zA-Z0-9]{22}(?:[,][a-zA-Z0-9]{22})*')
        if TRACK_ID_RE.match(message.text):
            tracks = message.text.split(", ")
            global recs
            from app import recommend
            recs = recommend(tracks) 
            ans = "Рекомендации для пользователя:"

            for track in recs:
                ans += "\n{} - {}".format(track['artist_name'], track['track_name'], "https://spotify.com/track")

            await message.answer(ans)
        else:
            await message.reply("Неверный формат ID")  
    return dp
