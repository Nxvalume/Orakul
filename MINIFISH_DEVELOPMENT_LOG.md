# MiniFish — проверенный технический журнал

## 2026-10-16 — единая активная сессия Chromium для владельца и MCP

**Задача:** подключать ChatGPT MiniFish и мобильную панель владельца к **одному** браузерному контексту MiniFish. Это не доступ к внутреннему Chromium ChatGPT и не создание общей памяти двух независимых браузерных платформ.

**Исправление:** в `server._open_telegram` действующая Telegram-сессия MiniFish имеет приоритет над сохранённым профилем. Повторный `browser_open('https://web.telegram.org/k/')` возвращает прежний `session_id` с `reused=true`, не вызывает `close`, не загружает старый профиль и не сбрасывает введённые данные. Обращение MCP во время `private_mode` отвергается через `engine.get`. Только при отсутствии активного Telegram-контекста профиль извлекается из постоянного хранилища. Закрываются по-прежнему только безопасные временные /healthz-пробы; пользовательские страницы не закрываются автоматически.

**GitHub:** коммиты `c4c617c` (исправление), `7eb67d9` (регрессии), `3be4bf4` (изоляция тестов от DNS Telegram), ветка `minifish-v02`, `main` не менялась. На `3be4bf4` все три GitHub Actions `MiniFish checks`, `MiniFish CI`, `MiniFish stability CI` завершились успешно. Тесты `tests/test_shared_browser_attach.py` проверяют повторное присоединение, защиту личного режима и восстановление профиля только после исчезновения активного контекста.

### Публикация и реальная проверка (2026-10-16)

- Render deploy `dep-db91u0brjlhs73du9tig` опубликован с SHA `f708106e4a3f86dd23f9fae6279fe80320a348fc`, статус **live**, завершён в `2026-10-16T13:00:11Z`.
- Все три CI на кодовом SHA `3be4bf4` успешны. Docker-сборка актуального деплоя: **109 passed, 1 warning**.
- Публичный `/healthz` проверен независимо после запуска: `status=ok`, `durable_storage=true`, `storage_probe=ok`, `storage_backend=edge_https`, `background_worker_running=true`; на момент проверки `active_browsers=0`.
- Реальный MCP smoke-тест через подключённый `browser_open`: два последовательных открытия `https://example.com` вернули один и тот же `session_id` (`ae23d1bf-924d-4a41-b00f-3f72aa2f63d3`); второй ответ содержал `reused=true`. `browser_snapshot` прочитал фактическую страницу. `browser_close` закрыл тестовый браузер, `closed=true`. Это проверка повторного использования живого браузера **для обычного сайта**, не подтверждение Telegram-login.
- Промежуточный HTTP 503 был во время переключения контейнера на Render; после успешного старта внешний health-check вернул OK. Не интерпретировать промежуточный 503 как итоговую ошибку.
- Не проверены: фактический общий `session_id` одновременно на странице владельца и после авторизации Telegram, сохранение Telegram-профиля после ручного логина и перезапуска, интерактивный UI внутри нативного ChatGPT Android, обновление кэшированного набора из 10 MCP-инструментов. Никогда не утверждать, что эти пункты завершены.


**На момент записи:** Render всё ещё показывал деплой `dep-db8krq6i0phs73bssf9g` с кодом `5dbb2afb`; GitHub Actions успех не означает публикацию. Render в настройках сообщает `autoDeploy=yes`, но история событий не показывала новые деплои после коммитов 16 октября; необходимо отдельно подтвердить запуск сборки и фактический `live` новый SHA. Не утверждать, что мобильное встроенное MCP Apps окно заработало: текущий Android-host продолжает открывать 10 старых инструментов.

**Приёмка дальше:** проверить Render deployment SHA, `/healthz`, действительный возврат одного `session_id` в браузере через MCP и панели (без просмотра Telegram-паролей), затем восстановление только после закрытия/перезапуска. Проверку интерактивного MCP Apps в ChatGPT web вести отдельно.

---

## 2026-10-16 — встроенный браузер и Android-представление

**Код:** репозиторий `Nxvalume/Orakul`, рабочая ветка `minifish-v02`, HEAD на момент аудита: `5dbb2afb3f91ad160ef5d7944f096f0d4ace9cb2`. Ветка `main` не менялась.

**Render:** service `srv-db789o5g1s2s739g756g`, workspace `tea-daa0meon74is739fjk3g`, последний проверенный deploy `dep-db8krq6i0phs73bssf9g` (live), URL `https://nxval-minifish-2026.onrender.com`.

**Plugin:** id `plugins_6ace90389e2c819192f0fb8f6fd58657`. Выпущен release `0.5.0`, id `pluginrel_6ad21c2fe61c81919981bce80567b70f`. Изменены только plugin.json и skills/minifish/SKILL.md, текущая `.mcp.json` и адрес существующего MCP сохранены. В 0.5.0 основной резервный путь для Android — **вызов `browser_screenshot` после `browser_open` и значимых браузерных действий** для вывода реального изображения в чат. Интерактивный MCP Apps ресурс `ui://minifish/browser-v4.html` остаётся для поддерживаемого хоста.

### Подтверждённые проверки

- Текущая подключённая в чате версия MiniFish предоставляет только 10 инструментов: `browser_open`, `browser_goto`, `browser_back`, `browser_snapshot`, `browser_click`, `browser_fill`, `browser_select`, `browser_scroll`, `browser_screenshot`, `browser_close`. Новые команды не появились в подключении после публикации. Не объявлять динамическое обновление инструментов работающим.
- В серверном коде реально зарегистрированы `browser_window`, `browser_tap`, `browser_telegram_status`. `tests/test_mcp_apps_window.py` проверяет ресурсы, URI и метаданные на сервере; это **не** доказывает, что мобильный хост отобразил UI.
- Команды `browser_open('https://web.telegram.org/k/')`, `browser_snapshot`, `browser_click` и `browser_screenshot` были выполнены подключённым плагином. Фактический PNG экрана входа Telegram показан как результат вызова в диалоге, без подмены картинкой.
- Официальная справка OpenAI, «Creating custom MCP apps in ChatGPT»: custom MCP apps доступны в ChatGPT web, не в мобильном нативном приложении (по состоянию на 2026-10-16). Проверить новые версии клиента при изменениях.

### Что не подтверждено

- Нативный интерактивный MCP Apps iframe внутри ChatGPT на Android.
- Обновление уже подключённого в чате набора из 10 старых инструментов до актуального `tools/list`. Вероятен кэш/переподключение клиента; до проверки не считать причиной однозначно.
- Реальная авторизация Telegram, сохранение сессии после перезапуска и передача управления ассистенту для текущего владельца. Не запрашивать коды и пароли в чате.

### Следующие технические шаги

1. Через реальный MCP-клиент выполнить `tools/list` и `resources/read`, сравнить зарегистрированные команды сервера с инструментами, которые предоставил ChatGPT. Проверить ресурс `ui://minifish/browser-v4.html`.
2. В клиенте ChatGPT web переподключить тот же plugin id и проверить `browser_window` и `browser_tap` именно в вызывающем чате.
3. Для Android показывать проверенные PNG после безопасных действий, при приватной авторизации НЕ вызывать снимок и не передавать коды/пароли в инструменты.
4. После входа владельца проверять `logged_in`, `saved`, устойчивость профиля после закрытия и перезапуска, без раскрытия его содержимого.

Никакая внешняя ссылка или статический PNG не считается полноценным интерактивным MCP Apps окном.

## 2026-10-16 — устранение зависания встроенного кадра MCP Apps на Android

**Полевое наблюдение:** пользователь подтвердил, что после переподключения оба приватных плагина MiniFish появились в чате видимые интерактивные кадры; в новом подключении ChatGPT доступно 22 инструмента. Затем вместо изображения страницы показался загрузочный кадр с текстом «Интерактивный кадр браузера MiniFish». Живость браузерной сессии `db375391-69d6-4cdd-9df5-7ff6606dbd3e` подтверждена через `browser_snapshot` (IANA Example Domains); сервер отвечает на `POST /mcp` с HTTP 200.

**Диагноз по коду:** старый `chat_ui.py:inputFrom` извлекал `session_id` только из прямого/структурированного объекта или `arguments`, но не из стандартного MCP text-content результата. Не слушал отложенное событие ChatGPT `openai:set_globals`. В результате iframe мог не узнать ID сессии и бесконечно показывать «Загрузка кадра…». Отсутствие изображения в ответе `browser_screenshot` не приводило к явной ошибке.

**Исправление:** коммит `288feeb40dc50a6b89f713ec34bf45d9b8bf829a` обновил декодирование результата MCP и отложенных глобальных событий, добавил разбор `content_items` и явные ошибки вместо немой загрузки. Коммит `56df9233dcc613c1ddd8f363e23eff03e2ba10e5` добавил `tests/test_chat_ui_mcp_envelopes.py` с тестами типичных MCP-обёрток, включая Node.js runtime, когда доступен.

**Статус на момент записи:** CI для исходного исправления (`288feeb`) прошёл во всех трёх workflow. CI для `56df923` выполняется. Live Render всё ещё на `bdcbd801`; **исправление ещё не считается выпущенным или проверенным на Android**. После CI: контролировать автоматический деплой Render; проверить реальный ресурс UI и получить подтверждение владельца о показе изображения и работе тапов. Не закрывать пользовательские сессии. Telegram `browser_telegram_status`: `phase=not_open`, `logged_in=false`, `saved=false`, `storage=ok`, без передачи секретов.


## 2026-10-16 20:51 МСК — Android ChatGPT теряет session_id, безопасное восстановление

**Полевое подтверждение:** снимок экрана Android от владельца показал открывшееся встроенное окно MiniFish, но статус «ChatGPT не передал ID браузера. Открой MiniFish повторно» и пустой кадр. Это объясняет загрузку: виджет не получил `session_id` из host `toolInput`/`toolOutput`; сам браузерный backend ранее обслуживал snapshot/screenshot. Не путать с подтверждением работоспособности touch UI.

**Код:** в `server.py` добавлена `browser_attach()` с `CHAT_ACTION_META`: только единственная существующая непублично-приватная/non-private сессия, `engine.get` для истечения срока, возврат `attached/session_id/site`; закрытые, приватные Telegram-сессии и несколько активных вкладок не раскрываются, Chromium не создаётся заново. В `chat_ui.py` виджет автоматически выполняет `browser_attach`, если хост не передал `session_id`; кнопка «Обновить экран» повторяет попытку без вызова `browser_open`. Обработка таймаутов и ошибки кадра остаётся явной. Коммиты: `1dec93bd`, `35963c08`, `e550bc9d`; обновлён старый тест сообщения `689223004cfce8905b3b21d10a0b74d86d187b7a`.

**Проверено:** три GitHub Actions workflows (MiniFish CI, MiniFish checks, MiniFish stability CI) для `68922300` завершились success, 121 тестов в предыдущем неуспешном run, где падал только устаревший assertion; после правки все CI зелёные. Render deployment `dep-db967cnt5n8s73cfkmr0` статуса **live**, тот же SHA `68922300`. Реальный подключённый MiniFish открыл `https://example.com` после деплоя, session `8cfc215b-e5c8-4218-824b-be5e27d5906d`, `browser_snapshot` подтвердил HTML-текст. `main` не менялась. Новые платные ресурсы не создавались.

**Не подтверждено:** актуальный Android виджет вызвал новый `browser_attach` и нарисовал кадр, касания/ввод внутри обновлённого виджета; новые команды могут требовать обновить набор tools у подключённого MCP, а URI `ui://minifish/browser-v4.html` кэшироваться хостом. Нельзя объявлять проблему загрузки полностью решённой до пользовательского подтверждения. Telegram login/persistence across Render restart не проверены; защищённые данные не раскрывались.

**Следующее:** получить от владельца один факт — отображается ли страница в новом окне или появилась конкретная ошибка. При старом коде iframe проверить повторное считывание UI resource (возможно версия URI v5); при `browser_attach` tool missing переподключить именно приватный plugin `plugins_6ace90389e2c819192f0fb8f6fd58657`. После Android приёмки проверить касания/поле без паролей, затем отдельно Telegram в приватном режиме.


## 2026-10-16 21:10 МСК — защищённый режим Android, устранение MCP INVALID_ARGUMENT

**Полевой симптом:** скриншот пользователя из встроенного окна MiniFish показывает `INVALID_ARGUMENT: RuntimeException: Error calling MCP tool... Error executing tool browser_...` одновременно с «Защищённый режим. ChatGPT не имеет доступа к полям входа» и непрорисованным изображением. Проверка реальной сессии `8cfc215b-...` через `browser_snapshot` вернула `PermissionError: Личный режим владельца: доступ MCP временно заблокирован`. Следовательно MCP отказ был преднамеренным серверным ограничением, а дефект — публичные кнопки и автообновление продолжали обращаться к приватному окну, плюс insecure image blob/переход интерфейса.

**Исправлено в `chat_ui.py`:** `publicView(false)` убирает обычный экран, прокрутку, поля и кнопки после успешного owner unlock; модельные `render/act` и polling остановлены при `secureToken` или `privateLocked`; полученный `PermissionError` переводит в вид владельца без разглашения приватного кадра; при истечении owner-capability требуется повторный пароль MiniFish; приватные JPEG преобразуются `FileReader.readAsDataURL` вместо `blob:` в рамках CSP iframe; добавлена приватная прокрутка через собственный HTTPS owner-control; `finish` не возвращает модельные инструменты, если сохранение Telegram профиля отклонено (`private_mode=true`). Пароли и коды не проходят через MCP.

**Коммиты только в `minifish-v02`:** `8b3e12f1ada3f0532cceda90de93ce691072e2e6` (UI), `0807ab8bd416eac9c39fe38a6a59985f0dbef032` (четыре regression tests, включая Node.js JS syntax). Все 3 workflows GitHub Actions завершились `success` для `0807ab8b`.

**Фактический deploy Render:** `dep-db96fvcs728c73fbkpn0`, `live`, commit `0807ab8bd416eac9c39fe38a6a59985f0dbef032`. После deploy подключённый MCP `browser_open('https://example.com')` выдал session `ceb66c5c-0efa-43da-935c-00cce040f38e`, `browser_snapshot` выдал текст страницы, `browser_screenshot` — реальный PNG, `browser_scroll(pixels=250)` успешно исполнился; tool browser_open инициировал UI в чате, поэтому дополнительных `browser_window` не вызывали ради предотвращения дублированных окон.

**Строго не подтверждено:** отображение нового приватного кадра и корректная работа тапов/текстового ввода непосредственно на Android, реальный Telegram login и durable recovery после рестарта Render. Никакой owner password/Telegram OTP не запрашивался в чат. Без отдельной обратной связи нельзя назвать задачу завершённой.


## 2026-10-16 21:30 МСК — MiniFish: общий браузер на разных HTTPS-сайтах и Telegram smoke

**Запрос владельца:** MiniFish должен быть универсальным совместным браузером ChatGPT+Android для разных сайтов, Telegram — лишь один тест. Не создавать новую Chromium-сессию для каждого сайта, не требовать ручного allowlist и не открывать приватные данные для model MCP.

**Реализовано:**
- `chat_ui.py`: адресные строки `navForm` (общее управление через `browser_goto(session_id,url)`) и `secureNavForm` (прямой owner-only HTTPS `secureAction('navigate',{url})`); валидация URL, `https:` без встроенного логина/пароля, запрет других схем/портов. Обе формы работают в одной Chromium-сессии, общая скрывается при owner-private mode. Canvas отображение не менялось относительно предыдущей версии.
- `chat_secure.py`: существующий owner-only control расширен `navigate` с передачей `url` в `engine.owner_control`, который вызывает `validate_url` (проверка публичного DNS/IP/HTTPS), разрешение и session HMAC проверяются ранее. Это не MCP инструмент. Коммит `4b9b0651`.
- Render: merge update только `MINIFISH_ALLOW_ANY_PUBLIC_HTTPS=1`; запрещённые private/link-local/loopback адреса, DNS, схемы кроме HTTPS, нестандартные порты остаются закрыты сервером; прочие environment vars сохранены.
- URL UI коммит `37505850`, regression/SSRF tests `f9de1834`, фиксы проверки протокола `384b32da`, `3f028fc1ea2b8a609ddc339653f87510a07da1a4`.

**CI:** все три GitHub Actions workflows по SHA `3f028fc1` завершились success, включая Node JS/Canvas/URL tests и отрицательные тесты для внутренней сети. **Render:** `dep-db96os6i0phs73fojbk0` в статусе live, commit `3f028fc1`.

**Реальная проверка MCP после деплоя:** `browser_open('https://example.com')` вернул session_id `b233e13e-4b6a-404f-a4a8-ee6ee5d4fae3`, title `Example Domain`. `browser_goto(same_session,'https://example.org/')` успешен. `browser_goto(same_session,'https://web.telegram.org/k/')` успешен, title `Telegram Web`. `browser_telegram_status` показал `phase=login_required,logged_in=false,saved=false,storage=ok`. `browser_snapshot` показал QR login с переключателем `LOG IN BY PHONE NUMBER`; `browser_click` по его selector выполнился, следующий snapshot подтвердил форму `Phone Number`, `NEXT`, переключатели QR/Passkey. Паролей, телефонов и кодов не вводили; Telegram аккаунт НЕ авторизован. MCP `browser_open` показал embedded UI в диалоге. Повторный `browser_window` не запускали во избежание дубликатов.

**Остаётся неподтверждённым:** фактическое Android отображение canvas и адресной строки после последнего релиза, пользовательские тап и ввод, owner-only protected HTTPS control (потребует владельца с локальным паролем), сохранение авторизованной Telegram сессии после restart. Не объявлять всё готовым только по CI/backend smoke. `main` не изменялась; доп. платные ресурсы не создавались.


## 2026-10-16 ~21:57 МСК — v0.5.1: настоящие вкладки, общая навигация, приватная изоляция

**Задача:** пользователь хочет MiniFish с обычными возможностями браузера (множество вкладок и совместная работа на разных сайтах), не только для Telegram. Разработка идёт в `minifish-v02` без изменения `main` и без новых платных ресурсов.

**Код:** `engine.py`: до 6 настоящих Playwright Page в ОДНОМ BrowserContext: `tab_list`, `tab_action(new/switch/close/forward/reload)`, сохранение выбранной вкладки после кликов, ручное закрытие последней вкладки создаёт blank tab, приватные действия доступны только владельцу. При закрытии вкладки Telegram во время owner private mode требуется предварительно завершить вход. Фоновая вкладка Telegram обнаруживается `telegram_session_id`/logged_in/authenticated_state без переключения активной вкладки. Коммиты `aa756619`, `bb08b749`, `947d9d4c`, `b27065a4`; устаревший тест приватного снятия блокировки исправлен с сохранением security invariants в `29106fad` и `d5a7033b`.

**Сервер:** `browser_tabs` и `browser_tab_action` имеют `CHAT_ACTION_META`, не создают дублирующие UI-окна; owner-only HTTPS endpoints `/chat/secure/tabs`, `/chat/secure/tab_action` защищены тем же HMAC owner-capability, что и отдельный приватный ввод. `chat_ui.py`: горизонтальные вкладки `+`, переключение по названию, закрытие `×`, вперёд `→`, назад `←`, обновление; свой tab strip для private. Никакие приватные заголовки/URL не отправляются модели во время авторизации.

**Проверки:** три GitHub Actions workflow `MiniFish CI`, `MiniFish checks`, `MiniFish stability CI` прошли `success` на `b27065a4fa3d0e70103fd86cf4e74745dd78e9f7`; 140 passed. Реальные тесты Chromium открыли/переключили/закрыли вкладки в одном BrowserContext, проверили сохранение активной вкладки, 6-tab лимит, owner privacy, фоновый Telegram test state. Реального входа в аккаунт Telegram не было.

**Публикация:** Render deployment `dep-db97653rjlhs73ar0900` со SHA `b27065a4` проверен `live`. Существующий приватный plugin `plugins_6ace90389e2c819192f0fb8f6fd58657` обновлён через Plugin Creator с 0.5.0 до **0.5.1**, release `pluginrel_6ad273948a2c819192c6f9cc1717e615`, url `https://chatgpt.com/plugins/plugins_6ace90389e2c819192f0fb8f6fd58657`; `.mcp.json` прежнего плагина сохранён. После деплоя реальный `browser_open('https://example.com')` успешно открыл сессию `2e661b05-17ec-475d-abbe-dcb7d794a956`, `browser_snapshot` вернул Example Domain, ChatGPT сообщил о показе embedded UI.

**Внешний блокер для завершающей приёмки Android:** в текущем ChatGPT-подключении доступно всё ещё 22 старых MCP-инструмента, **нет `browser_tabs` и `browser_tab_action`**, несмотря на их регистрацию на сервере и release. Чтобы убедиться, что кнопки вкладок работают в Android MCP Apps widget, нужно обновить инструментальный кэш переподключением **существующего MiniFish 0.5.1**, не создавать другой плагин. Хост может использовать старую версию набора tools; это не дефект Chromium. Не объявлять полностью готовым Android UI/клики, пока пользователь не подтвердит. Telegram auth/persistence после Render restart всё ещё не проверены.
