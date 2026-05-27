# Задача для Codex: переработать верстку и стили сервиса аналитики планировок

Нужно переработать верстку и визуальный стиль сервиса аналитики планировок по новому макету главной страницы.

Макет главной страницы приложен как визуальный референс. Его нужно использовать как источник истины по общему стилю, сетке, карточкам, отступам, типографике, формам элементов и визуальной логике.

Важно: нужно изменить не только главную страницу, но и привести к этому стилю все остальные страницы, блоки и UI-элементы сервиса:

- аналитика рынка;
- аналитика застройщика;
- анализ вариативности планировок;
- страница всех планировок;
- карточки планировок;
- таблицы;
- фильтры;
- KPI-карточки;
- кнопки;
- чипы;
- бейджи;
- графики;
- списки;
- пустые состояния;
- loading/error состояния.

Цель — сделать интерфейс более современным, легким и цельным. Визуально он должен быть похож на минималистичный B2B SaaS / BI-дашборд: светлый фон, крупные скругленные карточки, мягкие серые подложки, черно-белые акценты, аккуратные синие графики, компактные фильтры, много воздуха.

Нельзя ломать текущую бизнес-логику, расчеты, роутинг и данные. Нужно менять визуал, структуру компонентов и стили. Если для каких-то блоков данных пока нет — сделать аккуратные fallback / empty состояния.

---

## 1. Общий визуальный стиль

Новый стиль:

- фон страницы светло-серый;
- основные блоки на белых карточках;
- карточки крупные, с большим `border-radius`;
- минимум границ;
- без тяжелых теней;
- много воздуха;
- аккуратная сетка;
- черный цвет используется как основной акцент для бейджей и ключевых меток;
- синий используется для графиков, активных элементов и интерактивных состояний;
- красный используется только для негативной динамики и предупреждений;
- интерфейс должен выглядеть легче и современнее текущей версии.

Пример ощущения:

- Notion-like dashboard;
- современная BI-панель;
- чистый SaaS-интерфейс;
- без визуального шума.

---

## 2. Цветовая система

Добавить или обновить дизайн-токены.

```css
:root {
  --page-bg: #EDEDED;
  --surface: #FFFFFF;
  --surface-muted: #F3F4F6;
  --surface-soft: #F7F7F8;

  --text-primary: #101828;
  --text-secondary: #667085;
  --text-muted: #98A2B3;

  --border-soft: #E5E7EB;
  --border-medium: #D0D5DD;

  --accent-blue: #3F5CFF;
  --accent-blue-hover: #3048D9;
  --accent-blue-soft: #EEF2FF;

  --accent-black: #000000;
  --accent-black-hover: #1F1F1F;

  --danger: #FF3B30;
  --danger-soft: #FFECEC;

  --warning: #F59E0B;
  --warning-soft: #FFF7ED;

  --success: #16A34A;
  --success-soft: #ECFDF3;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;

  --shadow-none: none;
  --shadow-soft: 0 1px 2px rgba(16, 24, 40, 0.04);
}
```

Основные правила:

- `body background: #EDEDED`;
- карточки: `#FFFFFF`;
- вторичные подложки: `#F3F4F6`;
- основной текст: `#101828`;
- вторичный текст: `#667085`;
- черные бейджи: `#000000` + белый текст;
- синие бары/графики: `#3F5CFF`;
- опасные значения: `#FF3B30`.

---

## 3. Типографика

Использовать системный sans-serif или Inter, если он уже подключен.

```css
font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

### Заголовок страницы

Например: `Общий анализ рынка`.

```css
font-size: 22px;
line-height: 28px;
font-weight: 500 или 600;
letter-spacing: -0.02em;
color: #101828;
```

Важно: в новом макете заголовок страницы не огромный. Он спокойный и встроен в верхнюю панель.

### Заголовок карточки

```css
font-size: 16px;
line-height: 22px;
font-weight: 500 или 600;
color: #101828;
```

### KPI-значение

Например: `324`, `9.29 млн ₽`, `1.4 кв./план.`

```css
font-size: 18px;
line-height: 26px;
font-weight: 600;
color: #101828;
```

### Подпись KPI

```css
font-size: 12px;
line-height: 16px;
font-weight: 400;
color: #98A2B3;
```

### Основной текст

```css
font-size: 13px;
line-height: 18px;
font-weight: 400;
color: #101828;
```

### Вторичный текст

```css
font-size: 12px;
line-height: 16px;
font-weight: 400;
color: #667085;
```

---

## 4. Глобальная сетка страницы

Главная страница должна быть собрана по сетке, как на макете:

- общий фон серый;
- внешний padding страницы примерно `12px`;
- все блоки имеют одинаковый gap `6–8px`;
- карточки плотно уложены в сетку, но внутри них достаточно воздуха;
- карточки с большим скруглением.

```css
.page {
  min-height: 100vh;
  background: var(--page-bg);
  padding: 12px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 6px или 8px;
}
```

На desktop:

- верхняя панель занимает 12 колонок;
- KPI-карточки — по 4 колонки, 3 карточки в ряд;
- карточки застройщиков — по 4 колонки, 3 карточки в ряд;
- `Главное за период` — 6 колонок;
- `Динамика предложения` — 6 колонок;
- `Карта проектов` — 8 колонок;
- `Структура предложения` — 4 колонки.

На tablet:

- 2 колонки;
- крупные блоки по ширине.

На mobile:

- 1 колонка;
- все карточки идут вертикально;
- таблицы имеют горизонтальный скролл.

---

## 5. Header / верхняя панель

Собрать верхнюю панель как в макете.

Структура:

- слева карточка с логотипом;
- рядом карточка с названием страницы;
- справа карточка с фильтрами.

Высота верхней панели примерно `66–72px`.

```css
.header {
  display: grid;
  grid-template-columns: 190px 1fr 580px;
  gap: 6px или 8px;
  margin-bottom: 6px или 8px;
}
```

### Логотип

Карточка:

```css
.logo-card {
  background: #FFFFFF;
  border-radius: 12px;
  padding: 18px 24px;
  display: flex;
  align-items: center;
}
```

Логотип/текст:

- черный;
- жирный;
- компактный;
- не добавлять лишнюю декоративность.

### Карточка заголовка

```css
.title-card {
  background: #FFFFFF;
  border-radius: 12px;
  padding: 0 24px;
  display: flex;
  align-items: center;
}
```

Текст:

```css
font-size: 20px или 22px;
font-weight: 500;
color: #101828;
```

### Фильтры в header

Фильтры должны быть компактными, встроенными в правую белую карточку.

Поля:

- Застройщик;
- Проект;
- Период анализа.

Каждый фильтр:

```css
.filter-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
```

Label:

```css
font-size: 11px;
line-height: 14px;
font-weight: 500;
color: #101828;
```

Select:

```css
height: 36px;
border: none;
border-radius: 8px;
background: #F3F4F6;
padding: 0 12px;
font-size: 12px;
color: #101828;
```

Активное/hover-состояние:

```css
background: #EEF2FF;
outline: 1px solid rgba(63, 92, 255, 0.2);
```

---

## 6. Карточки

Все основные блоки должны использовать единый стиль карточки:

```css
.card {
  background: #FFFFFF;
  border-radius: 12px;
  border: none;
  box-shadow: none;
  padding: 20px;
}
```

Для больших блоков:

```css
.card-large {
  padding: 24px;
  border-radius: 14px;
}
```

Для компактных KPI:

```css
.kpi-card {
  min-height: 100px;
  padding: 20px;
  border-radius: 12px;
}
```

Не использовать тонкие серые рамки на каждой карточке, если они визуально утяжеляют интерфейс. Основное разделение блоков должно идти через серый фон страницы и белые карточки.

---

## 7. KPI-карточки

KPI-карточки должны выглядеть как на макете.

Структура:

- сверху бейдж или дополнительное значение;
- ниже маленькая подпись;
- ниже основное значение.

Пример:

```text
[-15 за 30 дней]
Квартир в продаже
324
```

Или:

```text
[163 500 ₽/м²]
Медианная цена
9.29 млн ₽
```

CSS:

```css
.kpi-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 108px;
  background: #FFFFFF;
  border-radius: 12px;
  padding: 20px;
}

.kpi-meta {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 4px;
  background: #000000;
  color: #FFFFFF;
  font-size: 13px;
  font-weight: 500;
}

.kpi-meta-danger {
  background: #FFECEC;
  color: #FF3B30;
}

.kpi-label {
  margin-top: 12px;
  font-size: 12px;
  color: #98A2B3;
}

.kpi-value {
  margin-top: 8px;
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
  color: #101828;
}
```

Правила для бейджей KPI:

- положительные/нейтральные значения — черный бейдж с белым текстом;
- негативная динамика — светло-красный бейдж с красным текстом;
- warning — светло-оранжевый бейдж;
- success — светло-зеленый бейдж.

---

## 8. Карточки застройщиков

Карточки застройщиков должны быть компактными, как на макете.

Структура:

```text
Железно
4 проекта - 294 квартиры - 172 планировки - 1,71 кв/план
```

CSS:

```css
.developer-card {
  background: #FFFFFF;
  border-radius: 12px;
  padding: 16px 20px;
  min-height: 58px;
  cursor: pointer;
}

.developer-card:hover {
  background: #F9FAFB;
}

.developer-name {
  font-size: 18px;
  line-height: 24px;
  font-weight: 500;
  color: #101828;
}

.developer-meta {
  margin-top: 4px;
  font-size: 12px;
  line-height: 16px;
  color: #101828;
  opacity: 0.8;
}
```

Сделать кликабельными, если есть роут аналитики застройщика.

---

## 9. Блок “Главное за период”

Сверстать как большую белую карточку.

Структура:

- заголовок слева;
- справа круглая кнопка collapse/expand;
- внутри список инсайтов;
- каждый инсайт в отдельной внутренней карточке с тонкой серой рамкой.

```css
.insights-card {
  background: #FFFFFF;
  border-radius: 12px;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}

.collapse-button {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  border: none;
  background: #F3F4F6;
  color: #667085;
}
```

Инсайт:

```css
.insight-item {
  padding: 14px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  background: #FFFFFF;
  font-size: 13px;
  line-height: 18px;
  color: #101828;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
```

Warning-инсайт можно выделять, но аккуратно:

```css
.insight-item-warning {
  border-color: #FFD6D6;
  background: #FFF7F7;
}
```

---

## 10. Блок “Динамика предложения”

Сверстать как белую карточку с таблицей-списком.

Строки:

```text
Было в прошлом срезе      679
Сейчас в продаже          268
Ушло из экспозиции        411
Новых                     0
С изменением цены         0
```

CSS:

```css
.metrics-list {
  display: flex;
  flex-direction: column;
}

.metric-row {
  display: grid;
  grid-template-columns: 1fr 160px;
  min-height: 44px;
  border-bottom: 1px solid #E5E7EB;
}

.metric-label {
  display: flex;
  align-items: center;
  padding: 0 16px;
  font-size: 13px;
  color: #101828;
}

.metric-value {
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-left: 1px solid #E5E7EB;
  font-size: 13px;
  color: #101828;
}
```

Warning-плашка снизу:

```css
.warning-panel {
  margin-top: 12px;
  min-height: 36px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  border-radius: 10px;
  background: #FFECEC;
  color: #FF3B30;
  font-size: 13px;
  font-weight: 500;
}
```

---

## 11. Блок “Карта проектов”

Карточка большая, слева внизу.

Пока если график не реализован, оставить корректный empty-state, но контейнер должен быть готов под график.

```css
.project-map-card {
  min-height: 350px;
  background: #FFFFFF;
  border-radius: 12px;
  padding: 20px;
}
```

Если график есть:

- фон графика белый;
- сетка очень светлая;
- точки синие или черные;
- tooltip в стиле белой карточки;
- не использовать яркие многоцветные схемы.

Для scatter plot:

- X: квартир на планировку;
- Y: квартир в продаже;
- размер точки: количество типовых планировок;
- цвет: застройщик;
- tooltip: проект, застройщик, квартир, планировок, кв./план.

---

## 12. Блок “Структура предложения”

Карточка справа.

Внутри:

- заголовок;
- collapse-кнопка;
- segmented control: Цена / Площадь / Комнатность;
- список баров.

Segmented control:

```css
.segmented-control {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  height: 30px;
  background: #F3F4F6;
  border-radius: 8px;
  padding: 2px;
}

.segmented-item {
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 12px;
  color: #101828;
}

.segmented-item-active {
  background: #FFFFFF;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}
```

Bar item:

```css
.structure-row {
  margin-top: 14px;
}

.structure-row-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #101828;
}

.bar-track {
  margin-top: 6px;
  height: 8px;
  border-radius: 999px;
  background: #D9D9D9;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
  background: #3F5CFF;
}
```

---

## 13. Остальные страницы

Применить этот же стиль ко всем страницам.

### Аналитика застройщика

Привести к новой системе:

- серый фон;
- белые карточки;
- скругление 12px;
- новая типографика;
- KPI-карточки как на главной;
- фильтры в верхней панели;
- графики и таблицы в белых карточках;
- убрать тяжелые рамки и лишние разделители.

### Анализ вариативности планировок

Обновить:

- header;
- карточки домов;
- карточки планировок;
- таблицы квартир;
- чипы;
- кнопки;
- группировки по комнатности.

Карточки планировок должны стать визуально ближе к новому стилю:

```css
.layout-card {
  background: #FFFFFF;
  border-radius: 12px;
  border: none;
  overflow: hidden;
}

.layout-image {
  border-radius: 8px;
  background: #F7F7F8;
}
```

### Все планировки

Обновить:

- фильтры;
- сетку карточек;
- чипы;
- пагинацию;
- empty/loading.

### Таблицы

Все таблицы должны стать легче:

- без тяжелых рамок вокруг;
- разделители только между строками;
- header светло-серый;
- числа выровнены аккуратно;
- hover строки светлый.

```css
.table {
  width: 100%;
  border-collapse: collapse;
}

.table th {
  background: #F7F7F8;
  color: #667085;
  font-size: 12px;
  font-weight: 500;
  padding: 10px 12px;
}

.table td {
  font-size: 13px;
  color: #101828;
  padding: 12px;
  border-bottom: 1px solid #E5E7EB;
}
```

---

## 14. Кнопки

Обновить все кнопки под новый стиль.

### Primary

```css
.button-primary {
  height: 36px;
  padding: 0 14px;
  border: none;
  border-radius: 8px;
  background: #000000;
  color: #FFFFFF;
  font-size: 13px;
  font-weight: 500;
}
```

### Secondary

```css
.button-secondary {
  height: 36px;
  padding: 0 14px;
  border: none;
  border-radius: 8px;
  background: #F3F4F6;
  color: #101828;
  font-size: 13px;
  font-weight: 500;
}
```

### Accent

```css
.button-accent {
  background: #3F5CFF;
  color: #FFFFFF;
}
```

Hover:

```css
.button-primary:hover {
  background: #1F1F1F;
}

.button-secondary:hover {
  background: #E5E7EB;
}

.button-accent:hover {
  background: #3048D9;
}
```

---

## 15. Бейджи и чипы

Обновить все бейджи.

```css
.badge {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
}
```

Варианты:

```css
.badge-black {
  background: #000000;
  color: #FFFFFF;
}

.badge-blue {
  background: #EEF2FF;
  color: #3F5CFF;
}

.badge-danger {
  background: #FFECEC;
  color: #FF3B30;
}

.badge-warning {
  background: #FFF7ED;
  color: #B45309;
}

.badge-success {
  background: #ECFDF3;
  color: #15803D;
}
```

---

## 16. Empty / loading / error states

Добавить единые состояния для всех страниц.

### Empty

```css
.empty-state {
  min-height: 180px;
  border-radius: 12px;
  background: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #667085;
  font-size: 13px;
}
```

### Loading skeleton

```css
.skeleton {
  border-radius: 8px;
  background: linear-gradient(
    90deg,
    #F3F4F6 25%,
    #FAFAFA 50%,
    #F3F4F6 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.2s ease-in-out infinite;
}
```

### Error

```css
.error-state {
  background: #FFECEC;
  color: #FF3B30;
  border-radius: 12px;
  padding: 16px;
  font-size: 13px;
}
```

---

## 17. Адаптив

Обязательно проверить адаптив.

### Desktop

- ширина 100%;
- внешний padding `12px`;
- сетка 12 колонок;
- карточки в несколько колонок.

### Tablet

- header перестраивается:
  - логотип и заголовок сверху;
  - фильтры ниже;
- KPI по 2–3 в ряд;
- большие блоки по 1–2 в ряд.

### Mobile

- одна колонка;
- header вертикальный;
- фильтры один под другим;
- KPI одна колонка или две, если помещаются;
- таблицы с horizontal scroll;
- карточки планировок в одну колонку;
- графики не ломаются, имеют min-width или адаптивную отрисовку.

---

## 18. Что важно не сломать

Не ломать:

- расчеты метрик;
- фильтрацию;
- период анализа;
- переходы между страницами;
- CSV-экспорт;
- обновление данных;
- отображение изображений планировок;
- группировки планировок;
- текущие API/data loaders;
- тесты.

Если потребуется изменить структуру компонентов — сделать это аккуратно и модульно.

---

## 19. Предпочтительная структура компонентов

Если в проекте возможно, вынести общие UI-компоненты:

```text
components/ui/
  Card.tsx
  Badge.tsx
  Button.tsx
  Select.tsx
  MetricCard.tsx
  SectionCard.tsx
  CollapseButton.tsx
  SegmentedControl.tsx
  Table.tsx
  EmptyState.tsx
  Skeleton.tsx
  ErrorState.tsx

components/dashboard/
  DashboardHeader.tsx
  KpiGrid.tsx
  InsightsCard.tsx
  DynamicsCard.tsx
  ProjectMapCard.tsx
  MarketStructureCard.tsx
  DeveloperSummaryCard.tsx
```

Если такие компоненты уже есть — обновить их стили, а не создавать дубли.

---

## 20. Критерии готовности

Результат считается готовым, если:

1. Главная страница визуально соответствует приложенному макету.
2. Все остальные страницы приведены к той же дизайн-системе.
3. Нет старого визуального стиля с тяжелыми рамками и крупными синими кнопками.
4. Все карточки имеют единый border-radius, отступы и типографику.
5. KPI-карточки выглядят как в новом макете.
6. Фильтры встроены в верхнюю панель и выглядят компактно.
7. Таблицы стали легче и аккуратнее.
8. Бейджи и чипы унифицированы.
9. Состояния loading / empty / error оформлены в новом стиле.
10. Адаптив работает на desktop / tablet / mobile.
11. Бизнес-логика и данные не сломаны.
12. Линтер, тесты и сборка проходят успешно.

---

## 21. После реализации

После внесения изменений:

1. Запусти форматирование.
2. Запусти линтер.
3. Запусти тесты.
4. Проверь сборку.
5. Кратко опиши:
   - какие страницы обновлены;
   - какие компоненты изменены;
   - какие общие стили добавлены;
   - были ли fallback-решения;
   - что еще стоит улучшить отдельно.
