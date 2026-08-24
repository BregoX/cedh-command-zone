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
