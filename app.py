import re
import csv
import asyncio
from aiogram import Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from decimal import Decimal
import authorization
import dynamo_get_table
from queue import Queue
from Bot import bot


sp = authorization.authorize()

# Функция для получения данных
def get_data():
    table    = dynamo_get_table.get_dynamodb_table()
    response = table.scan()
    data     = response['Items']
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        data.extend(response['Items'])
    return data  

# Функция для получения рекомендаций
def recommend(track_ids, n_recs=5):
    data        = get_data()
    total_diffs = [0] * len(data)
    for track_id in track_ids:
        track_features = sp.track_audio_features(track_id)
        track_valence = Decimal(str(track_features.valence))
        track_energy = Decimal(str(track_features.energy))

        for i, item in enumerate(data):
            diff_valence    = abs(track_valence - item['mood_vec'][0])
            diff_energy     = abs(track_energy - item['mood_vec'][1])  
            total_diffs[i] += diff_valence + diff_energy

    for i, item in enumerate(data):
        item['total_diffs'] = total_diffs[i]

    sorted_data = sorted(data, key=lambda item: item['total_diffs'])[:n_recs]

    return sorted_data

  # Сохранение оценки в CSV
def save_rating(user_id, track, rating):
  with open('ratings.csv', 'a') as f: 
    writer = csv.writer(f)
    writer.writerow([user_id, track['id'], rating])

recs = []

dp = Dispatcher(bot, storage=MemoryStorage())
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
current_track = None
rated_tracks = []

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


TRACK_ID_RE = re.compile(r'[a-zA-Z0-9]{22}(?:[,][a-zA-Z0-9]{22})*')  
@dp.message_handler()
async def process_tracks(message: types.Message):
  if TRACK_ID_RE.match(message.text):
    tracks = message.text.split(", ")
    global recs

    recs = recommend(tracks) 
    ans = "Рекомендации для пользователя {}:"

    for track in recs:
        ans += "\n{} - {}".format(track['artist_name'], track['track_name'])

    await message.answer(ans)
  else:
    await message.reply("Неверный формат ID")  


if __name__ == '__main__':
    asyncio.run(dp.start_polling())
