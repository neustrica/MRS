# Базовый образ
FROM python:3.8

# Создаем директорию для приложения
WORKDIR /app

# Копируем файлы приложения  
COPY requirements.txt .
COPY app.py .
COPY telegram_bot.py .
COPY ratings.csv .

# Устанавливаем зависимости
RUN pip install -r requirements.txt

# Создаем директорию для данных
RUN mkdir /data 

# Добавляем volume для данных
VOLUME ["/data"]

# Запускаем бота
CMD [ "python", "app.py" ]