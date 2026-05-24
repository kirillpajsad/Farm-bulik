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
import pytesseract
import cv2
import io
import numpy as np
from PIL import Image

# --- Настройки ---
API_ID = 35383753
API_HASH = '2acb2aa83e1a54f8a7c864f1ef41fcf0'
SESSION_STRING = os.getenv('SESSION_STRING') 

OWN_CHAT_ID = 8793273625 
CHANNEL_ID = -1001808189654 
BOT_TOKEN = '8686010063:AAGyAzdydCnKOMJlI7yRY6PfdA3gEFaxslQ'

# Путь к Tesseract внутри Linux-контейнера
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "Promo OCR Sniper (Lightweight) is Running"

def self_ping():
    url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:10000')
    while True:
        try:
            requests.get(url, timeout=10)
            logger.info("✅ Самопинг")
        except:
            pass
        time.sleep(5)

# --- Улучшенная легкая предобработка OpenCV + Tesseract ---
def extract_promo_from_image(image_bytes):
    try:
        # Читаем картинку из байт через OpenCV
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 1. Переводим в оттенки серого
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. Увеличиваем размер в 2 раза для лучшего распознавания мелких букв
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # 3. Адаптивная бинаризация (убирает дым, тени на мыле и делает текст контрастным)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Конвертируем обратно в формат PIL для Tesseract
        pil_img = Image.fromarray(thresh)
        
        # Запускаем распознавание (Английский язык, режим PSM 6 — единый блок текста)
        text = pytesseract.image_to_string(pil_img, config='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        logger.info(f"Распознанный текст: {text}")
        
        # Очистка
        full_text = text.upper().replace(" ", "").strip()
        
        # Ищем промокод регуляркой (от 5 до 9 заглавных букв и цифр)
        match = re.search(r'[A-Z0-9]{5,9}', full_text)
        if match:
            return match.group(0)
            
        return None
    except Exception as e:
        logger.error(f"Ошибка OCR: {e}")
        return None

async def main():
    user_client = TelegramClient(
        StringSession(SESSION_STRING), API_ID, API_HASH
    )
    bot_client = TelegramClient(
        'bot_session', API_ID, API_HASH
    )
    
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)
    logger.info("🚀 Легкий бот запущен и ждет посты!")

    @user_client.on(events.NewMessage(chats=CHANNEL_ID))
    async def handler(event):
        if event.photo:
            try:
                logger.info("📸 Обнаружено фото. Скачиваем в память...")
                image_bytes = await user_client.download_media(event.photo, bytes)
                
                # Обработка в отдельном потоке (теперь ест всего ~30МБ вместо 600МБ)
                promo_code = await asyncio.to_thread(extract_promo_from_image, image_bytes)
                
                if promo_code:
                    logger.info(f"🎯 Код успешно вытащен: {promo_code}")
                    
                    # 1. Сначала промокод
                    await bot_client.send_message(OWN_CHAT_ID, f"`{promo_code}`", parse_mode='markdown')
                    
                    # 2. Спам-алерт
                    spam_alert = "🚨 НОВОЕ ПРОМО... ❗❗❗❗\n" * 10
                    await bot_client.send_message(OWN_CHAT_ID, spam_alert)
                    
                    await asyncio.sleep(0.2)
                    
                    # 3. Еще 5 раз код
                    for _ in range(5):
                        await bot_client.send_message(OWN_CHAT_ID, f"`{promo_code}`", parse_mode='markdown')
                        await asyncio.sleep(0.15)
                else:
                    logger.warning("Промокод на фото не обнаружен фильтрами.")
            except Exception as e:
                logger.error(f"Ошибка обработчика: {e}")

    await user_client.run_until_disconnected()

if __name__ == '__main__':
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000))), daemon=True).start()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
