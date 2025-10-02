import asyncio
import sys
import os

# Добавляем родительскую папку
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def create_tables():
    print("🚀 Creating tables...")
    await init_db_pool()
    
    with open('db/init_db.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
    
    await close_db_pool()
    print("✅ All tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_tables())