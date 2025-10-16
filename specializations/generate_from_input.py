import anthropic
import json
import os
import sys
import random
from pathlib import Path

# Добавляем путь к корню проекта для импорта config
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY

# Инициализация клиента
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Пути
INPUT_FILE = Path("input_prof.json")
THEMES_DIR = Path("output/themes")
FINAL_DIR = Path("output/final")

# Создаем директории
THEMES_DIR.mkdir(parents=True, exist_ok=True)
FINAL_DIR.mkdir(parents=True, exist_ok=True)


def parse_competency(comp_string):
    """
    Парсит строку компетенции типа:
    "Навыки Java [CORE 90%]"
    
    Возвращает: {
        "name": "Навыки Java",
        "type": "CORE",
        "importance": 90
    }
    """
    # Извлекаем имя (все до '[')
    name = comp_string.split('[')[0].strip()
    
    # Извлекаем тип и важность
    bracket_content = comp_string.split('[')[1].split(']')[0]  # "CORE 90%"
    parts = bracket_content.split()
    
    comp_type = parts[0]  # "CORE" или "DAILY"
    importance = int(parts[1].replace('%', ''))  # 90
    
    return {
        "name": name,
        "type": comp_type,
        "importance": importance
    }


def generate_themes(profile, specialization, competency):
    """Генерация 4 тем для компетенции"""
    
    prompt = f"""Ты генеришь темы для тестирования IT-специалистов на конференции в Казахстане.

ПРОФЕССИЯ: {profile}
СПЕЦИАЛИЗАЦИЯ: {specialization}
КОМПЕТЕНЦИЯ: {competency['name']}
ТИП: {competency['type']} {competency['importance']}%

ЗАДАЧА: Сгенерируй 4 темы для проверки этой компетенции.

ТРЕБОВАНИЯ:
- Темы должны покрывать разные аспекты компетенции
- Реалистичные для IT-индустрии
- От базовых до продвинутых аспектов
- Каждая тема - это конкретная область знаний внутри компетенции

ФОРМАТ ОТВЕТА (только JSON, без markdown):
{{
  "themes": [
    "Тема 1",
    "Тема 2", 
    "Тема 3",
    "Тема 4"
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = response.content[0].text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1])
    
    result = json.loads(text)
    return result['themes']


def generate_questions(profile, specialization, competency, theme):
    """Генерация 3 вопросов (Junior/Middle/Senior) с правильными ответами"""
    
    depth_guide = ""
    if competency['type'] == 'CORE' and competency['importance'] >= 85:
        depth_guide = "CORE компетенция высокой важности - Senior должен быть экспертом, вопросы про архитектуру, edge cases, оптимизацию."
    elif competency['type'] == 'CORE':
        depth_guide = "CORE компетенция - Senior должен глубоко понимать, вопросы про проектирование и best practices."
    elif competency['type'] == 'DAILY':
        depth_guide = "DAILY компетенция - Senior должен быть опытным практиком, вопросы про применение и troubleshooting."
    
    prompt = f"""Ты генеришь вопросы для тестирования IT-специалистов на конференции/форуме.

ПРОФЕССИЯ: {profile}
СПЕЦИАЛИЗАЦИЯ: {specialization}
КОМПЕТЕНЦИЯ: {competency['name']} [{competency['type']} {competency['importance']}%]
ТЕМА: {theme}

{depth_guide}

ЗАДАЧА: Сгенерируй 3 вопроса с ПРАВИЛЬНЫМИ ответами (по одному вопросу на уровень).

УРОВНИ СЛОЖНОСТИ:
- JUNIOR (6 мес - 1.5 года): Что такое? Как создать? Какой инструмент? → Базовые определения, синтаксис
- MIDDLE (2-3 года): В чем разница? Когда использовать? Как настроить? → Применение, выбор подхода
- SENIOR (5+ лет): Как спроектировать? Почему X вместо Y? Какие проблемы? → Зависит от типа компетенции (см. выше)

ТРЕБОВАНИЯ К ВОПРОСАМ:
- Вопрос должен быть четким и однозначным
- Контекст: банки/телеком в Казахстане
- Вопрос связан с темой, компетенцией и специализацией

ТРЕБОВАНИЯ К ПРАВИЛЬНЫМ ОТВЕТАМ:
- Точный и конкретный
- 5-15 слов (варьируй длину естественным образом)
- Без лишних слов, профессиональная формулировка
- Технически корректный

ФОРМАТ ОТВЕТА (только JSON, без markdown):
{{
  "questions": [
    {{
      "level": "Junior",
      "question": "текст вопроса",
      "correct_answer": "правильный ответ"
    }},
    {{
      "level": "Middle",
      "question": "текст вопроса",
      "correct_answer": "правильный ответ"
    }},
    {{
      "level": "Senior",
      "question": "текст вопроса",
      "correct_answer": "правильный ответ"
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = response.content[0].text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1])
    
    result = json.loads(text)
    return result['questions']


def count_words(text):
    """Подсчет количества слов"""
    return len(text.split())


def generate_wrong_answers(profile, specialization, competency, theme, level, question, correct_answer):
    """Генерация 3 неправильных вариантов ответа"""
    
    correct_words = count_words(correct_answer)
    
    prompt = f"""Ты генеришь неправильные варианты ответов для тестирования IT-специалистов на конференции в Казахстане (банки/телеком).

КОНТЕКСТ:
Профессия: {profile}
Специализация: {specialization}
Компетенция: {competency}
Тема: {theme}
Уровень: {level}

ВОПРОС: {question}

ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer}
Длина правильного ответа: {correct_words} слов

ЗАДАЧА: Сгенерируй 3 НЕПРАВИЛЬНЫХ варианта ответа.

ТРЕБОВАНИЯ К НЕПРАВИЛЬНЫМ ВАРИАНТАМ:
✓ Примерно такая же длина как правильный: {correct_words} ± 1-3 слова (можно короче или длиннее)
✓ Правдоподобные, звучат профессионально
✓ Используют правильную терминологию
✓ НЕ содержат: "не нужно", "невозможно", "нет разницы", "всегда", "никогда", "может быть"
✓ Уверенная тональность (как правильный ответ)

КРИТИЧНО ВАЖНО - избегай этих ошибок:
❌ НЕ делай технически правильные варианты! Если подход работает в реальности - это НЕ неправильный ответ
   Плохо: "класс с __call__" (это валидный декоратор!)
   Хорошо: "функция с @decorator.register() из встроенного модуля"

❌ НЕ делай явно абсурдные варианты, которые никто не использует
   Плохо: "WebSocket для ML-скоринга" (никто так не делает)
   Плохо: "binary тип для полнотекстового поиска" (абсурд)
   Хорошо: технологии из той же области, но для другого use case

❌ НЕ путай концепции с похожими названиями
   Плохо: "tuple для уникальности" (tuple про immutability, не uniqueness)
   Хорошо: "frozenset для неизменяемости и уникальности"

✅ ПРАВИЛЬНЫЙ ПОДХОД:
- Технологии/подходы из смежных областей
- Похожие концепции, но не подходящие для конкретной задачи
- Устаревшие решения или для других масштабов
- Частично верные утверждения с тонкой ошибкой

ВАЖНО:
- Все варианты должны быть РАЗНЫМИ по смыслу
- Неправильные должны быть правдоподобны для Junior/Middle уровня
- Опытный Senior должен легко отличить правильный

ФОРМАТ ОТВЕТА (только JSON, без markdown):
{{
  "wrong_answers": [
    "неправильный вариант 1",
    "неправильный вариант 2",
    "неправильный вариант 3"
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = response.content[0].text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1])
    
    try:
        result = json.loads(text)
        if 'wrong_answers' not in result:
            print(f"\n❌ ОШИБКА: Неверный формат ответа!")
            print(f"Получено: {text[:200]}...")
            raise KeyError('wrong_answers')
        return result['wrong_answers']
    except json.JSONDecodeError as e:
        print(f"\n❌ ОШИБКА парсинга JSON!")
        print(f"Текст ответа: {text[:200]}...")
        raise


def main():
    """Основная функция генерации"""
    
    print("=" * 70)
    print("УНИВЕРСАЛЬНЫЙ ГЕНЕРАТОР ВОПРОСОВ")
    print("=" * 70)
    
    # Читаем input
    if not INPUT_FILE.exists():
        print(f"❌ ОШИБКА: Файл {INPUT_FILE} не найден")
        exit(1)
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        input_data = json.load(f)
    
    profile = input_data['profile']
    specialization = input_data['specialization']
    file_name = input_data['file_name']
    competencies_raw = input_data['competencies']
    
    print(f"\nПрофессия: {profile}")
    print(f"Специализация: {specialization}")
    print(f"Компетенций: {len(competencies_raw)}")
    print(f"Имя файла: {file_name}")
    
    # Парсим компетенции
    competencies = [parse_competency(comp) for comp in competencies_raw]
    
    # ========== ШАГ 1: ГЕНЕРАЦИЯ ТЕМ ==========
    print("\n" + "=" * 70)
    print("ШАГ 1: ГЕНЕРАЦИЯ ТЕМ")
    print("=" * 70)
    
    themes_data = {
        "profile": profile,
        "specialization": specialization,
        "file_name": file_name,
        "competencies": []
    }
    
    for comp_idx, competency in enumerate(competencies, 1):
        print(f"\n[{comp_idx}/{len(competencies)}] {competency['name']} [{competency['type']} {competency['importance']}%]")
        print("    → Генерация тем...")
        
        themes = generate_themes(profile, specialization, competency)
        
        themes_data['competencies'].append({
            "competency": competency['name'],
            "type": competency['type'],
            "importance": competency['importance'],
            "themes": themes
        })
        
        for idx, theme in enumerate(themes, 1):
            print(f"       {idx}. {theme}")
    
    # Сохраняем темы
    themes_file = THEMES_DIR / f"{file_name}_themes.json"
    with open(themes_file, 'w', encoding='utf-8') as f:
        json.dump(themes_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Темы сохранены: {themes_file}")
    
    # ========== ШАГ 2: ГЕНЕРАЦИЯ ВОПРОСОВ ==========
    print("\n" + "=" * 70)
    print("ШАГ 2: ГЕНЕРАЦИЯ ВОПРОСОВ")
    print("=" * 70)
    
    questions_data = {
        "profile": profile,
        "specialization": specialization,
        "file_name": file_name,
        "competencies": []
    }
    
    for comp_idx, comp_themes in enumerate(themes_data['competencies'], 1):
        competency = competencies[comp_idx - 1]
        print(f"\n[{comp_idx}/{len(competencies)}] {comp_themes['competency']}")
        
        comp_questions = {
            "competency": comp_themes['competency'],
            "type": comp_themes['type'],
            "importance": comp_themes['importance'],
            "themes": []
        }
        
        for theme_idx, theme in enumerate(comp_themes['themes'], 1):
            print(f"    [{theme_idx}/4] {theme}")
            
            questions = generate_questions(
                profile,
                specialization,
                competency,
                theme
            )
            
            comp_questions['themes'].append({
                "theme": theme,
                "questions": questions
            })
            
            for q in questions:
                words = count_words(q['correct_answer'])
                print(f"         • {q['level']}: {words} слов")
        
        questions_data['competencies'].append(comp_questions)
    
    # Сохраняем вопросы
    questions_file = THEMES_DIR / f"{file_name}_questions.json"
    with open(questions_file, 'w', encoding='utf-8') as f:
        json.dump(questions_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Вопросы сохранены: {questions_file}")
    
    # ========== ШАГ 3: ГЕНЕРАЦИЯ НЕПРАВИЛЬНЫХ ВАРИАНТОВ ==========
    print("\n" + "=" * 70)
    print("ШАГ 3: ГЕНЕРАЦИЯ НЕПРАВИЛЬНЫХ ВАРИАНТОВ")
    print("=" * 70)
    
    total_questions = sum(
        len(theme['questions'])
        for comp in questions_data['competencies']
        for theme in comp['themes']
    )
    
    current = 0
    
    for comp in questions_data['competencies']:
        print(f"\n{comp['competency']}")
        
        for theme in comp['themes']:
            print(f"  {theme['theme']}")
            
            for question in theme['questions']:
                current += 1
                level = question['level']
                correct_answer = question['correct_answer']
                correct_words = count_words(correct_answer)
                
                print(f"    [{current}/{total_questions}] {level}: {correct_words} слов... ", end='', flush=True)
                
                wrong_answers = generate_wrong_answers(
                    profile,
                    specialization,
                    comp['competency'],
                    theme['theme'],
                    level,
                    question['question'],
                    correct_answer
                )
                
                # Создаем список из 4 вариантов
                all_answers = [correct_answer] + wrong_answers
                random.shuffle(all_answers)
                correct_position = all_answers.index(correct_answer) + 1
                
                # Добавляем варианты
                question['var_1'] = all_answers[0]
                question['var_2'] = all_answers[1]
                question['var_3'] = all_answers[2]
                question['var_4'] = all_answers[3]
                question['correct_position'] = correct_position
                
                wrong_lengths = [count_words(ans) for ans in wrong_answers]
                print(f"✓ (неправ: {wrong_lengths})")
    
    # Сохраняем финальный результат
    final_file = FINAL_DIR / f"{file_name}.json"
    with open(final_file, 'w', encoding='utf-8') as f:
        json.dump(questions_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 70)
    print(f"✓ ФИНАЛЬНЫЙ РЕЗУЛЬТАТ: {final_file}")
    print("=" * 70)
    
    # Статистика
    positions = [1, 2, 3, 4]
    position_counts = {pos: 0 for pos in positions}
    
    for comp in questions_data['competencies']:
        for theme in comp['themes']:
            for question in theme['questions']:
                position_counts[question['correct_position']] += 1
    
    print(f"\nСТАТИСТИКА:")
    print(f"  Компетенций: {len(questions_data['competencies'])}")
    print(f"  Тем: {sum(len(comp['themes']) for comp in questions_data['competencies'])}")
    print(f"  Вопросов: {total_questions}")
    
    print(f"\nРАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ:")
    for pos in positions:
        count = position_counts[pos]
        percentage = (count / total_questions * 100) if total_questions > 0 else 0
        print(f"  var_{pos}: {count} ({percentage:.1f}%)")


if __name__ == "__main__":
    if not ANTHROPIC_API_KEY:
        print("❌ ОШИБКА: Не найден ANTHROPIC_API_KEY")
        exit(1)
    
    main()