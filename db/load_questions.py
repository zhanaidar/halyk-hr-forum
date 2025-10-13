import json
import asyncio
import sys
import os
import re

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection


def extract_importance(competency_name: str) -> int:
    """
    Извлекает важность из названия компетенции
    Пример: "Знание C# [CORE 90%]" -> 90
    """
    match = re.search(r'\[CORE\s+(\d+)%\]', competency_name)
    if match:
        return int(match.group(1))
    return 50  # Default importance


async def load_questions_from_json(json_file_path: str):
    """Загрузка вопросов из JSON в новую структуру БД"""
    
    # Читаем JSON
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    profiles_data = data.get('profiles', [])
    
    if not profiles_data:
        print("❌ No profiles found in JSON file")
        return
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            # Группируем по profile (профессии)
            profiles_dict = {}
            for item in profiles_data:
                profile_name = item['profile']
                specialization_name = item['specialization']
                
                if profile_name not in profiles_dict:
                    profiles_dict[profile_name] = []
                
                profiles_dict[profile_name].append({
                    'specialization': specialization_name,
                    'competencies': item['competencies']
                })
            
            # Обрабатываем каждую профессию
            for profile_name, specializations_list in profiles_dict.items():
                
                # Определяем: есть ли специализации
                has_specializations = len(specializations_list) > 1 or (
                    len(specializations_list) == 1 and 
                    specializations_list[0]['specialization'] != profile_name
                )
                
                # Создаём профессию
                await cur.execute(
                    "INSERT INTO profiles (name, has_specializations) VALUES (%s, %s) RETURNING id",
                    (profile_name, has_specializations)
                )
                profile_id = (await cur.fetchone())[0]
                print(f"\n✅ Created profile: {profile_name} (ID: {profile_id}, has_spec: {has_specializations})")
                
                # Обрабатываем специализации
                for spec_data in specializations_list:
                    specialization_name = spec_data['specialization']
                    
                    # Создаём специализацию
                    await cur.execute(
                        "INSERT INTO specializations (profile_id, name) VALUES (%s, %s) RETURNING id",
                        (profile_id, specialization_name)
                    )
                    specialization_id = (await cur.fetchone())[0]
                    print(f"  ✅ Specialization: {specialization_name} (ID: {specialization_id})")
                    
                    # Обрабатываем компетенции
                    for competency in spec_data['competencies']:
                        competency_name = competency['competency_name']
                        importance = extract_importance(competency_name)
                        
                        await cur.execute(
                            "INSERT INTO competencies (specialization_id, name, importance) VALUES (%s, %s, %s) RETURNING id",
                            (specialization_id, competency_name, importance)
                        )
                        competency_id = (await cur.fetchone())[0]
                        print(f"    ✅ Competency: {competency_name} (ID: {competency_id}, importance: {importance})")
                        
                        # Обрабатываем темы
                        for topic in competency['topics']:
                            topic_name = topic['topic_name']
                            
                            await cur.execute(
                                "INSERT INTO topics (competency_id, name) VALUES (%s, %s) RETURNING id",
                                (competency_id, topic_name)
                            )
                            topic_id = (await cur.fetchone())[0]
                            print(f"      ✅ Topic: {topic_name} (ID: {topic_id})")
                            
                            # Загружаем вопросы
                            for question in topic['questions']:
                                await cur.execute(
                                    """INSERT INTO questions 
                                    (topic_id, level, question_text, var_1, var_2, var_3, var_4, correct_answer)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                                    (
                                        topic_id,
                                        question['level'],
                                        question['question_text'],
                                        question['var_1'],
                                        question['var_2'],
                                        question['var_3'],
                                        question['var_4'],
                                        question['correct_answer']
                                    )
                                )
                            print(f"        ✅ Loaded {len(topic['questions'])} questions")
            
            print(f"\n✅ Successfully loaded all data from {json_file_path}")


async def main():
    """Main function"""
    print("🚀 Starting database loading...")
    
    # Initialize connection pool
    await init_db_pool()
    
    # Load questions from JSON
    await load_questions_from_json('Questions.json')
    
    # Close pool
    await close_db_pool()
    
    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())