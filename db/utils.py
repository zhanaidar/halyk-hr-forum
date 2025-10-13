import random
from db.database import get_db_connection


async def generate_test_topics(user_test_id: int, specialization_id: int):
    """
    Генерирует 8 случайных тем для теста юзера
    
    Алгоритм:
    1. Получаем компетенции специализации (сортировка по importance DESC)
    2. Рассчитываем сколько тем брать из каждой компетенции
    3. Выбираем случайные темы из каждой компетенции
    4. Сохраняем в user_test_topics с правильным порядком (группировка по компетенциям)
    
    Args:
        user_test_id: ID теста юзера
        specialization_id: ID специализации
    """
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            # 1. Получаем компетенции (сортировка по важности)
            await cur.execute("""
                SELECT id, name, importance
                FROM competencies
                WHERE specialization_id = %s
                ORDER BY importance DESC
            """, (specialization_id,))
            
            competencies = await cur.fetchall()
            num_competencies = len(competencies)
            
            if num_competencies == 0:
                raise Exception(f"No competencies found for specialization_id={specialization_id}")
            
            # 2. Рассчитываем распределение тем
            topics_distribution = calculate_topics_distribution(num_competencies)
            
            print(f"📊 Competencies: {num_competencies}, Distribution: {topics_distribution}")
            
            # 3. Генерируем темы для каждой компетенции
            topic_order = 1
            selected_topics = []
            
            for idx, (comp_id, comp_name, importance) in enumerate(competencies):
                num_topics_needed = topics_distribution[idx]
                
                # Получаем все темы этой компетенции
                await cur.execute("""
                    SELECT id, name
                    FROM topics
                    WHERE competency_id = %s
                """, (comp_id,))
                
                available_topics = await cur.fetchall()
                
                if len(available_topics) < num_topics_needed:
                    print(f"⚠️ Competency '{comp_name}' has only {len(available_topics)} topics, needed {num_topics_needed}")
                    num_topics_needed = len(available_topics)
                
                # Выбираем случайные темы
                chosen_topics = random.sample(available_topics, num_topics_needed)
                
                # Добавляем в список с порядком
                for topic_id, topic_name in chosen_topics:
                    selected_topics.append({
                        'topic_id': topic_id,
                        'competency_id': comp_id,
                        'topic_order': topic_order,
                        'topic_name': topic_name,
                        'comp_name': comp_name
                    })
                    topic_order += 1
                
                print(f"  ✅ Competency '{comp_name}' (importance={importance}): selected {num_topics_needed} topics")
            
            # 4. Сохраняем в БД
            for topic_data in selected_topics:
                await cur.execute("""
                    INSERT INTO user_test_topics 
                    (user_test_id, topic_id, competency_id, topic_order)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user_test_id,
                    topic_data['topic_id'],
                    topic_data['competency_id'],
                    topic_data['topic_order']
                ))
                
                print(f"    📌 Order {topic_data['topic_order']}: {topic_data['topic_name']}")
            
            print(f"✅ Generated {len(selected_topics)} topics for user_test_id={user_test_id}")


def calculate_topics_distribution(num_competencies: int) -> list:
    """
    Рассчитывает сколько тем брать из каждой компетенции
    Всего нужно 8 тем
    
    Правила:
    - 4 компетенции: все по 2 темы (2+2+2+2 = 8)
    - 5 компетенций: топ-3 по 2 темы, остальные по 1 (2+2+2+1+1 = 8)
    - 6 компетенций: топ-2 по 2 темы, остальные по 1 (2+2+1+1+1+1 = 8)
    
    Args:
        num_competencies: количество компетенций
        
    Returns:
        list: сколько тем брать из каждой компетенции [2, 2, 1, 1, 1, 1]
    """
    TOTAL_TOPICS = 8
    
    if num_competencies == 4:
        # Все по 2 темы
        return [2, 2, 2, 2]
    
    elif num_competencies == 5:
        # Топ-3: по 2 темы, остальные 2: по 1 теме
        return [2, 2, 2, 1, 1]
    
    elif num_competencies == 6:
        # Топ-2: по 2 темы, остальные 4: по 1 теме
        return [2, 2, 1, 1, 1, 1]
    
    else:
        # Если компетенций меньше 4 или больше 6
        # Распределяем равномерно
        base_topics = TOTAL_TOPICS // num_competencies
        remainder = TOTAL_TOPICS % num_competencies
        
        distribution = [base_topics] * num_competencies
        
        # Добавляем остаток первым компетенциям
        for i in range(remainder):
            distribution[i] += 1
        
        return distribution


async def get_test_progress(user_test_id: int) -> dict:
    """
    Получить прогресс теста с группировкой по компетенциям
    
    Returns:
        {
            "competencies": [
                {
                    "id": 1,
                    "name": "Навыки Java",
                    "answered": 5,
                    "correct": 2,
                    "total": 6
                },
                ...
            ],
            "total": {
                "answered": 10,
                "correct": 5,
                "total": 24
            },
            "current_question_number": 11
        }
    """
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            # Получаем текущий номер вопроса
            await cur.execute("""
                SELECT current_question_number
                FROM user_specialization_tests
                WHERE id = %s
            """, (user_test_id,))
            
            row = await cur.fetchone()
            current_question = row[0] if row else 1
            
            # Получаем статистику по компетенциям
            await cur.execute("""
                SELECT 
                    c.id,
                    c.name,
                    COUNT(DISTINCT q.id) as total_questions,
                    COUNT(DISTINCT CASE WHEN ta.id IS NOT NULL THEN q.id END) as answered,
                    COUNT(DISTINCT CASE WHEN ta.is_correct = true THEN q.id END) as correct
                FROM user_test_topics utt
                JOIN competencies c ON c.id = utt.competency_id
                JOIN topics t ON t.id = utt.topic_id
                JOIN questions q ON q.topic_id = t.id
                LEFT JOIN test_answers ta ON ta.question_id = q.id AND ta.user_test_id = utt.user_test_id
                WHERE utt.user_test_id = %s
                GROUP BY c.id, c.name
                ORDER BY MIN(utt.topic_order)
            """, (user_test_id,))
            
            competencies_stats = await cur.fetchall()
            
            # Формируем ответ
            competencies = []
            total_answered = 0
            total_correct = 0
            total_questions = 0
            
            for comp_id, comp_name, total, answered, correct in competencies_stats:
                competencies.append({
                    "id": comp_id,
                    "name": comp_name,
                    "answered": answered,
                    "correct": correct,
                    "total": total
                })
                total_answered += answered
                total_correct += correct
                total_questions += total
            
            return {
                "competencies": competencies,
                "total": {
                    "answered": total_answered,
                    "correct": total_correct,
                    "total": total_questions
                },
                "current_question_number": current_question
            }