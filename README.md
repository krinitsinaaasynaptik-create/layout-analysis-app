# Анализ вариативности планировок ССК

Локальный веб-сервис для сбора каталога квартир Железно по Кирову и анализа типовых планировок по проектам и домам.

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Открыть: http://127.0.0.1:8000

### Запуск с Postgres

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require'
export USE_LOCAL_IMAGE_FILES=0
uvicorn app.main:app --host 127.0.0.1 --port 8002
```

## Деплой на Vercel

В проект уже добавлены:

- `vercel.json`
- serverless entrypoint `api/index.py`
- режим работы с Postgres через `DATABASE_URL`
- отключение локальной раздачи картинок через `USE_LOCAL_IMAGE_FILES=0`

### Переменные окружения в Vercel

Обязательные:

- `DATABASE_URL` — строка подключения к Postgres
- `USE_LOCAL_IMAGE_FILES=0`

Опциональные:

- `OBJECTIV_ACCESS_TOKEN` — если нужен сбор данных из Объектива через `/api/refresh`

### Настройки проекта в Vercel

- Framework Preset: `Other`
- Build Command: не нужен
- Output Directory: не нужен

### Важно

- Данные уже вынесены в Postgres.
- Интерфейс больше не зависит от локальной папки с картинками.
- `/api/refresh` на Vercel все еще может упираться в лимиты serverless по времени, потому что это длинный парсинг. Для production лучше выносить обновление данных в отдельный job/worker.

## Отдельный refresh worker / cron

В проект добавлены:

- CLI-скрипт: `scripts/refresh_data.py`
- GitHub Actions workflow: `.github/workflows/refresh-data.yml`

### Локальный запуск worker

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require'
export OBJECTIV_ACCESS_TOKEN='...'
export KSM_PHPSESSID='...'
./.venv/bin/python scripts/refresh_data.py --developer-id ksm --no-report
```

Для полного прохода по одному застройщику укажите его `id`.  
Если `--developer-id` не передан, скрипт прогонит все targets.

### GitHub Actions secrets

Для cron в GitHub нужно задать secrets:

- `DATABASE_URL`
- `OBJECTIV_ACCESS_TOKEN`
- `KSM_PHPSESSID`

### Как это работает

- Vercel остается только интерфейсом;
- worker запускается в GitHub Actions по cron или вручную;
- результаты refresh пишутся прямо в Postgres;
- фронт на Vercel читает уже обновленные данные из Postgres.

## Что делает сервис

- собирает квартиры с `https://zhcom.ru/flats`;
- при наличии `OBJECTIV_ACCESS_TOKEN` собирает группу `КССК` как собственное предложение, а также группы конкурентов `СМУ-5`, `Стройсоюз`, `АлтайСтрой`, `Профстрой`, `КСМ`, `Авитек`, `Маяковская`, `Кино Девелопмент`, `Арсо Групп`, `Гипромстрой`, `Мой дом` и `СтройСити` из Объектива;
- группирует планировки внутри каждого дома и комнатности;
- объединяет визуально похожие планировки через perceptual hash;
- считает коэффициент вариативности: `типовые планировки / квартиры дома * 100`;
- показывает отчет в интерфейсе и отдает JSON/CSV.

## API

- `GET /` — интерфейс отчета.
- `POST /api/refresh` — обновить данные.
- `GET /api/report` — JSON отчета.
- `GET /api/export.csv` — CSV выгрузка.
