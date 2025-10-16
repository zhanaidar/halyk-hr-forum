import json
import asyncio
import sys
import os
from pathlib import Path

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection


async def import_all_specializations(folder_path: str):
    """
    Импортирует все JSON файлы из папки specializations/output/final/
    
    Логика:
    1. Читает все .json файлы из папки
    2. Для каждого файла проверяет БД:
       - Profile существует? Используем ID, иначе создаем
       - Specialization существует? Пропускаем файл, иначе создаем все
    3. ID продолжаются с MAX(id) + 1 (автоматически через SERIAL)
    """
    
    await init_db_pool()
    
    # Находим все JSON файлы
    json_files = list(Path(folder_path).glob('*.json'))
    
    if not json_files:
        print(f"❌ No JSON files found in {folder_path}")
        await close_db_pool()
        return
    
    print(f"📁 Found {len(json_files)} files\n")
    
    stats = {
        'files_processed': 0,
        'files_skipped': 0,
        'profiles_created': 0,
        'profiles_existing': 0,
        'specializations_created': 0,
        'specializations_skipped': 0,
        'competencies_created': 0,
        'topics_created': 0,
        'questions_created': 0
    }
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            for json_file in sorted(json_files):
                
                # Читаем JSON
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                profile_name = data['profile']
                specialization_name = data['specialization']
                # file_name не используем
                
                # 1. Проверяем Profile
                await cur.execute(
                    "SELECT id FROM profiles WHERE name = %s",
                    (profile_name,)
                )
                profile_row = await cur.fetchone()
                
                profile_status = ""
                if profile_row:
                    profile_id = profile_row[0]
                    profile_status = "Profile: existing"
                    stats['profiles_existing'] += 1
                else:
                    # Создаем профиль
                    await cur.execute(
                        "INSERT INTO profiles (name, has_specializations) VALUES (%s, %s) RETURNING id",
                        (profile_name, True)
                    )
                    profile_id = (await cur.fetchone())[0]
                    profile_status = "Profile: created"
                    stats['profiles_created'] += 1
                
                # 2. Проверяем Specialization
                await cur.execute(
                    "SELECT id FROM specializations WHERE profile_id = %s AND name = %s",
                    (profile_id, specialization_name)
                )
                spec_row = await cur.fetchone()
                
                if spec_row:
                    print(f"⚪ {specialization_name} — already exists | {profile_status}")
                    stats['files_skipped'] += 1
                    stats['specializations_skipped'] += 1
                    continue
                
                # 3. Создаем Specialization
                await cur.execute(
                    "INSERT INTO specializations (profile_id, name) VALUES (%s, %s) RETURNING id",
                    (profile_id, specialization_name)
                )
                specialization_id = (await cur.fetchone())[0]
                stats['specializations_created'] += 1
                
                # 4. Обрабатываем Competencies
                for comp_data in data['competencies']:
                    # competency + " [" + type + " " + importance + "%]"
                    comp_base_name = comp_data['competency']
                    comp_type = comp_data.get('type', 'CORE')
                    importance = comp_data.get('importance', 50)
                    
                    # Формируем полное название: "SQL и работа с БД [CORE 90%]"
                    competency_name = f"{comp_base_name} [{comp_type} {importance}%]"
                    
                    await cur.execute(
                        "INSERT INTO competencies (specialization_id, name, importance) VALUES (%s, %s, %s) RETURNING id",
                        (specialization_id, competency_name, importance)
                    )
                    competency_id = (await cur.fetchone())[0]
                    stats['competencies_created'] += 1
                    
                    # 5. Обрабатываем Topics (в JSON это themes)
                    for theme_data in comp_data['themes']:
                        topic_name = theme_data['theme']  # theme -> topic_name
                        
                        await cur.execute(
                            "INSERT INTO topics (competency_id, name) VALUES (%s, %s) RETURNING id",
                            (competency_id, topic_name)
                        )
                        topic_id = (await cur.fetchone())[0]
                        stats['topics_created'] += 1
                        
                        # 6. Batch insert Questions
                        questions_batch = []
                        for q in theme_data['questions']:
                            questions_batch.append((
                                topic_id,
                                q['level'],                    # level
                                q['question'],                 # question -> question_text
                                q['var_1'],
                                q['var_2'],
                                q['var_3'],
                                q['var_4'],
                                q['correct_position']          # correct_position -> correct_answer
                            ))
                        
                        if questions_batch:
                            await cur.executemany(
                                """INSERT INTO questions 
                                (topic_id, level, question_text, var_1, var_2, var_3, var_4, correct_answer)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                                questions_batch
                            )
                            stats['questions_created'] += len(questions_batch)
                
                print(f"  ✅ Imported: {len(data['competencies'])} competencies\n")
                stats['files_processed'] += 1
    
    await close_db_pool()
    
    # Итоговая статистика
    print("=" * 60)
    print("📊 IMPORT SUMMARY")
    print("=" * 60)
    print(f"Files processed:          {stats['files_processed']}")
    print(f"Files skipped:            {stats['files_skipped']}")
    print(f"Profiles created:         {stats['profiles_created']}")
    print(f"Profiles existing:        {stats['profiles_existing']}")
    print(f"Specializations created:  {stats['specializations_created']}")
    print(f"Specializations skipped:  {stats['specializations_skipped']}")
    print(f"Competencies created:     {stats['competencies_created']}")
    print(f"Topics created:           {stats['topics_created']}")
    print(f"Questions created:        {stats['questions_created']}")
    print("=" * 60)


async def main():
    """Main function"""
    print("🚀 Starting specializations import...\n")
    
    # Путь к папке с JSON файлами
    folder_path = 'C:/Users/everg/halyk-hr-forum/specializations/output/final'
    
    await import_all_specializations(folder_path)
    
    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())