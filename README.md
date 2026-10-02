# Last Ball Standing - otomatik video botu

Her gün yeni bir "country ball" eleme videosu üretir (fizik simülasyonu, telifsiz müzik ve efektler)
ve Telegram'a video + başlık + açıklama + etiketler olarak gönderir.

- Zamanlama: .github/workflows/daily.yml içindeki cron satırı (UTC). Varsayılan 09:00 UTC = 12:00 Türkiye.
- Elle çalıştırma: Actions > Daily video > Run workflow (count = kaç video).
- Gerekli secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
- Yerelde: pip install -r requirements.txt (ffmpeg gerekir), sonra python lbs.py
