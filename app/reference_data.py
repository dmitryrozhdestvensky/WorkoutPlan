GROUPS = {
    'Тип нагрузки': ['Силовые', 'Кардио', 'Растяжка', 'Мобильность', 'Баланс', 'Координация'],
    'Зона тела': ['Ноги', 'Ягодицы', 'Спина', 'Грудь', 'Плечи', 'Руки', 'Кор', 'Всё тело'],
    'Основные мышцы': ['Квадрицепсы', 'Задняя поверхность бедра', 'Икры', 'Бицепс', 'Трицепс', 'Дельты', 'Широчайшие', 'Пресс'],
    'Вторичные мышцы': ['Deltoid Anterior', 'Pectoralis Major Sternal Head'],
    'Оборудование': ['Без оборудования', 'Штанга', 'Гантели', 'Гиря', 'Резинка', 'Блок', 'Силовой тренажёр', 'Турник', 'Скамья', 'Петли', 'Фитбол', 'BOSU', 'Кардиотренажёр'],
    'Движение': ['Приседание', 'Выпад', 'Наклон', 'Жим', 'Тяга', 'Сгибание', 'Разгибание', 'Вращение', 'Перенос веса', 'Прыжок'],
    'Особенности': ['Динамика', 'Статика', 'Одностороннее', 'Двустороннее'],
    'Сложность': ['Начальная', 'Средняя', 'Высокая'],
}


def initialize_references(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tag_groups(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, name TEXT NOT NULL);
    """)
    for name, values in GROUPS.items():
        if db.execute('SELECT 1 FROM tag_groups WHERE name=?', (name,)).fetchone():
            continue
        group = db.execute('INSERT INTO tag_groups(name) VALUES(?)', (name,)).lastrowid
        db.executemany('INSERT INTO tags(group_id,name) VALUES(?,?)', [(group, value) for value in values])
