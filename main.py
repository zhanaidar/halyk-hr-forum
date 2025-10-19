from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
import sys
import os



# Fix для Windows asyncio
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from db.database import init_db_pool, close_db_pool, get_db_connection
from db.utils import generate_test_topics, get_test_progress
import config

import anthropic
import httpx

# Инициализируем Claude client
http_client = httpx.Client(timeout=30.0)
claude_client = anthropic.Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    http_client=http_client
)

from auth import create_access_token, verify_token

# ===== DEPENDENCY =====
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Получить текущего пользователя из JWT токена"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    user_data = verify_token(token)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return user_data

# ===== AI РЕКОМЕНДАЦИИ (MOCK ДЛЯ ТЕСТА) =====
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
                        s.name as specialization_name,
                        u.name,
                        u.surname
                    FROM user_specialization_tests ut
                    JOIN specializations s ON s.id = ut.specialization_id
                    JOIN users u ON u.id = ut.user_id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                test_data = await cur.fetchone()
                if not test_data:
                    return None
                
                score, max_score, specialization, name, surname = test_data
                
                # Определяем уровень
                percentage = (score / max_score) * 100
                if percentage >= 80:
                    level = "Senior"
                elif percentage >= 50:
                    level = "Middle"
                else:
                    level = "Junior"
                
                # ========================================
                # MOCK РЕКОМЕНДАЦИЯ (БЕЗ CLAUDE API)
                # ========================================
                recommendation = f"""Рекомендация: {name}, вы показали {level} уровень в области "{specialization}" ({score}/{max_score} баллов). Продолжайте развиваться в выбранном направлении и обращайте внимание на практические навыки."""
                
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

# # ===== AI РЕКОМЕНДАЦИИ (БЕЗ ИЗМЕНЕНИЙ) =====
# async def generate_ai_recommendation(user_test_id: int):
#     """Генерация AI рекомендации на основе результатов теста"""
#     try:
#         async with get_db_connection() as conn:
#             async with conn.cursor() as cur:
#                 # Получаем данные теста
#                 await cur.execute("""
#                     SELECT 
#                         ut.score,
#                         ut.max_score,
#                         s.name as specialization_name,
#                         u.name,
#                         u.surname
#                     FROM user_specialization_tests ut
#                     JOIN specializations s ON s.id = ut.specialization_id
#                     JOIN users u ON u.id = ut.user_id
#                     WHERE ut.id = %s
#                 """, (user_test_id,))
                
#                 test_data = await cur.fetchone()
#                 if not test_data:
#                     return None
                
#                 score, max_score, specialization, name, surname = test_data
                
#                 # Получаем детали ответов С ТЕМАМИ
#                 await cur.execute("""
#                     SELECT 
#                         q.level,
#                         t.name as topic_name,
#                         ta.is_correct
#                     FROM test_answers ta
#                     JOIN questions q ON q.id = ta.question_id
#                     JOIN topics t ON t.id = q.topic_id
#                     WHERE ta.user_test_id = %s
#                     ORDER BY ta.answered_at
#                 """, (user_test_id,))

#                 answers = await cur.fetchall()

#                 # Формируем детали для промпта
#                 answers_summary = []
#                 for level, topic_name, is_correct in answers:
#                     status = "✓ Правильно" if is_correct else "✗ Неправильно"
#                     answers_summary.append(f"{topic_name} ({level}): {status}")

#                 answers_text = "\n".join(answers_summary)
                
#                 # Определяем уровень
#                 percentage = (score / max_score) * 100
#                 if percentage >= 80:
#                     level = "Senior"
#                 elif percentage >= 50:
#                     level = "Middle"
#                 else:
#                     level = "Junior"
                
#                 # Промпт для Claude
#                 prompt = f"""Ты - опытный HR-специалист Халык банка. 

# Кандидат: {name} {surname}
# Специализация: {specialization}
# Результат: {score}/{max_score} баллов (уровень {level})

# Детали ответов:
# {answers_text}

# Создай краткую персональную рекомендацию (2-3 предложения):
# - Отметь что освоено хорошо
# - Укажи конкретные пробелы (Junior/Middle/Senior вопросы)
# - Дай практический совет для развития

# Тон: дружелюбный, конкретный, мотивирующий."""

#                 # Вызываем Claude API
#                 message = claude_client.messages.create(
#                     model="claude-sonnet-4-20250514",
#                     max_tokens=300,
#                     messages=[{"role": "user", "content": prompt}]
#                 )
                
#                 recommendation = message.content[0].text.strip()
                
#                 # Сохраняем в БД
#                 await cur.execute(
#                     """INSERT INTO ai_recommendations (user_test_id, recommendation_text)
#                        VALUES (%s, %s)""",
#                     (user_test_id, recommendation)
#                 )
                
#                 return recommendation
                
#     except Exception as e:
#         print(f"Ошибка генерации рекомендации: {e}")
#         return "Рекомендация будет доступна позже."

# ===== LIFECYCLE =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    print("🚀 Starting application...")
    await init_db_pool()
    print("✅ Database pool ready")
    
    yield
    
    print("🔄 Shutting down...")
    await close_db_pool()

app = FastAPI(
    title="Halyk HR Forum",
    description="Система тестирования компетенций",
    lifespan=lifespan
)

# Static
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===== PYDANTIC MODELS =====
class UserRegister(BaseModel):
    name: str
    surname: str
    phone: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None

class SpecializationSelect(BaseModel):
    specialization_id: int

class TestStart(BaseModel):
    specialization_id: int

class AnswerSubmit(BaseModel):
    user_test_id: int
    question_id: int
    user_answer: int

class LoginRequest(BaseModel):
    phone: str

class SQLQuery(BaseModel):
    query: str

# ===== HTML PAGES =====
@app.get("/", response_class=HTMLResponse)
async def home():
    """Главная страница"""
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/specializations", response_class=HTMLResponse)
async def specializations_page():
    """Страница специализаций"""
    with open('templates/specializations.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    
@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """Страница прохождения теста"""
    with open('templates/test.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    
@app.get("/results", response_class=HTMLResponse)
async def results_page():
    """Страница результатов теста"""
    with open('templates/results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def verify_hr_password(credentials: HTTPBasicCredentials = Depends(security)):
    correct_password = os.getenv("HR_PASSWORD", "halyk2024")
    if credentials.password != correct_password:
        raise HTTPException(status_code=401, detail="Incorrect password", headers={"WWW-Authenticate": "Basic"})
    return credentials

@app.get("/hr", response_class=HTMLResponse)
async def hr_login_page(credentials: HTTPBasicCredentials = Depends(verify_hr_password)):
    with open('templates/hr_login.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/dashboard", response_class=HTMLResponse)
async def hr_dashboard_page(credentials: HTTPBasicCredentials = Depends(verify_hr_password)):
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/database", response_class=HTMLResponse)
async def hr_database_page(credentials: HTTPBasicCredentials = Depends(verify_hr_password)):
    with open('templates/hr_panel.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    return {"status": "ok", "service": "halyk-hr-forum"}

# ===== API: АУТЕНТИФИКАЦИЯ (БЕЗ ИЗМЕНЕНИЙ) =====
@app.post("/api/login")
async def login(request: LoginRequest):
    """Вход по номеру телефона"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name, surname FROM users WHERE phone = %s",
                    (request.phone,)
                )
                user = await cur.fetchone()
                
                if user:
                    token = create_access_token(user_id=user[0], phone=request.phone)
                    
                    return {
                        "status": "found",
                        "user_id": user[0],
                        "name": user[1],
                        "surname": user[2],
                        "token": token
                    }
                else:
                    return {"status": "not_found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/register")
@limiter.limit("3/day")
async def register_user(request: Request, user: UserRegister):
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
        
        token = create_access_token(user_id=user_id, phone=user.phone)
        
        return {
            "status": "success",
            "user_id": user_id,
            "token": token
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: PROFILES & SPECIALIZATIONS =====
@app.get("/api/profiles")
async def get_profiles():
    """Получить список профессий"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name, has_specializations FROM profiles ORDER BY id"
                )
                rows = await cur.fetchall()
        
        profiles = [
            {
                "id": row[0], 
                "name": row[1], 
                "has_specializations": row[2]
            }
            for row in rows
        ]
        
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/profiles/{profile_id}/specializations")
async def get_specializations(profile_id: int):
    """Получить специализации профессии"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT id, name FROM specializations 
                       WHERE profile_id = %s ORDER BY id""",
                    (profile_id,)
                )
                rows = await cur.fetchall()
        
        specializations = [
            {"id": row[0], "name": row[1]}
            for row in rows
        ]
        
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: ЗАЩИЩЕННЫЕ ENDPOINTS =====
@app.post("/api/select-specialization")
async def select_specialization(data: SpecializationSelect, current_user: dict = Depends(get_current_user)):
    """Пользователь выбирает специализацию"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO user_specialization_selections (user_id, specialization_id)
                       VALUES (%s, %s)
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    (user_id, data.specialization_id)
                )
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/my-specializations")
async def get_my_specializations(current_user: dict = Depends(get_current_user)):
    """Получить все специализации юзера с прогрессом"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT 
                        s.id,
                        s.name,
                        p.name as profile_name,
                        ut.id as user_test_id,
                        ut.score,
                        ut.max_score,
                        ut.completed_at,
                        ut.started_at
                    FROM user_specialization_selections uss
                    JOIN specializations s ON s.id = uss.specialization_id
                    JOIN profiles p ON p.id = s.profile_id
                    LEFT JOIN user_specialization_tests ut ON ut.specialization_id = s.id AND ut.user_id = %s
                    WHERE uss.user_id = %s
                    ORDER BY uss.selected_at DESC
                """, (user_id, user_id))
                
                rows = await cur.fetchall()
        
        specializations = []
        for row in rows:
            status = "not_started"
            if row[7]:  # started_at
                if row[6]:  # completed_at
                    status = "completed"
                else:
                    status = "in_progress"
            
            specializations.append({
                "id": row[0],
                "name": row[1],
                "profile_name": row[2],
                "user_test_id": row[3],
                "score": row[4],
                "max_score": row[5],
                "status": status
            })
        
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-test")
async def start_test(data: TestStart, current_user: dict = Depends(get_current_user)):
    """Начать тест специализации"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Проверяем есть ли уже тест
                await cur.execute(
                    """SELECT id FROM user_specialization_tests 
                       WHERE user_id = %s AND specialization_id = %s""",
                    (user_id, data.specialization_id)
                )
                existing = await cur.fetchone()
                
                if existing:
                    user_test_id = existing[0]
                    print(f"✅ Existing test found: user_test_id={user_test_id}")
                else:
                    # Создаем новый тест
                    await cur.execute(
                        """INSERT INTO user_specialization_tests (user_id, specialization_id, max_score)
                           VALUES (%s, %s, 24) RETURNING id""",
                        (user_id, data.specialization_id)
                    )
                    user_test_id = (await cur.fetchone())[0]
                    print(f"🆕 Created new test: user_test_id={user_test_id}")
                    
                    # ⭐ ГЕНЕРИРУЕМ 8 ТЕМ
                    await generate_test_topics(user_test_id, data.specialization_id)
                    print(f"✅ Generated 8 topics for user_test_id={user_test_id}")
        
        return {"status": "success", "user_test_id": user_test_id}
    except Exception as e:
        print(f"❌ Error in start_test: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{user_test_id}/questions")
async def get_test_questions(user_test_id: int, current_user: dict = Depends(get_current_user)):
    """Получить вопросы для теста с группировкой по компетенциям"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Проверяем что тест принадлежит пользователю
                await cur.execute(
                    "SELECT user_id FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()
                
                if not test_data or test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                # Получаем вопросы с группировкой по компетенциям
                await cur.execute("""
                    SELECT 
                        c.id as competency_id,
                        c.name as competency_name,
                        q.id as question_id,
                        q.level,
                        q.question_text,
                        q.var_1,
                        q.var_2,
                        q.var_3,
                        q.var_4,
                        t.name as topic_name,
                        utt.topic_order,
                        ta.user_answer,
                        ta.is_correct
                    FROM user_test_topics utt
                    JOIN topics t ON t.id = utt.topic_id
                    JOIN competencies c ON c.id = utt.competency_id
                    JOIN questions q ON q.topic_id = t.id
                    LEFT JOIN test_answers ta ON ta.question_id = q.id AND ta.user_test_id = utt.user_test_id
                    WHERE utt.user_test_id = %s
                    ORDER BY utt.topic_order, 
                             CASE q.level 
                                WHEN 'Junior' THEN 1 
                                WHEN 'Middle' THEN 2 
                                WHEN 'Senior' THEN 3 
                             END
                """, (user_test_id,))
                
                rows = await cur.fetchall()
        
        # Группируем по компетенциям
        competencies_dict = {}
        all_questions = []
        
        for row in rows:
            comp_id = row[0]
            
            if comp_id not in competencies_dict:
                competencies_dict[comp_id] = {
                    "id": comp_id,
                    "name": row[1],
                    "questions": []
                }
            
            question = {
                "question_id": row[2],
                "level": row[3],
                "question_text": row[4],
                "options": [row[5], row[6], row[7], row[8]],
                "topic_name": row[9],
                "is_answered": row[11] is not None,
                "user_answer": row[11],
                "is_correct": row[12]
            }
            
            competencies_dict[comp_id]["questions"].append(question)
            all_questions.append(question)
        
        # Получаем прогресс
        progress = await get_test_progress(user_test_id)
        
        return {
            "status": "success",
            "questions": all_questions,
            "competencies": list(competencies_dict.values()),
            "progress": progress
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-answer")
async def submit_answer(data: AnswerSubmit, current_user: dict = Depends(get_current_user)):
    """Отправить ответ на вопрос"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Проверяем что тест принадлежит пользователю
                await cur.execute(
                    "SELECT user_id, current_question_number FROM user_specialization_tests WHERE id = %s",
                    (data.user_test_id,)
                )
                test_user = await cur.fetchone()
                
                if not test_user or test_user[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                # Получаем правильный ответ
                await cur.execute(
                    "SELECT correct_answer FROM questions WHERE id = %s",
                    (data.question_id,)
                )
                correct_answer = (await cur.fetchone())[0]
                
                is_correct = (data.user_answer == correct_answer)
                
                # Сохраняем ответ (ON CONFLICT - если уже отвечал)
                await cur.execute(
                    """INSERT INTO test_answers 
                       (user_test_id, question_id, user_answer, is_correct)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (user_test_id, question_id) DO NOTHING""",
                    (data.user_test_id, data.question_id, data.user_answer, is_correct)
                )
                
                # Обновляем current_question_number
                current_q = test_user[1]
                await cur.execute(
                    """UPDATE user_specialization_tests 
                       SET current_question_number = %s
                       WHERE id = %s""",
                    (current_q + 1, data.user_test_id)
                )
        
        return {"status": "success", "is_correct": is_correct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complete-test/{user_test_id}")
async def complete_test(user_test_id: int, current_user: dict = Depends(get_current_user)):
    """Завершить тест и подсчитать результат"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Проверяем что тест принадлежит пользователю
                await cur.execute(
                    "SELECT user_id, completed_at, score FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()
                
                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                # Если тест уже завершен
                if test_data[1] is not None:
                    await cur.execute(
                        "SELECT recommendation_text FROM ai_recommendations WHERE user_test_id = %s",
                        (user_test_id,)
                    )
                    rec_row = await cur.fetchone()
                    recommendation = rec_row[0] if rec_row else None
                    
                    score = test_data[2]
                    percentage = (score / 24) * 100
                    if percentage >= 80:
                        level = "Senior"
                    elif percentage >= 50:
                        level = "Middle"
                    else:
                        level = "Junior"
                    
                    return {
                        "status": "already_completed",
                        "score": score,
                        "max_score": 24,
                        "level": level,
                        "recommendation": recommendation
                    }
                
                # Подсчитываем баллы
                await cur.execute(
                    """SELECT COUNT(*) FROM test_answers 
                       WHERE user_test_id = %s AND is_correct = true""",
                    (user_test_id,)
                )
                score = (await cur.fetchone())[0]
                
                # Обновляем user_specialization_tests
                await cur.execute(
                    """UPDATE user_specialization_tests 
                       SET score = %s, completed_at = NOW()
                       WHERE id = %s""",
                    (score, user_test_id)
                )
        
        # Генерируем AI рекомендацию
        recommendation = await generate_ai_recommendation(user_test_id)
        
        # Определяем уровень
        percentage = (score / 24) * 100
        if percentage >= 80:
            level = "Senior"
        elif percentage >= 50:
            level = "Middle"
        else:
            level = "Junior"
        
        return {
            "status": "success",
            "score": score,
            "max_score": 24,
            "level": level,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/results/{user_test_id}")
async def get_results(user_test_id: int, current_user: dict = Depends(get_current_user)):
    """Получить результаты теста"""
    user_id = current_user["user_id"]
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT 
                        ut.user_id,
                        ut.score,
                        ut.max_score,
                        ut.completed_at,
                        s.name as specialization_name,
                        ar.recommendation_text
                    FROM user_specialization_tests ut
                    JOIN specializations s ON s.id = ut.specialization_id
                    LEFT JOIN ai_recommendations ar ON ar.user_test_id = ut.id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                row = await cur.fetchone()
                
                if not row:
                    raise HTTPException(status_code=404, detail="Test not found")
                
                if row[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                score = row[1]
                max_score = row[2]
                percentage = (score / max_score) * 100
                
                if percentage >= 80:
                    level = "Senior"
                elif percentage >= 50:
                    level = "Middle"
                else:
                    level = "Junior"
        
        return {
            "status": "success",
            "score": score,
            "max_score": max_score,
            "level": level,
            "specialization_name": row[4],
            "recommendation": row[5]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Статистика для публичного дашборда"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Всего уникальных пользователей
                await cur.execute("SELECT COUNT(DISTINCT id) FROM users")
                total_users = (await cur.fetchone())[0]
                
                # Уникальные пользователи с хотя бы 1 завершённым тестом
                await cur.execute("""
                    SELECT COUNT(DISTINCT user_id) 
                    FROM user_specialization_tests 
                    WHERE completed_at IS NOT NULL
                """)
                completed_users = (await cur.fetchone())[0]
                
                # Уникальные пользователи, ответившие >= 10 вопросов но не завершившие
                # И НЕ завершившие НИКАКИЕ другие тесты
                await cur.execute("""
                    SELECT COUNT(DISTINCT ut.user_id)
                    FROM user_specialization_tests ut
                    WHERE ut.completed_at IS NULL
                    AND EXISTS (
                        SELECT 1 
                        FROM test_answers ta 
                        WHERE ta.user_test_id = ut.id
                        GROUP BY ta.user_test_id
                        HAVING COUNT(*) >= 10
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM user_specialization_tests ut2
                        WHERE ut2.user_id = ut.user_id
                        AND ut2.completed_at IS NOT NULL
                    )
                """)
                in_progress = (await cur.fetchone())[0]
                
                # Распределение по уровням
                await cur.execute("""
                    SELECT 
                        CASE 
                            WHEN (score::float / max_score * 100) >= 80 THEN 'Senior'
                            WHEN (score::float / max_score * 100) >= 50 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                levels_data = await cur.fetchall()
                levels = {row[0]: row[1] for row in levels_data}
                
                # Топ-20 лучших результатов
                await cur.execute("""
                    SELECT 
                        u.name,
                        u.surname,
                        ut.score,
                        ut.max_score,
                        s.name as specialization
                    FROM user_specialization_tests ut
                    JOIN users u ON u.id = ut.user_id
                    JOIN specializations s ON s.id = ut.specialization_id
                    WHERE ut.completed_at IS NOT NULL
                    ORDER BY ut.score DESC, ut.completed_at ASC
                    LIMIT 20
                """)
                top_results_data = await cur.fetchall()
                top_results = [
                    {
                        "name": f"{row[0]} {row[1]}",
                        "score": row[2],
                        "max_score": row[3],
                        "specialization": row[4]
                    }
                    for row in top_results_data
                ]
                
                # Все специализации по популярности
                await cur.execute("""
                    SELECT 
                        s.name,
                        COUNT(ut.id) as test_count
                    FROM specializations s
                    LEFT JOIN user_specialization_tests ut ON ut.specialization_id = s.id 
                        AND ut.completed_at IS NOT NULL
                    GROUP BY s.id, s.name
                    ORDER BY test_count DESC
                """)
                specializations_data = await cur.fetchall()
                top_specializations = [
                    {"name": row[0], "count": row[1]}
                    for row in specializations_data
                ]
                
                return {
                    "users": {
                        "total": total_users,
                        "completed": completed_users,
                        "in_progress": in_progress
                    },
                    "levels": {
                        "Senior": levels.get("Senior", 0),
                        "Middle": levels.get("Middle", 0),
                        "Junior": levels.get("Junior", 0)
                    },
                    "top_results": top_results,
                    "top_specializations": top_specializations
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== API: HR PANEL =====

HR_PASSWORD = "159753"  # Простой пароль для HR

@app.post("/api/hr/login")
async def hr_login(password: str):
    """Вход в HR панель"""
    if password == HR_PASSWORD:
        # Создаём простой токен
        token = create_access_token(user_id=0, phone="hr_admin")
        return {"status": "success", "token": token}
    else:
        raise HTTPException(status_code=401, detail="Неверный пароль")

@app.get("/api/hr/tables")
async def get_hr_tables():
    """Получить список таблиц с первыми 5 строками"""
    tables = [
        "users",
        "profiles", 
        "specializations",
        "competencies",
        "topics",
        "questions",
        "user_specialization_selections",
        "user_specialization_tests",
        "user_test_topics",
        "test_answers",
        "ai_recommendations"
    ]
    
    result = {}
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for table in tables:
                    # Получаем первые 5 строк
                    await cur.execute(f"SELECT * FROM {table} LIMIT 5")
                    rows = await cur.fetchall()
                    
                    # Получаем названия колонок
                    await cur.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                        ORDER BY ordinal_position
                    """)
                    columns = [row[0] for row in await cur.fetchall()]
                    
                    result[table] = {
                        "columns": columns,
                        "rows": rows
                    }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hr/sql")
async def execute_hr_sql(data: SQLQuery):
    """Выполнить SQL запрос (только SELECT)"""
    query = data.query
    # Проверка безопасности - только SELECT
    query_lower = query.lower().strip()
    if not query_lower.startswith("select"):
        raise HTTPException(status_code=400, detail="Только SELECT запросы разрешены")
    
    # Запрещённые слова
    forbidden = ["insert", "update", "delete", "drop", "create", "alter", "truncate"]
    if any(word in query_lower for word in forbidden):
        raise HTTPException(status_code=400, detail="Запрещённые команды обнаружены")
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                rows = await cur.fetchall()
                
                # Получаем названия колонок из курсора
                columns = [desc[0] for desc in cur.description] if cur.description else []
                
                return {
                    "columns": columns,
                    "rows": rows,
                    "count": len(rows)
                }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка SQL: {str(e)}")


@app.get("/hr/menu", response_class=HTMLResponse)
async def hr_menu_page():
    """HR панель - меню выбора"""
    with open('templates/hr_menu.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())
    

# Monitoring
# ===== ДОБАВЬ В main.py =====

# 1. Импорты (в начало файла)
import psutil
import time
import statistics
from datetime import datetime, timedelta
from collections import defaultdict, deque

# 2. Глобальные переменные для мониторинга (после импортов)
monitoring_data = {
    "requests": deque(maxlen=1000),  # Последние 1000 запросов
    "active_users": {},  # {user_id: last_activity_timestamp}
    "start_time": time.time()
}

# 3. Middleware (после создания app)
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    
    # Извлекаем user_id из токена если есть
    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        user_data = verify_token(token)
        if user_data:
            user_id = user_data.get("user_id")
            # Обновляем активность пользователя
            monitoring_data["active_users"][user_id] = datetime.now()
    
    try:
        response = await call_next(request)
        
        # Записываем время ответа
        response_time = (time.time() - start_time) * 1000  # в миллисекундах
        
        monitoring_data["requests"].append({
            "endpoint": request.url.path,
            "method": request.method,
            "response_time": response_time,
            "timestamp": datetime.now(),
            "user_id": user_id
        })
        
        return response
    except Exception as e:
        raise

# 4. HTML роут
@app.get("/hr/monitoring", response_class=HTMLResponse)
async def hr_monitoring_page(credentials: HTTPBasicCredentials = Depends(verify_hr_password)):
    with open('templates/monitoring.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# 5. API эндпоинты

def calculate_percentiles(values):
    """Вычисляет медиану и 95% перцентиль"""
    if not values:
        return {"median": 0, "p95": 0}
    
    sorted_values = sorted(values)
    median = statistics.median(sorted_values)
    
    # 95% перцентиль
    index_95 = int(len(sorted_values) * 0.95)
    p95 = sorted_values[min(index_95, len(sorted_values) - 1)]
    
    return {"median": round(median, 2), "p95": round(p95, 2)}

@app.get("/api/hr/monitoring/overview")
async def get_monitoring_overview():
    """Общая информация: онлайн, CPU, RAM"""
    try:
        # Онлайн пользователи (активность < 5 минут)
        now = datetime.now()
        online_threshold = now - timedelta(minutes=5)
        online_count = sum(
            1 for last_activity in monitoring_data["active_users"].values()
            if last_activity > online_threshold
        )
        
        # CPU и RAM
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        return {
            "status": "success",
            "online_users": online_count,
            "cpu_percent": round(cpu_percent, 1),
            "ram_percent": round(memory.percent, 1),
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/monitoring/realtime")
async def get_realtime_metrics():
    """Метрики за последние 10 секунд для графика"""
    try:
        now = datetime.now()
        threshold = now - timedelta(seconds=10)
        
        # Фильтруем запросы за последние 10 сек
        recent_requests = [
            req for req in monitoring_data["requests"]
            if req["timestamp"] > threshold
        ]
        
        if not recent_requests:
            return {
                "status": "success",
                "median": 0,
                "p95": 0,
                "count": 0,
                "timestamp": now.isoformat()
            }
        
        # Вычисляем перцентили
        response_times = [req["response_time"] for req in recent_requests]
        percentiles = calculate_percentiles(response_times)
        
        return {
            "status": "success",
            "median": percentiles["median"],
            "p95": percentiles["p95"],
            "count": len(recent_requests),
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/monitoring/operations")
async def get_operations_stats():
    """Статистика по типам операций за 5 минут"""
    try:
        now = datetime.now()
        threshold = now - timedelta(minutes=5)
        
        # Фильтруем запросы за последние 5 мин
        recent_requests = [
            req for req in monitoring_data["requests"]
            if req["timestamp"] > threshold
        ]
        
        # Группируем по типам операций
        operations = {
            "submit_answer": {
                "name": "💬 Ответы на вопросы",
                "endpoint": "/api/submit-answer",
                "times": []
            },
            "register": {
                "name": "📝 Регистрация",
                "endpoint": "/api/register",
                "times": []
            },
            "start_test": {
                "name": "▶️ Старт теста",
                "endpoint": "/api/start-test",
                "times": []
            },
            "get_questions": {
                "name": "📄 Получение вопросов",
                "endpoint_pattern": "/api/test/",
                "times": []
            }
        }
        
        # Собираем времена по операциям
        for req in recent_requests:
            endpoint = req["endpoint"]
            
            if endpoint == "/api/submit-answer":
                operations["submit_answer"]["times"].append(req["response_time"])
            elif endpoint == "/api/register":
                operations["register"]["times"].append(req["response_time"])
            elif endpoint == "/api/start-test":
                operations["start_test"]["times"].append(req["response_time"])
            elif "/api/test/" in endpoint and "/questions" in endpoint:
                operations["get_questions"]["times"].append(req["response_time"])
        
        # Вычисляем статистику
        result = []
        for op_key, op_data in operations.items():
            if op_data["times"]:
                percentiles = calculate_percentiles(op_data["times"])
                result.append({
                    "name": op_data["name"],
                    "median": percentiles["median"],
                    "p95": percentiles["p95"],
                    "count": len(op_data["times"])
                })
            else:
                result.append({
                    "name": op_data["name"],
                    "median": 0,
                    "p95": 0,
                    "count": 0
                })
        
        return {
            "status": "success",
            "operations": result,
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)