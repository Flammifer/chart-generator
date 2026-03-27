# GP to YARG Chart Generator

Конвертер Guitar Pro 7/8 табов в формат чартов для YARG / Clone Hero.

Берёт `.gp` файл с гитарными табами и генерирует `notes.chart` + `song.ini` с четырьмя уровнями сложности.

## Установка

```bash
pip install -r requirements.txt
```

Зависимость одна — `pyguitarpro` (нужен только для fallback на GP3-5 файлы; GP7/8 парсятся напрямую из XML).

Python 3.10+.

## Быстрый старт

```bash
python main.py path/to/song.gp
```

Результат появится в папке `Artist - Title/` рядом с GP файлом. Внутри:
- `notes.chart` — ноты для всех 4 сложностей
- `song.ini` — метаданные

Для загрузки в YARG положите аудиофайл (`song.ogg`, `song.mp3` или `song.opus`) в ту же папку.

## GUI — генерация в один клик

```bash
python gui.py
```

Откроется окно с простым интерфейсом:

1. **Выберите GP файл** — кнопка `...` рядом с полем "Guitar Pro tab"
2. **Аудио подтянется автоматически** — если `song.mp3` / `song.ogg` лежит рядом с табом, он подставится сам. Или выберите вручную.
3. **Нажмите Generate Chart** — через пару секунд в логе появится результат: BPM, количество нот по сложностям, соло-секции.
4. **Preview** — после генерации разблокируется кнопка превью: визуализация нот на таймлайне с воспроизведением аудио. Прямо в превью можно подкрутить **Audio offset** и сразу пере-экспортировать чарт.

Результат: папка `Artist - Title/` с `notes.chart`, `song.ini` и скопированным аудиофайлом — готова для загрузки в YARG.

## Опции командной строки

```
python main.py <input.gp> [опции]

Аргументы:
  input                 Путь к .gp файлу (Guitar Pro 7/8)

Опции:
  -o, --output DIR      Папка вывода (по умолчанию: "Artist - Title" рядом с GP файлом)
  -a, --audio FILENAME  Имя аудиофайла в чарте (по умолчанию: song.ogg)
  -c, --config PATH     Путь к JSON-конфигу для настройки сложностей
  --dump-config PATH    Сохранить дефолтный конфиг в файл и выйти
```

## Примеры

```bash
# Базовая конвертация
python main.py "Metallica - Sandman.gp"

# С указанием mp3 и папки вывода
python main.py "song.gp" -a song.mp3 -o "My Song (Custom)"

# Экспорт дефолтного конфига, редактирование, запуск с ним
python main.py --dump-config config.json
# ... редактируете config.json ...
python main.py "song.gp" -c config.json
```

## Конфигурация сложностей

Сгенерируйте дефолтный конфиг:

```bash
python main.py --dump-config config.json
```

Получится JSON:

```json
{
  "hard": {
    "min_gap": 0.5,
    "max_chord_size": 2,
    "max_fret": 4,
    "allow_forced": true,
    "allow_sustains": true,
    "thin_repeated_eighths": true,
    "max_consecutive_same_gap": 4
  },
  "medium": {
    "min_gap": 1.0,
    "max_chord_size": 2,
    "max_fret": 3,
    "allow_forced": false,
    "allow_sustains": true,
    "thin_repeated_eighths": false,
    "max_consecutive_same_gap": 999
  },
  "easy": {
    "min_gap": 2.0,
    "max_chord_size": 1,
    "max_fret": 2,
    "allow_forced": false,
    "allow_sustains": false,
    "thin_repeated_eighths": false,
    "max_consecutive_same_gap": 999
  },
  "star_power_interval_bars": 12,
  "star_power_duration_bars": 3,
  "phrase_bar_group_size": 4,
  "merge_bar_window": 2
}
```

### Параметры сложности (hard / medium / easy)

| Параметр | Тип | Описание |
|---|---|---|
| `min_gap` | float | Минимальный промежуток между нотами в долях четвертной ноты. `0.5` = восьмая, `1.0` = четвертная, `2.0` = половинная. **Увеличьте для более лёгкой игры.** |
| `max_chord_size` | int | Максимальное количество одновременных нот. `1` = только одиночные, `2` = пары, `3` = трёхнотные аккорды. |
| `max_fret` | int | Максимальный лад (0=Green, 1=Red, 2=Yellow, 3=Blue, 4=Orange). Medium=3 (без Orange), Easy=2 (только G/R/Y). |
| `allow_forced` | bool | Разрешить HOPO (hammer-on / pull-off) ноты. |
| `allow_sustains` | bool | Разрешить длинные (зажатые) ноты. |
| `thin_repeated_eighths` | bool | Прореживать длинные цепочки одинаковых нот (типичный металл-чаггинг). |
| `max_consecutive_same_gap` | int | Сколько нот подряд с одинаковым промежутком допускать перед прореживанием. `4` = после 4-й подряд начнёт пропускать через одну. |

### Глобальные параметры

| Параметр | Тип | Описание |
|---|---|---|
| `star_power_interval_bars` | int | Минимальное расстояние между фразами Star Power (в тактах). |
| `star_power_duration_bars` | int | Длительность одной фразы Star Power (в тактах). |
| `phrase_bar_group_size` | int | Размер группы тактов при авто-разбиении на фразы (влияет на маппинг питчей). |
| `merge_bar_window` | int | Окно (в тактах) для решения lead vs rhythm при сведении треков. |

### Типичные пресеты

**Сделать Hard значительно легче Expert** (для казуальных игроков):
```json
{
  "hard": {
    "min_gap": 1.0,
    "max_chord_size": 2,
    "max_fret": 4,
    "allow_forced": true,
    "allow_sustains": true,
    "thin_repeated_eighths": true,
    "max_consecutive_same_gap": 2
  }
}
```

**Сделать Medium совсем простым:**
```json
{
  "medium": {
    "min_gap": 2.0,
    "max_chord_size": 1,
    "max_fret": 3,
    "allow_forced": false,
    "allow_sustains": false,
    "thin_repeated_eighths": false,
    "max_consecutive_same_gap": 999
  }
}
```

## Детекция соло

Программа автоматически определяет соло-секции и размечает их:

- **`E solo` / `E soloend`** — track events внутри каждой сложности, YARG показывает счётчик попаданий и бонусные очки.
- **`N 6 0` (tap flag)** — ноты в соло, сыгранные на высоких ладах (≥10 на реальной гитаре), помечаются как tap. Их можно играть **solo-кнопками** на верхней части грифа контроллера без strumming.

### Как детектируется соло

1. **Маркеры из GP файла** — если в табе есть секция с "Solo" в названии, она используется напрямую.
2. **Эвристика по трекам** — сравниваются Lead и Rhythm гитары по окнам в 4 такта. Соло определяется, когда Lead имеет одновременно:
   - Высокую нотную плотность относительно Rhythm
   - Широкое разнообразие питчей (≥6 уникальных)
   - Высокий регистр (лады ≥10 на реальной гитаре)
   - Высокий средний питч (MIDI ≥65)

Минимум 2 из 4 признаков должны совпасть.

## Как работает маппинг нот

Алгоритм основан на гайдах сообщества GH/Clone Hero чартеров:

1. **Фразы** — песня разбивается на фразы (по секциям из GP или автоматически по паузам/группам тактов).
2. **Питч → лад** — внутри каждой фразы MIDI-питчи маппятся на 5 ладов относительно локального диапазона: Green = самый низкий звук во фразе, Orange = самый высокий.
3. **Аккорды** — интервал между нотами аккорда определяет расстояние между ладами в GH: малый интервал → соседние лады (GR), квинта → через один (GY), октава → через два (GB).
4. **Сведение треков** — Lead гитара приоритетнее при мелодичной игре, Rhythm — при чаггинге/аккомпанементе.
5. **Сложности** — Expert содержит все ноты, каждая следующая сложность прореживает, упрощает аккорды и сужает диапазон ладов.

## Структура файлов

```
chart-generator/
├── main.py                # Точка входа, CLI
├── config.py              # Конфигурация сложностей
├── models.py              # Модели данных
├── gp7_parser.py          # Парсер Guitar Pro 7/8 (ZIP+XML)
├── track_merger.py        # Сведение Lead + Rhythm треков
├── phrase_splitter.py     # Разбиение на музыкальные фразы
├── pitch_mapper.py        # MIDI питч → 5 GH ладов
├── difficulty_reducer.py  # Expert → Hard → Medium → Easy
├── section_detector.py    # Авто-детекция секций песни
├── star_power.py          # Расстановка Star Power
├── solo_detector.py       # Детекция соло секций + tap ноты
├── chart_exporter.py      # Генерация .chart + song.ini
├── pipeline.py            # Оркестрация полного пайплайна
├── gui.py                 # GUI (tkinter)
├── preview.py             # Визуализация чарта с аудио
└── requirements.txt
```
