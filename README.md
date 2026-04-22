# UK Crime Radius Analyzer (Railway-ready)

Веб застосунок для аналізу подій злочинності за UK postcode і радіусом (в метрах).

## Що робить
- Геокодує postcode через `postcodes.io`
- Тягне події з `data.police.uk`
- Фільтрує події в межах заданого радіуса
- Показує інфографіку:
  - загальна кількість
  - топ-категорії
  - графік категорій
  - графік по місяцях
- Візуалізує події на Leaflet-мапі

## Локальний запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Деплой на Railway
1. Запуште репозиторій на GitHub.
2. Railway → New Project → Deploy from GitHub Repo.
3. Railway автоматично зчитає `Procfile` і запустить:
   `gunicorn app:app --bind 0.0.0.0:$PORT`

## API
### `POST /api/analyze`
```json
{
  "postcode": "SW1A 1AA",
  "radius": 300,
  "start_month": "2024-01",
  "end_month": "2024-03"
}
```

`start_month` і `end_month` — опціональні, але мають передаватися парою. Якщо не вказані, API повертає останні доступні дані.

Під капотом API робить запит до `data.police.uk` для кожного місяця в діапазоні.

## Police API rate-limit handling
- A small delay between multi-month requests is enabled by default: `POLICE_API_REQUEST_DELAY_SECONDS=0.07` (adjustable via env variable).
- For `429 Too Many Requests`, the app:
  - respects `Retry-After` response header when present;
  - otherwise uses exponential backoff (`POLICE_API_BACKOFF_BASE_SECONDS`, `POLICE_API_BACKOFF_MAX_SECONDS`);
  - retries up to `POLICE_API_MAX_RETRIES_429`.
