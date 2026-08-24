# Command Zone — FastAPI cEDH Manager

Учебное приложение для игроков, турниров, парингов и результатов cEDH.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Откройте http://localhost:8000. Без настроек используется SQLite `cedh.db`.

## Внешний PostgreSQL

Создайте бесплатную базу Neon или Supabase и задайте строку подключения:

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require'
uvicorn app.main:app --reload
```

Та же переменная задаётся на Render при публикации. Секрет нельзя добавлять в Git.

## Вход через Google

Создайте OAuth client типа **Web application** в Google Cloud и добавьте точный redirect URI:

```text
https://cedh-command-zone.onrender.com/auth/google/callback
```

В Render задайте переменные окружения:

```text
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://cedh-command-zone.onrender.com/auth/google/callback
```

Google-email пользователя заранее указывается администратором во вкладке «Пользователи». Парольный вход остаётся резервным.
