import asyncio
import sys
import os

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection


async def delete_test_users(condition_field: str, condition_value: str):
    """
    Удаляет пользователей по условию и все их связанные данные
    
    Args:
        condition_field: поле для условия ('surname', 'name', 'phone', etc.)
        condition_value: значение для поиска
    """
    await init_db_pool()
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            
            # Находим пользователей
            query = f"SELECT id, name, surname FROM users WHERE {condition_field} = %s"
            await cur.execute(query, (condition_value,))
            users = await cur.fetchall()
            
            if not users:
                print(f"✅ No users found")
                await close_db_pool()
                return
            
            # Удаляем (CASCADE удалит все связанные данные)
            user_ids = [u[0] for u in users]
            await cur.execute(
                f"DELETE FROM users WHERE id = ANY(%s)",
                (user_ids,)
            )
            
            print(f"✅ Deleted {len(users)} user(s)")
    
    await close_db_pool()


async def main():
    """Main function"""
    
    # Удалить всех с фамилией Test
    await delete_test_users(
        'company', 'Test Company')

    xs = ['Иван', 'Tyu', 'рнн', 'отпр', 'Hii', 'Hb', 'К', 'Yyu', 'Hhj', 'pp', 'dddd', 'ppp', 'Aa', ]
    for x in xs:
        await delete_test_users('name', x)
    
    # Другие примеры:
    # await delete_test_users('name', 'Тестовый')
    # await delete_test_users('phone', '+77001234567')


if __name__ == "__main__":
    asyncio.run(main())