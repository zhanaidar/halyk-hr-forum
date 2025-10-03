from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional, List
import sys
import os

# Fix для Windows asyncio
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from db.database import init_db_pool, close_db_pool, get_db_connection
import config

import anthropic

# Инициализируем Claude client
# claude_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

import httpx

# В функции generate_ai_recommendation:
http_client = httpx.Client(timeout=30.0)
claude_client = anthropic.Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    http_client=http_client
)

async def generate_ai_recommendation(user_test_id: int):
    """Генерация AI рекомендации на основе результатов теста"""
    try:
        
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Получаем данные теста
                await cur.execute("""
                    SELECT 
                        ut.score,
                        ut.max_score,
                        c.name as competency_name,
                        u.name,
                        u.surname
                    FROM user_tests ut
                    JOIN competencies c ON c.id = ut.competency_id
                    JOIN users u ON u.id = ut.user_id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                test_data = await cur.fetchone()
                if not test_data:
                    return None
                
                score, max_score, competency, name, surname = test_data
                
                # НОВОЕ: Получаем детали ответов С ТЕМАМИ
                await cur.execute("""
                    SELECT 
                        q.level,
                        t.name as topic_name,
                        ta.is_correct
                    FROM test_answers ta
                    JOIN questions q ON q.id = ta.question_id
                    JOIN topics t ON t.id = q.topic_id
                    WHERE ta.user_test_id = %s
                    ORDER BY ta.answered_at
                """, (user_test_id,))

                answers = await cur.fetchall()

                # Формируем детали для промпта
                answers_summary = []
                for level, topic_name, is_correct in answers:
                    status = "✓ Правильно" if is_correct else "✗ Неправильно"
                    answers_summary.append(f"{topic_name} ({level}): {status}")

                answers_text = "\n".join(answers_summary)
                
                # Определяем уровень
                if score >= 5:
                    level = "Senior"
                elif score >= 3:
                    level = "Middle"
                else:
                    level = "Junior"
                
                # Улучшенный промпт
                prompt = f"""Ты - опытный HR-специалист Халык банка. 

Кандидат: {name} {surname}
Компетенция: {competency}
Результат: {score}/{max_score} баллов (уровень {level})

Детали ответов:
{answers_text}

Создай краткую персональную рекомендацию (2-3 предложения):
- Отметь что освоено хорошо
- Укажи конкретные пробелы (Junior/Middle/Senior вопросы)
- Дай практический совет для развития

Тон: дружелюбный, конкретный, мотивирующий."""

                # Вызываем Claude API
                message = claude_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                recommendation = message.content[0].text.strip()
                
                # Сохраняем в БД
                await cur.execute(
                    """INSERT INTO ai_recommendations (user_test_id, recommendation_text)
                       VALUES (%s, %s)""",
                    (user_test_id, recommendation)
                )
                
                return recommendation
                
    except Exception as e:
        print(f"Ошибка генерации рекомендации: {e}")
        return "Рекомендация будет доступна позже."

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    # Startup
    print("🚀 Starting application...")
    await init_db_pool()
    print("✅ Database pool ready")
    
    yield
    
    # Shutdown
    print("🔄 Shutting down...")
    await close_db_pool()

app = FastAPI(
    title="Halyk HR Forum",
    description="Система тестирования компетенций",
    lifespan=lifespan
)

# Static files and templates
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")

# ===== PYDANTIC MODELS =====

class UserRegister(BaseModel):
    name: str
    surname: str
    phone: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None

class ProfileSelect(BaseModel):
    user_id: int
    profile_id: int

class TestStart(BaseModel):
    user_id: int
    competency_id: int

class AnswerSubmit(BaseModel):
    user_test_id: int
    question_id: int
    user_answer: int  # 1, 2, 3, или 4

# ===== HOMEPAGE =====
@app.get("/", response_class=HTMLResponse)
async def home():
    """Главная страница"""
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    
# @app.get("/", response_class=HTMLResponse)
# async def home(request: Request):
#     """Главная страница"""
#     return templates.TemplateResponse("index.html", {
#         "request": request,
#         "org_name": config.ORG_NAME,
#         "org_color": config.ORG_PRIMARY_COLOR
#     })

@app.get("/competencies", response_class=HTMLResponse)
async def competencies_page():
    """Страница компетенций"""
    with open('templates/competencies.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    
@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """Страница прохождения теста"""
    with open('templates/test.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    return {"status": "ok", "service": "halyk-hr-forum"}

# ===== API: РЕГИСТРАЦИЯ =====

@app.post("/api/register")
async def register_user(user: UserRegister):
    """Регистрация нового пользователя"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO users (name, surname, phone, company, job_title)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (user.name, user.surname, user.phone, user.company, user.job_title)
                )
                user_id = (await cur.fetchone())[0]
        
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: ПРОФИЛИ =====

@app.get("/api/profiles")
async def get_profiles():
    """Получить список профессий"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name, specialization FROM profiles ORDER BY id"
                )
                rows = await cur.fetchall()
        
        profiles = [
            {"id": row[0], "name": row[1], "specialization": row[2]}
            for row in rows
        ]
        
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/select-profile")
async def select_profile(data: ProfileSelect):
    """Пользователь выбирает профессию"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO user_profile_selections (user_id, profile_id)
                       VALUES (%s, %s)
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    (data.user_id, data.profile_id)
                )
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: КОМПЕТЕНЦИИ =====

@app.get("/api/competencies/{profile_id}")
async def get_competencies(profile_id: int, user_id: int):
    """Получить компетенции профиля со статусами прохождения"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Получаем компетенции с информацией о прохождении
                await cur.execute("""
                    SELECT 
                        c.id,
                        c.name,
                        ut.score,
                        ut.max_score,
                        ut.completed_at,
                        ut.started_at,
                        ut.id as user_test_id
                    FROM competencies c
                    LEFT JOIN user_tests ut ON ut.competency_id = c.id AND ut.user_id = %s
                    WHERE c.profile_id = %s
                    ORDER BY c.id
                """, (user_id, profile_id))
                
                rows = await cur.fetchall()
        
        competencies = []
        for row in rows:
            status = "not_started"
            if row[5]:  # started_at
                if row[4]:  # completed_at
                    status = "completed"
                else:
                    status = "in_progress"
            
            competencies.append({
                "id": row[0],
                "name": row[1],
                "score": row[2],
                "max_score": row[3],
                "status": status,
                "user_test_id": row[6]
            })
        
        return {"status": "success", "competencies": competencies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: ТЕСТЫ =====

@app.post("/api/start-test")
async def start_test(data: TestStart):
    """Начать тест компетенции"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Проверяем есть ли уже незавершенный тест
                await cur.execute(
                    """SELECT id FROM user_tests 
                       WHERE user_id = %s AND competency_id = %s""",
                    (data.user_id, data.competency_id)
                )
                existing = await cur.fetchone()
                
                if existing:
                    user_test_id = existing[0]
                else:
                    # Создаем новый тест
                    await cur.execute(
                        """INSERT INTO user_tests (user_id, competency_id, max_score)
                           VALUES (%s, %s, 6) RETURNING id""",
                        (data.user_id, data.competency_id)
                    )
                    user_test_id = (await cur.fetchone())[0]
        
        return {"status": "success", "user_test_id": user_test_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{user_test_id}/questions")
async def get_test_questions(user_test_id: int):
    """Получить вопросы для теста (2 темы × 3 вопроса)"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Получаем competency_id
                await cur.execute(
                    "SELECT competency_id FROM user_tests WHERE id = %s",
                    (user_test_id,)
                )
                competency_id = (await cur.fetchone())[0]
                
                # Получаем 2 темы с вопросами
                await cur.execute("""
                    SELECT 
                        t.id as topic_id,
                        t.name as topic_name,
                        q.id as question_id,
                        q.level,
                        q.question_text,
                        q.var_1,
                        q.var_2,
                        q.var_3,
                        q.var_4
                    FROM topics t
                    JOIN questions q ON q.topic_id = t.id
                    WHERE t.competency_id = %s
                    ORDER BY t.id, 
                             CASE q.level 
                                WHEN 'Junior' THEN 1 
                                WHEN 'Middle' THEN 2 
                                WHEN 'Senior' THEN 3 
                             END
                    LIMIT 6
                """, (competency_id,))
                
                rows = await cur.fetchall()
        
        questions = []
        for row in rows:
            questions.append({
                "question_id": row[2],
                "level": row[3],
                "topic_name": row[1],
                "question_text": row[4],
                "options": [row[5], row[6], row[7], row[8]]
            })
        
        return {"status": "success", "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-answer")
async def submit_answer(data: AnswerSubmit):
    """Отправить ответ на вопрос"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Получаем правильный ответ
                await cur.execute(
                    "SELECT correct_answer FROM questions WHERE id = %s",
                    (data.question_id,)
                )
                correct_answer = (await cur.fetchone())[0]
                
                is_correct = (data.user_answer == correct_answer)
                
                # Сохраняем ответ
                await cur.execute(
                    """INSERT INTO test_answers 
                       (user_test_id, question_id, user_answer, is_correct)
                       VALUES (%s, %s, %s, %s)""",
                    (data.user_test_id, data.question_id, data.user_answer, is_correct)
                )
        
        return {"status": "success", "is_correct": is_correct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complete-test/{user_test_id}")
async def complete_test(user_test_id: int):
    """Завершить тест и подсчитать результат"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Подсчитываем баллы
                await cur.execute(
                    """SELECT COUNT(*) FROM test_answers 
                       WHERE user_test_id = %s AND is_correct = true""",
                    (user_test_id,)
                )
                score = (await cur.fetchone())[0]
                
                # Обновляем user_tests
                await cur.execute(
                    """UPDATE user_tests 
                       SET score = %s, completed_at = NOW()
                       WHERE id = %s""",
                    (score, user_test_id)
                )
        
        # Генерируем AI рекомендацию
        recommendation = await generate_ai_recommendation(user_test_id)
        
        # Определяем уровень
        if score >= 5:
            level = "Senior"
        elif score >= 3:
            level = "Middle"
        else:
            level = "Junior"
        
        return {
            "status": "success",
            "score": score,
            "max_score": 6,
            "level": level,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.post("/api/complete-test/{user_test_id}")
# async def complete_test(user_test_id: int):
#     """Завершить тест и подсчитать результат"""
#     try:
#         async with get_db_connection() as conn:
#             async with conn.cursor() as cur:
#                 # Подсчитываем баллы
#                 await cur.execute(
#                     """SELECT COUNT(*) FROM test_answers 
#                        WHERE user_test_id = %s AND is_correct = true""",
#                     (user_test_id,)
#                 )
#                 score = (await cur.fetchone())[0]
                
#                 # Обновляем user_tests
#                 await cur.execute(
#                     """UPDATE user_tests 
#                        SET score = %s, completed_at = NOW()
#                        WHERE id = %s""",
#                     (score, user_test_id)
#                 )
        
#         # Определяем уровень
#         if score >= 5:
#             level = "Senior"
#         elif score >= 3:
#             level = "Middle"
#         else:
#             level = "Junior"
        
#         return {
#             "status": "success",
#             "score": score,
#             "max_score": 6,
#             "level": level
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/results/{user_test_id}")
async def get_results(user_test_id: int):
    """Получить результаты теста"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT 
                        ut.score,
                        ut.max_score,
                        ut.completed_at,
                        c.name as competency_name,
                        ar.recommendation_text
                    FROM user_tests ut
                    JOIN competencies c ON c.id = ut.competency_id
                    LEFT JOIN ai_recommendations ar ON ar.user_test_id = ut.id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                row = await cur.fetchone()
                
                if not row:
                    raise HTTPException(status_code=404, detail="Test not found")
                
                score = row[0]
                if score >= 5:
                    level = "Senior"
                elif score >= 3:
                    level = "Middle"
                else:
                    level = "Junior"
        
        return {
            "status": "success",
            "score": row[0],
            "max_score": row[1],
            "level": level,
            "competency_name": row[3],
            "recommendation": row[4]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)