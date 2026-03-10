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
  "month": "2024-01"
}
```

`month` опціональний.
