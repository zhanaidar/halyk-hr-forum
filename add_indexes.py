import asyncio
import sys
import os
import asyncio.selector_events

# Добавляем родительскую папку в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

async def add_indexes():
    """Добавить индексы для оптимизации"""
    
    # Инициализируем pool
    print("🔌 Подключаемся к БД...")
    await init_db_pool()
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                
                print("📊 Создаём индексы...")
                
                # Индекс 1
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_questions_topic_level 
                    ON questions(topic_id, level)
                """)
                print("✅ idx_questions_topic_level создан")
                
                # Индекс 2
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_test_answers_test_question 
                    ON test_answers(user_test_id, question_id)
                """)
                print("✅ idx_test_answers_test_question создан")
                
                # Индекс 3
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_test_topics_test_order 
                    ON user_test_topics(user_test_id, topic_order)
                """)
                print("✅ idx_user_test_topics_test_order создан")
                
                print("🎉 Все индексы успешно созданы!")
    
    finally:
        # Закрываем pool
        await close_db_pool()
        print("👋 Отключились от БД")

if __name__ == "__main__":
    # Фикс для Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(add_indexes())