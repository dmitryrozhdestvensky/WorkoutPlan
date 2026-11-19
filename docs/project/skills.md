# Навыки Codex для «ПланТренировок»

Сверено 19 ноября 2026 года. В справочнике 113 навыков, которые мы установили вручную или создали для проекта. Для вызова напишите имя со знаком `$`, например «Запусти `$fitness-e2e`».

## Что попробовать в ближайшей работе

- Лендинг и регистрация. `product-marketing` фиксирует аудиторию и ценность, `copywriting` помогает с текстом, `cro` и `signup` разбирают путь после «Начать тренироваться», а `fitness-e2e` проверяет результат в браузере.
- Новый клиент с пустым планом. `onboarding` помогает определить, что показать до первого назначения. `analytics` задаёт события от регистрации до первого сохранённого подхода.
- Сбой. `diagnosing-bugs` локализует причину, `tdd` помогает закрепить исправление, `code-review` проверяет изменения.
- Новая функция. `grill-with-docs` проясняет правила, `to-spec` описывает их, `to-tickets` разбивает работу на проверяемые задачи.

Источники: [Marketing Skills](https://github.com/coreyhaines31/marketingskills/tree/73573e94a06a39965978b3fa1f9c1eace8cebc7c), [Matt Pocock](https://github.com/mattpocock/skills), [Anthropic](https://github.com/anthropics/skills), [Taste Skill](https://github.com/Leonxlnx/taste-skill).

## Свои и дизайн

| Задача | Навыки | Пример для проекта |
|---|---|---|
| Браузер и лендинг | `fitness-e2e`, `design-taste-frontend` | Прогон регистрации по W4J78, профиля, замеров и подхода на 18743. Для подхода нужна назначенная тренировка. Taste Skill помогает со страницей и её адаптивностью, его скрипты используют Node.js 22+. |

## Marketing Skills · 53

| Задача | Навыки | Пример для проекта |
|---|---|---|
| Стратегия | `product-marketing`, `customer-research`, `competitors`, `competitor-profiling`, `reverse-engineer-marketing`, `marketing-plan`, `marketing-ideas`, `marketing-council`, `marketing-psychology`, `offers` | Определить ценность для тренера и клиента, опираясь на интервью и разборы FitStars, Fitmus и TrainingCalc. |
| Лендинг и регистрация | `copywriting`, `copy-editing`, `cro`, `signup`, `onboarding`, `popups` | Проверить первый экран, переход по кнопке «Начать тренироваться» и состояние пустого плана после регистрации. |
| Измерение | `analytics`, `conversion-tracking`, `attribution`, `ab-testing` | Определить события от клика до сохранения первого подхода и сравнить варианты при достаточном трафике. |
| Поиск и каталоги | `seo-audit`, `ai-seo`, `site-architecture`, `schema`, `programmatic-seo`, `link-building`, `directory-submissions`, `aso` | Проверить публичные страницы, подготовить поисковую структуру и карточки приложений после публикации. |
| Контент и каналы | `content-strategy`, `social`, `image`, `video`, `ad-creative`, `ads`, `emails`, `sms` | Сделать демонстрацию продукта и подготовить материалы для соцсетей и писем. |
| Запуск и рост | `launch`, `referrals`, `marketing-loops`, `free-tools`, `lead-magnets`, `co-marketing`, `influencer-marketing`, `community-marketing`, `events`, `public-relations` | Спланировать пилот с тренерами, проверить процесс приглашений и подготовить материалы запуска. |
| Продажи и удержание | `prospecting`, `cold-email`, `sales-enablement`, `revops`, `pricing`, `paywalls`, `churn-prevention` | При развитии платных функций проработать предложения клубам, тарифы и причины ухода. |

## Matt Pocock · 39

| Задача | Навыки | Пример для проекта |
|---|---|---|
| Требования | `ask-matt`, `grill-me`, `grilling`, `grill-with-docs`, `domain-modeling`, `to-questionnaire`, `to-spec`, `to-tickets`, `triage`, `setup-matt-pocock-skills` | Согласовать продуктовые правила, критерии приёмки и зависимости задач. |
| Реализация и проверка | `diagnosing-bugs`, `tdd`, `code-review`, `implement`, `implement-spec`, `pr`, `prototype`, `software-factory`, `loop-me` | Воспроизвести сбой, закрепить исправление тестом, проверить изменения. |
| Архитектура и инструменты | `codebase-design`, `improve-codebase-architecture`, `wayfinder`, `setup-ts-deep-modules`, `git-guardrails-claude-code`, `migrate-to-shoehorn`, `setup-pre-commit` | Проверить границы модулей и применять инструменты там, где подходит стек. |
| Передача работы и обучение | `chief-of-staff`, `claude-handoff`, `handoff`, `research`, `retro`, `scaffold-exercises`, `teach`, `wait-what`, `wizard` | Подготовить передачу задачи, исследование или разбор прогона. |
| Тексты | `writing-beats`, `writing-for-agents`, `writing-fragments`, `writing-shape` | Оформить документацию и инструкции для повторяемых задач. |

## Anthropic · 19

| Задача | Навыки | Пример для проекта |
|---|---|---|
| Браузер и интерфейс | `webapp-testing`, `frontend-design`, `web-artifacts-builder` | Проверить форму в браузере или сделать интерактивный прототип экрана. |
| Документы и данные | `docx`, `pdf`, `pptx`, `xlsx`, `doc-coauthoring`, `internal-comms` | Подготовить печатный план тренировок, таблицу прогресса или спецификацию. |
| Визуальные материалы | `algorithmic-art`, `canvas-design`, `theme-factory`, `brand-guidelines`, `slack-gif-creator` | Сделать карточки тренировок, графику и материалы для команды. `brand-guidelines` использует стиль Anthropic. |
| Интеграции и методика | `academy-guide`, `claude-api`, `mcp-builder`, `discernment-nudge`, `skill-creator` | Изучить Claude, спроектировать MCP-интеграцию или превратить повторяемую процедуру в навык. |

## Обновление справочника

При установке или создании навыка добавляем его имя, источник и пример применения. Начинаем с одного навыка под задачу и подключаем остальные по мере необходимости.
