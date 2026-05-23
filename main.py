import os
import re
import asyncio
import logging
import threading
import time
import requests
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import easyocr
import io
import numpy as np
from PIL import Image

# --- Настройки ---
API_ID = 35383753
API_HASH = '2acb2aa83e1a54f8a7c864f1ef41fcf0'
SESSION_STRING = os.getenv('SESSION_STRING') 

# Твой личный Telegram ID (указан как число)
OWN_CHAT_ID = 8793273625 

# ID целевого канала (указан как число, Telethon сам поймет префикс -100)
CHANNEL_ID = -1001808189654 

# Токен твоего официального бота, который будет присылать уведомления
BOT_TOKEN = '8686010063:AAGyAzdydCnKOMJlI7yRY6PfdA3gEFaxslQ'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализируем EasyOCR для английского языка
reader = easyocr.Reader(['en'], gpu=False)

# --- Flask для анти-засыпания ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Promo OCR Sniper (EasyOCR) is Running"

def self_ping():
    url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:10000')
    while True:
        try:
            requests.get(url, timeout=10)
            logger.info("✅ Самопинг")
        except:
            pass
        time.sleep(5)

# --- Логика распознавания ---
def extract_promo_from_image(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        
        results = reader.readtext(image_np, detail=0)
        logger.info(f"Найденный сырой текст: {results}")
        
        full_text = "".join(results).upper().replace(" ", "")
        
        # Регулярка для поиска промокода (заглавные буквы и цифры от 5 до 9 символов)
        match = re.search(r'[A-Z0-9]{5,9}', full_text)
        
        if match:
            return match.group(0)
        
        for word in results:
            clean_word = word.strip().upper()
            if 4 < len(clean_word) < 10 and clean_word.isalnum():
                return clean_word
                
        return None
    except Exception as e:
        logger.error(f"Ошибка EasyOCR: {e}")
        return None

async def main():
    # Клиент-юзербот (для чтения канала по ID)
    user_client = TelegramClient(
        StringSession(SESSION_STRING), API_ID, API_HASH
    )
    
    # Клиент-бот (для отправки сообщений тебе в личку)
    bot_client = TelegramClient(
        'bot_session', API_ID, API_HASH
    )
    
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)
    logger.info("🚀 Оба клиента успешно запущены по ID!")

    # Настраиваем хендлер на точный ID канала
    @user_client.on(events.NewMessage(chats=CHANNEL_ID))
    async def handler(event):
        if event.photo:
            try:
                logger.info("📸 Обнаружено новое фото в целевом канале. Скачиваем...")
                image_bytes = await user_client.download_media(event.photo, bytes)
                
                # Распознаем в отдельном потоке
                promo_code = await asyncio.to_thread(extract_promo_from_image, image_bytes)
                
                if promo_code:
                    logger.info(f"🎯 Распознан код: {promo_code}")
                    
                    # 1. ПЕРВЫМ бот отправляет сам промокод моноширинным текстом
                    await bot_client.send_message(
                        OWN_CHAT_ID,
                        f"`{promo_code}`",
                        parse_mode='markdown'
                    )
                    
                    # 2. СРАЗУ ЖЕ отправляет блок спама из 10 строк
                    spam_alert = "🚨 НОВОЕ ПРОМО... ❗❗❗❗\n" * 10
                    await bot_client.send_message(OWN_CHAT_ID, spam_alert)
                    
                    # Небольшая микро-пауза (0.2 сек)
                    await asyncio.sleep(0.2)
                    
                    # 3. ПОТОМ отправляет это промо еще 5 раз отдельными сообщениями
                    for _ in range(5):
                        await bot_client.send_message(
                            OWN_CHAT_ID,
                            f"`{promo_code}`",
                            parse_mode='markdown'
                        )
                        await asyncio.sleep(0.15)
                        
                    logger.info("🎯 Все уведомления отправлены ботом!")
                else:
                    logger.warning("Промокод на фото не найден.")
                    
            except Exception as e:
                logger.error(f"Ошибка в обработчике: {e}")

    # Держим запущенным основного слушателя событий
    await user_client.run_until_disconnected()

if __name__ == '__main__':
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000))), daemon=True).start()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
