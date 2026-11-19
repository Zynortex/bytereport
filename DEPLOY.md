# Деплой ByteReport на бесплатные сервисы

Схема: **Vercel** — сайт, **Render Free** — API, **Supabase Free** — вход и база, **cron-job.org** — пинг, чтобы API не засыпал. Всё бесплатно, кроме OpenAI (около $0,03 за отчёт).

Порядок важен: сначала Render (нужен его адрес), потом Vercel (нужен адрес сайта), потом снова Render (вписать адрес сайта в CORS).

Везде ниже:
- `https://bytereport-api.onrender.com` — адрес API, который выдаст Render;
- `https://bytereport.vercel.app` — адрес сайта, который выдаст Vercel.

Подставьте свои.

---

## 0. Перед началом: новый публичный репозиторий и новые ключи

В истории текущего репозитория лежат старые `.env` с живыми ключами, поэтому публиковать его нельзя. Публикуем новый репозиторий: один коммит, без истории.

1. **Смените ключи**, раз старые попадали в git:
   - **OpenAI:** удалите старый ключ (platform.openai.com → API keys → Revoke). Новый создадите в шаге 4.
   - **Supabase:** Project Settings → **JWT Keys** (или API Keys) → ротация. Старые anon и service_role перестанут работать. Новые значения понадобятся в шагах 1 и 2.

2. **Узнайте свой noreply-адрес GitHub:** GitHub → Settings → Emails → включите «Keep my email addresses private». Ниже появится адрес вида `12345678+login@users.noreply.github.com`. Автор коммита в публичном репозитории виден всем, поэтому личную почту туда не ставим.

3. **Соберите репозиторий** из папки текущего репозитория (все изменения должны быть закоммичены):
   ```bash
   python tools/make_public_repo.py ../bytereport-public --email 12345678+login@users.noreply.github.com
   ```
   Скрипт:
   - берёт файлы последнего коммита;
   - выкидывает `.env`, `venv`, `node_modules`, `dist`, логи и `.claude/`;
   - проверяет результат сканером секретов (`tools/secret_scan.py`) и при любой находке останавливается;
   - делает один коммит.

   Сам ничего не пушит.

4. **Создайте пустой репозиторий** на GitHub (New repository, без README и .gitignore) и отправьте код:
   ```bash
   cd ../bytereport-public
   git remote add origin https://github.com/<login>/bytereport.git
   git push -u origin main
   ```

---

## 1. Render: API

1. render.com → войдите через GitHub.
2. **New → Blueprint** → выберите репозиторий `bytereport`. Render прочитает `render.yaml` из корня:
   - Python 3.11.9;
   - сборка: `pip install -r bytereport/requirements.txt`;
   - старт: `cd bytereport && uvicorn main:app --host 0.0.0.0 --port $PORT`;
   - проверка здоровья: `/health`;
   - тариф Free, регион Frankfurt;
   - `ENVIRONMENT=production`: CORS пускает только адреса из `ALLOWED_ORIGINS`. Локально по умолчанию `development`, и там подходит любой порт localhost.
3. Render попросит значения переменных. Где их взять:

   | Переменная | Что вписать |
   |---|---|
   | `OPENAI_API_KEY` | ключ проекта `bytereport-prod`, шаг 4. Можно сначала оставить пустым и вписать позже |
   | `SUPABASE_URL` | Supabase → Project Settings → API → Project URL (`https://xxxx.supabase.co`) |
   | `SUPABASE_ANON_KEY` | там же, ключ **anon** (publishable) |
   | `SUPABASE_SERVICE_KEY` | там же, ключ **service_role** (secret). Только здесь, больше нигде |
   | `ALLOWED_ORIGINS` | пока можно оставить пустым; после шага 2 — адрес сайта на Vercel. Пока он пуст, сайт до API не достучится: в production localhost не пускается |
   | `UNLIMITED_REPORT_EMAILS` | ваша почта для входа в ByteReport: с неё отчёты не списываются |

   `AI_MOCK` **не задавайте**: на сервере нужен настоящий AI.
4. **Apply.** Первая сборка идёт 3–6 минут.
5. Проверьте в браузере:
   - `https://bytereport-api.onrender.com/health` → `{"status":"ok", ...}`;
   - `https://bytereport-api.onrender.com/health/deep` → `"database":"ok"`.

   Если `/health/deep` отвечает `unavailable`, неверны `SUPABASE_URL` или ключ: Render → Logs покажет код ответа Supabase.

Если база новая: Supabase → SQL Editor → по очереди выполните файлы из `supabase/migrations` (по имени файла). Каждый можно запускать повторно.

---

## 2. Vercel: сайт

1. vercel.com → войдите через GitHub → **Add New → Project** → импортируйте `bytereport`.
2. **Root Directory:** `bytereport-frontend`. Framework определится сам (Vite), команды возьмутся из `vercel.json`.
3. Проверьте, что включено **«Include source files outside of the Root Directory in the Build Step»** (Settings → Build and Deployment → Root Directory; у новых проектов включено по умолчанию). Сайт при сборке читает общие файлы из корня репозитория: `report-copy.json`, `pricing.json`, `design-tokens.json`, `report-blocks.json`. Без этой галочки сборка упадёт.
4. **Environment Variables:**

   | Переменная | Значение |
   |---|---|
   | `VITE_API_URL` | `https://bytereport-api.onrender.com` (без `/` в конце) |
   | `VITE_SUPABASE_URL` | как `SUPABASE_URL` в Render |
   | `VITE_SUPABASE_ANON_KEY` | ключ **anon**. Никогда не service_role: всё из `VITE_` попадает в публичный JavaScript |
   | `VITE_SITE_URL` | адрес сайта, например `https://bytereport.vercel.app` (для превью ссылки на `/demo`) |

5. **Deploy.** Переменные `VITE_` вшиваются при сборке: если поменяли их позже, нажмите Redeploy.
6. Вернитесь в **Render → Environment**. Впишите в `ALLOWED_ORIGINS` адрес сайта ровно так, как он в адресной строке, без `/` в конце. Несколько адресов — через запятую. Нажмите **Save and deploy**.

Ссылка на демо для портфолио: **`https://bytereport.vercel.app/demo`**. Она открывается при прямом заходе и после обновления страницы и ни разу не обращается к API.

---

## 3. Supabase: вход и письма

Supabase → **Authentication → URL Configuration**:
- **Site URL:** `https://bytereport.vercel.app` — сюда ведёт ссылка из письма подтверждения;
- **Redirect URLs:** добавьте `https://bytereport.vercel.app/**`. Для разработки можно оставить `http://localhost:5173/**`.

Бесплатный проект Supabase ставится на паузу после недели без активности. Этого не случится, пока работает ежедневный пинг `/health/deep` из шага 5.

---

## 4. OpenAI: отдельный проект с лимитом

1. platform.openai.com → переключатель проектов слева вверху → **Create project** → `bytereport-prod`.
2. **Лимит.** Project → **Limits** → бюджет **$5** в месяц.

   Надёжнее всего ограничивает расходы предоплата: Billing → пополните на $5 и **выключите auto-recharge**. Когда деньги закончатся, OpenAI начнёт отвечать `insufficient_quota`, сайт покажет ошибку анализа, и больше ничего не спишется.
3. **Модели.** В Limits проекта должны быть разрешены:
   - `gpt-4.1` — отчёт и чат;
   - `gpt-4o` — фото чеков;
   - `gpt-4o-transcribe` — голосовые заметки.
4. **API keys → Create new secret key** в проекте `bytereport-prod`. Скопируйте ключ (его показывают один раз) и вставьте **только** в Render → `OPENAI_API_KEY` → Save and deploy.

   Не вставляйте его в Vercel и в git.

Один отчёт стоит $0,02–0,03. На $5 выйдет примерно 150–200 отчётов.

---

## 5. cron-job.org: чтобы API не засыпал

Render Free усыпляет сервис после 15 минут без запросов, а просыпается он до минуты.

1. cron-job.org → зарегистрируйтесь → **Create cronjob**.
2. Задача **«ByteReport ping»**:
   - URL `https://bytereport-api.onrender.com/health`;
   - расписание: **каждые 10 минут**;
   - включите уведомление о сбоях.
3. Задача **«ByteReport DB»**:
   - URL `https://bytereport-api.onrender.com/health/deep`;
   - расписание: **раз в сутки** (например, 06:00 по Ташкенту).

   Она делает один лёгкий запрос в базу, чтобы Supabase не ушёл на паузу. В ответе нет никаких данных, только «ok» и время. Результат кэшируется на минуту.

Учтите лимит Render: **750 бесплатных часов в месяц на весь аккаунт**. Один сервис без сна тратит около 744 часов, то есть почти всё.
- Если на этом аккаунте Render есть другие бесплатные сервисы, пингуйте только днём, например с 07:00 до 23:00 (около 500 часов).
- Ночью первый запрос тогда будет ждать пробуждения, и сайт покажет экран «Сервер запускается».

---

## 6. Проверка: 5 пунктов

1. **API жив и видит базу:**
   - `…onrender.com/health` → `"status":"ok"` за доли секунды;
   - `…onrender.com/health/deep` → `"database":"ok"`.
2. **Демо не зависит от API:**
   - откройте `https://bytereport.vercel.app/demo` и нажмите F5 — отчёт на месте;
   - DevTools (F12) → Network → фильтр `onrender`: ноль запросов;
   - на главной странице там же ровно один запрос `/health` (прогрев).
3. **Полный путь:**
   - регистрация → письмо → ссылка ведёт на ваш сайт;
   - загрузите выписку (CSV, XLSX или PDF) — отчёт готов примерно за минуту;
   - PDF скачивается, кириллица в нём читается (не квадратики).
4. **Пробуждение:**
   - выключите задачу «ByteReport ping» в cron-job.org на 20 минут;
   - откройте сайт и загрузите файл;
   - появится «Сервер запускается, это займёт до минуты», и запрос пройдёт сам, без повторного нажатия.
   - Включите задачу обратно.
5. **Деньги и ключи:**
   - OpenAI → Usage проекта `bytereport-prod`: за отчёт из пункта 3 около $0,03;
   - в GitHub-репозитории поиск по `sk-` и `eyJ` ничего не находит;
   - локально то же проверяет `python tools/secret_scan.py`.
