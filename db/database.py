import asyncio
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
import sys
import os
# Добавляем родительскую папку в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

# Global connection pool
pool = None

async def init_db_pool():
    """Initialize database connection pool"""
    global pool
    try:
        pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=30,
            max_size=150,
            timeout=30,
            max_waiting=200,
            kwargs={"autocommit": True}
        )
        await pool.open()
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}")
        raise

async def close_db_pool():
    """Close database connection pool"""
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")

@asynccontextmanager
async def get_db_connection():
    """Get database connection from pool"""
    global pool
    if not pool:
        raise Exception("Database pool not initialized")
    
    async with pool.connection() as conn:
        yield conn

async def execute_query(query: str, params: tuple = None):
    """Execute query and return results"""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            try:
                return await cur.fetchall()
            except:
                return None

async def execute_one(query: str, params: tuple = None):
    """Execute query and return one result"""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            try:
                return await cur.fetchone()
            except:
                return None