# QSolutions: Docker Web Service & Company Impressum Extraction with DeepSeek

Веб-сервис и программный комплекс для:
1. **Задание 1 & 2**: автоматической записи, хранения, зумирования (Camtasia-style zoom effect) и предпросмотра видео в Docker (`web`: Apache 2.4 + `mod_wsgi` + Flask + FFmpeg, `db`: PostgreSQL 16).
2. **Задание 3**: импорта реестра компаний из CSV, веб-интерфейса загрузки, поиска страниц Impressum/Imprint, оптимизации токенов и структурированного извлечения юридических реквизитов через DeepSeek API.

---

## 🌐 Развертывание и сетевая конфигурация (любой хост / IP / домен)

Сервис полностью готов к работе **как локально, так и на удаленном сервере / VPS / в локальной сети** (не привязан к `localhost`):
* **Apache**: настроен с директивой `ServerAlias *` — корректно принимает запросы по любому IP-адресу, хостнейму или доменному имени.
* **Flask эндпоинты**: генерируют внешние ссылки динамически через `request.host_url` — все ссылки на медиа и страницы адаптируются к адресу, по которому обратился клиент (например, `http://192.168.1.100:8000` или `http://my-server.com:8000`).
* **Docker Compose**: пробрасывает порты `0.0.0.0:8000:80` (веб) и `0.0.0.0:5432:5432` (PostgreSQL), делая их доступными извне.
* **CLI-скрипты**: скрипты `enrich_companies.py`, `view_companies.py` и клиенты поддерживают подключение к любой внешней базе данных через аргументы `--db-host <IP>` (или переменную окружения `DB_HOST`).

### Быстрый запуск Docker-стека:

```bash
# Клонирование и переход в репозиторий
cd Test_Task_QSolutions

# Сборка и запуск контейнеров в фоне
docker compose up --build -d

# Проверка статуса (web и db должны быть healthy / running)
docker compose ps
```

Доступ к веб-интерфейсу:
* Локально: **`http://localhost:8000`**
* На удаленном сервере / в локальной сети: **`http://<IP_ИЛИ_ДОМЕН_СЕРВЕРА>:8000`**

---

## 🏢 Задание 3: Импорт компаний и извлечение данных Impressum через DeepSeek

### 1. Настройка DeepSeek API ключа

Ключ API хранится в файле `.env` (добавлен в `.gitignore` и защищен от коммитов):
* **Быстрая настройка в 1 клик (Windows)**: запустите `set_deepseek_key.bat` или выполните:
  ```bash
  python set_deepseek_key.py <ВАШ_DEEPSEEK_API_KEY>
  ```
* Ключ автоматически считывается скриптом `enrich_companies.py` и пробрасывается в контейнер веб-сервиса через `docker-compose.yml` (`DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:-}`).

---

### 2. Импорт CSV и веб-интерфейс (§1, §3)

* **`GET /upload_companies`** — минималистичный HTML-интерфейс для загрузки CSV через браузер:
  * Откройте `http://<HOST>:8000/upload_companies`
  * Выберите CSV-файл (например, `companies.csv`) и нажмите **Upload & Import**.
* **`POST /upload_companies`** — программный эндпоинт загрузки CSV (`multipart/form-data`, поле `file`):
  ```bash
  curl -F "file=@companies.csv" http://<HOST>:8000/upload_companies
  # Ответ: {"imported": 0, "total_rows": 2, "updated": 2}
  ```
  * Формат CSV: кодировка UTF-8, разделитель `;`, квалификатор `"`, колонки: `URL;Company Name;Language;Country;Postcode;City;Street;HouseNo;Web`.
  * **Идемпотентность**: при повторном импорте обновляются только исходные поля CSV (`ON CONFLICT (company_name) DO UPDATE`). Статус обработки (`status`), найденный `impressum_url` и извлеченные юридические данные **не затираются**.
* **`GET /companies`** — получение всех записей в JSON. Поддерживает фильтрацию по статусу:
  * `GET /companies?status=0` — только успешно распознанные компании с полным адресом;
  * `GET /companies?status=pending` (или `?status=null`) — только ожидающие обработки.
* **`GET /companies/<company_name>`** — детальные данные одной компании в JSON (возвращает 404, если компания не найдена).

---

### 3. Скрипт обогащения данных `enrich_companies.py` (§4)

Автономный скрипт подключается к PostgreSQL, обрабатывает компании в порядке возрастания `id`:
1. Нормализует адрес сайта (`web`): при пустом значении ставит `status = 5` (`NO_WEBSITE`), при отсутствии схемы добавляет `https://`.
2. Загружает главную страницу и находит ссылку на Impressum/Imprint (сначала по точному тексту, затем по `href`, с резолвом относительных URL). Если ссылка не найдена — ставит `status = 1` (`NO_IMPRESSUM_LINK_FOUND`).
3. Загружает страницу Impressum, очищает невидимый/служебный HTML (`script`, `style`, `nav`, `header`, `footer`, `form` и т.д.) и оптимизирует текст по бюджету токенов.
4. Отправляет очищенный текст в DeepSeek API (режим `json_object`, системный промпт с эталонной схемой).
5. Проверяет полноту реквизитов и выставляет статус:
   * `0 (OK)`: поля извлечены и адрес полный (`postcode`, `city`, `street`, `house_no`);
   * `2 (PARSING_FAILED)`: пустой ответ или нет распознанных полей;
   * `3 (ADDRESS_INCOMPLETE)`: реквизиты есть, но адрес неполный;
   * `4 (ERROR)`: ошибка сети / HTTP 4xx/5xx / ошибка API (обработка остальных компаний продолжается без падения).
6. **Декомпозиция адреса**: извлеченный адрес сохраняется как в виде единой строки `postal_address`, так и распарсенным по отдельным колонкам PostgreSQL: `postcode` (PostalCode), `city` (City), `street` (Street), `house_no` (HouseNo) и `country` для дальнейших задач.

#### Примеры запуска:
```bash
# Обработка всех ожидающих компаний (status IS NULL или status <> 0)
python enrich_companies.py

# Подключение к внешней/удаленной базе данных:
python enrich_companies.py --db-host 192.168.1.100 --db-port 5432

# Обработка конкретной компании:
python enrich_companies.py --company "Barolo & Champagne GbR"

# Тестовый прогон без списания токенов DeepSeek:
python enrich_companies.py --dry-run
```

---

### 4. Оптимизация бюджета токенов `impressum.py` (§5 — The Core Challenge)

Отправка всей страницы Impressum целиком неэффективна из-за информационного шума (куки-баннеры, навигация, списки категорий, футеры и дисклеймеры). 

Реализована стратегия **двусторонней обрезки («Sandwich cut»)**:
1. **Порог**: `MAX_TEXT_CHARS = 8000` (~2000 токенов). Если текст меньше порога — отправляется без изменений.
2. **Фильтрация шума**: удаление строк boilerplate (баннеры согласия с куки, меню, ссылки категорий).
3. **Head Anchor**: поиск открывающего заголовка юридического блока (`Impressum`, `Angaben gemäß § 5 TMG / DDG`, `Anbieterkennzeichnung`) с оценкой плотности юридических терминов.
4. **Tail Anchors**: поиск последнего вхождения юридических маркеров (телефон с кодом `+49`, номер плательщика НДС `DE\d{9}`, e-mail, `HRB/HRA/Amtsgericht`, ответственные лица `Geschäftsführer/Vorstand`).
5. **Срез**: сохраняется блок `[head_start - margin : last_tail_match + 400 chars]`.
6. **Верификация**: проверка сохранения смысловых якорей и логирование экономии.

> **Результат на реальных данных**: на компании `Barolo & Champagne GbR` объем текста сократился с **8 992** до **3 444** символов — **экономия 61.7% токенов** с сохранением 100% необходимых реквизитов.

---

### 5. Просмотр данных в PostgreSQL (`view_companies.py` / `view_companies.bat`)

Утилита для наглядного отображения состояния таблицы `companies`:
```bash
# Сводная таблица (ID, компания, статус, Street & HouseNo, Postcode & City, VAT, реестр)
python view_companies.py
# (или view_companies.bat)

# Полная карточка всех реквизитов (включая распарсенные поля адреса) и raw_json:
python view_companies.py --detail

# Поиск конкретной компании:
python view_companies.py --company "nutrimmun"

# Подключение к удаленному серверу:
python view_companies.py --db-host 192.168.1.100
```

---

### 6. Автоматическое тестирование

Для запуска тестов **только Задания 3**:
* **Windows (1 клик)**: `test_task3.bat`
* **Командная строка**:
  ```bash
  python -m unittest test_task3.py -v
  ```

Набор включает 23 автотеста:
* Нормализация URL и регистронезависимый поиск Impressum/Imprint с фолбэком по `href`;
* Очистка тегов HTML и алгоритм sandwich cut оптимизации токенов;
* Логика выставления статусов `0 (OK)`, `1 (NO_IMPRESSUM)`, `2 (PARSING_FAILED)`, `3 (ADDRESS_INCOMPLETE)`, `4 (ERROR)`, `5 (NO_WEBSITE)`;
* Тест JSON-модели DeepSeek с моком;
* Интеграционные тесты веб-эндпоинтов `GET/POST /upload_companies`, `GET /companies`, `GET /companies/<name>`;
* **Сквозные тесты на компаниях из `companies.csv`**:
  * `test_21_companies_csv_end_to_end` — загрузка `companies.csv`, проверка сохранения в БД, резолв ссылок и извлечение реквизитов;
  * `test_22_companies_csv_reimport_preserves_enrichment` — проверка идемпотентности и сохранения результатов обогащения при повторном импорте;
  * `test_23_parsed_address_fields_stored_in_postgres` — прямая проверка сохранения и корректности отдельных колонок `postcode`, `city`, `street`, `house_no` в PostgreSQL.

---

## 📹 Задания 1 & 2: Видеосервис и Camtasia Zoom

* **Горячая клавиша F5**: 1-е нажатие — приближение к точке мыши (Zoom-In), 2-е нажатие — отдаление (Zoom-Out).
* **Скрипт интерактивной записи**: `record_interactive.bat` (или `python record_interactive.py --url https://duckduckgo.com`).
* **Постобработка FFmpeg**: `python apply_zoom.py --video <path_to_video>`.
* **Тесты видеосервиса**:
  ```bash
  # Тесты зума
  pytest test_zoom.py -v
  # Интеграционные тесты API сервиса
  python test_service.py -v
  ```
