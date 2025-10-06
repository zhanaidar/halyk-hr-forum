import asyncio
import sys
import os

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

async def fix_duplicate_answers():
    """Удаляем дубликаты и добавляем уникальный constraint"""
    print("🔧 Fixing duplicate answers...")
    await init_db_pool()
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Шаг 1: Удаляем дубликаты (оставляем только первый ответ)
            print("📌 Removing duplicate answers...")
            await cur.execute("""
                DELETE FROM test_answers a
                USING test_answers b
                WHERE a.id > b.id 
                AND a.user_test_id = b.user_test_id 
                AND a.question_id = b.question_id
            """)
            
            # Шаг 2: Добавляем уникальный constraint
            print("🔒 Adding unique constraint...")
            try:
                await cur.execute("""
                    ALTER TABLE test_answers 
                    ADD CONSTRAINT unique_user_test_question 
                    UNIQUE (user_test_id, question_id)
                """)
                print("✅ Constraint added successfully!")
            except Exception as e:
                if "already exists" in str(e):
                    print("⚠️ Constraint already exists, skipping...")
                else:
                    raise e
    
    await close_db_pool()
    print("✅ Done!")

if __name__ == "__main__":
    asyncio.run(fix_duplicate_answers())