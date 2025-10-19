from fastapi import FastAPI, Request, HTTPException, Header, Depends, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
import sys
import os

# Мониторинг
import psutil
import time
import statistics
from datetime import datetime, timedelta
from collections import deque

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

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# =====================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ МОНИТОРИНГА
# =====================================================
monitoring_data = {
    "requests": deque(maxlen=1000),
    "active_users": {},
    "start_time": time.time()
}

# =====================================================
# PYDANTIC MODELS
# =====================================================
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

# =====================================================
# LIFECYCLE
# =====================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting application...")
    await init_db_pool()
    print("✅ Database pool ready")
    yield
    print("🔄 Shutting down...")
    await close_db_pool()

# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI(
    title="Halyk HR Forum",
    description="Система тестирования компетенций",
    lifespan=lifespan
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Rate limiter
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# =====================================================
# MIDDLEWARE - МОНИТОРИНГ
# =====================================================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    
    # Извлекаем user_id из токена
    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        user_data = verify_token(token)
        if user_data:
            user_id = user_data.get("user_id")
            monitoring_data["active_users"][user_id] = datetime.now()
    
    try:
        response = await call_next(request)
        response_time = (time.time() - start_time) * 1000
        
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

# =====================================================
# DEPENDENCY - AUTH
# =====================================================
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_data

# =====================================================
# AI РЕКОМЕНДАЦИИ
# =====================================================
async def generate_ai_recommendation(user_test_id: int):
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT ut.score, ut.max_score, s.name, u.name, u.surname
                    FROM user_specialization_tests ut
                    JOIN specializations s ON s.id = ut.specialization_id
                    JOIN users u ON u.id = ut.user_id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                test_data = await cur.fetchone()
                if not test_data:
                    return None
                
                score, max_score, specialization, name, surname = test_data
                percentage = (score / max_score) * 100
                
                if percentage >= 80:
                    level = "Senior"
                elif percentage >= 50:
                    level = "Middle"
                else:
                    level = "Junior"
                
                recommendation = f"Рекомендация: {name}, вы показали {level} уровень в области \"{specialization}\" ({score}/{max_score} баллов). Продолжайте развиваться в выбранном направлении и обращайте внимание на практические навыки."
                
                await cur.execute(
                    "INSERT INTO ai_recommendations (user_test_id, recommendation_text) VALUES (%s, %s)",
                    (user_test_id, recommendation)
                )
                
                return recommendation
    except Exception as e:
        print(f"Ошибка генерации рекомендации: {e}")
        return "Рекомендация будет доступна позже."

# =====================================================
# HTML ROUTES - PUBLIC
# =====================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/specializations", response_class=HTMLResponse)
async def specializations_page():
    with open('templates/specializations.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    with open('templates/test.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/results", response_class=HTMLResponse)
async def results_page():
    with open('templates/results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    return {"status": "ok", "service": "halyk-hr-forum"}

# =====================================================
# HTML ROUTES - HR PANEL
# =====================================================
# ===== ДОБАВЬ/ЗАМЕНИ ЭТИ ЧАСТИ В main.py =====

from fastapi import Cookie
from fastapi.responses import RedirectResponse

# =====================================================
# DEPENDENCY - HR AUTH (НОВОЕ!)
# =====================================================
async def verify_hr_cookie(hr_token: Optional[str] = Cookie(None)):
    """Проверяет HR токен из cookie"""
    if not hr_token:
        return None
    
    # Проверяем токен
    user_data = verify_token(hr_token)
    if user_data and user_data.get("phone") == "hr_admin":
        return user_data
    return None

# =====================================================
# HTML ROUTES - HR PANEL (ОБНОВЛЕННЫЕ!)
# =====================================================
@app.get("/hr", response_class=HTMLResponse)
async def hr_login_page():
    """Страница логина HR"""
    with open('templates/hr_login.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/menu", response_class=HTMLResponse)
async def hr_menu_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR меню - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)
    
    with open('templates/hr_menu.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/dashboard", response_class=HTMLResponse)
async def hr_dashboard_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR дашборд - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)
    
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/database", response_class=HTMLResponse)
async def hr_database_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR база данных - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)
    
    with open('templates/hr_panel.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/monitoring", response_class=HTMLResponse)
async def hr_monitoring_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR мониторинг - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)
    
    with open('templates/hr_monitoring.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# =====================================================
# API - АУТЕНТИФИКАЦИЯ ПОЛЬЗОВАТЕЛЕЙ
# =====================================================
@app.post("/api/login")
async def login(request: LoginRequest):
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
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO users (name, surname, phone, company, job_title) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (user.name, user.surname, user.phone, user.company, user.job_title)
                )
                user_id = (await cur.fetchone())[0]
        
        token = create_access_token(user_id=user_id, phone=user.phone)
        return {"status": "success", "user_id": user_id, "token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - PROFILES & SPECIALIZATIONS
# =====================================================
@app.get("/api/profiles")
async def get_profiles():
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, name, has_specializations FROM profiles ORDER BY id")
                rows = await cur.fetchall()
        
        profiles = [{"id": row[0], "name": row[1], "has_specializations": row[2]} for row in rows]
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/profiles/{profile_id}/specializations")
async def get_specializations(profile_id: int):
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name FROM specializations WHERE profile_id = %s ORDER BY id",
                    (profile_id,)
                )
                rows = await cur.fetchall()
        
        specializations = [{"id": row[0], "name": row[1]} for row in rows]
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - ТЕСТИРОВАНИЕ (ЗАЩИЩЕННЫЕ)
# =====================================================
@app.post("/api/select-specialization")
async def select_specialization(data: SpecializationSelect, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO user_specialization_selections (user_id, specialization_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id",
                    (user_id, data.specialization_id)
                )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/my-specializations")
async def get_my_specializations(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT s.id, s.name, p.name, ut.id, ut.score, ut.max_score, ut.completed_at, ut.started_at
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
            if row[7]:
                status = "completed" if row[6] else "in_progress"
            
            specializations.append({
                "id": row[0], "name": row[1], "profile_name": row[2],
                "user_test_id": row[3], "score": row[4], "max_score": row[5], "status": status
            })
        
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-test")
async def start_test(data: TestStart, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM user_specialization_tests WHERE user_id = %s AND specialization_id = %s",
                    (user_id, data.specialization_id)
                )
                existing = await cur.fetchone()
                
                if existing:
                    user_test_id = existing[0]
                else:
                    await cur.execute(
                        "INSERT INTO user_specialization_tests (user_id, specialization_id, max_score) VALUES (%s, %s, 24) RETURNING id",
                        (user_id, data.specialization_id)
                    )
                    user_test_id = (await cur.fetchone())[0]
                    await generate_test_topics(user_test_id, data.specialization_id)
        
        return {"status": "success", "user_test_id": user_test_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{user_test_id}/questions")
async def get_test_questions(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT user_id FROM user_specialization_tests WHERE id = %s", (user_test_id,))
                test_data = await cur.fetchone()
                
                if not test_data or test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                await cur.execute("""
                    SELECT c.id, c.name, q.id, q.level, q.question_text, q.var_1, q.var_2, q.var_3, q.var_4,
                           t.name, utt.topic_order, ta.user_answer, ta.is_correct
                    FROM user_test_topics utt
                    JOIN topics t ON t.id = utt.topic_id
                    JOIN competencies c ON c.id = utt.competency_id
                    JOIN questions q ON q.topic_id = t.id
                    LEFT JOIN test_answers ta ON ta.question_id = q.id AND ta.user_test_id = utt.user_test_id
                    WHERE utt.user_test_id = %s
                    ORDER BY utt.topic_order, CASE q.level WHEN 'Junior' THEN 1 WHEN 'Middle' THEN 2 WHEN 'Senior' THEN 3 END
                """, (user_test_id,))
                rows = await cur.fetchall()
        
        competencies_dict = {}
        all_questions = []
        
        for row in rows:
            comp_id = row[0]
            if comp_id not in competencies_dict:
                competencies_dict[comp_id] = {"id": comp_id, "name": row[1], "questions": []}
            
            question = {
                "question_id": row[2], "level": row[3], "question_text": row[4],
                "options": [row[5], row[6], row[7], row[8]], "topic_name": row[9],
                "is_answered": row[11] is not None, "user_answer": row[11], "is_correct": row[12]
            }
            
            competencies_dict[comp_id]["questions"].append(question)
            all_questions.append(question)
        
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
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, current_question_number FROM user_specialization_tests WHERE id = %s",
                    (data.user_test_id,)
                )
                test_user = await cur.fetchone()
                
                if not test_user or test_user[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                await cur.execute("SELECT correct_answer FROM questions WHERE id = %s", (data.question_id,))
                correct_answer = (await cur.fetchone())[0]
                is_correct = (data.user_answer == correct_answer)
                
                await cur.execute(
                    "INSERT INTO test_answers (user_test_id, question_id, user_answer, is_correct) VALUES (%s, %s, %s, %s) ON CONFLICT (user_test_id, question_id) DO NOTHING",
                    (data.user_test_id, data.question_id, data.user_answer, is_correct)
                )
                
                await cur.execute(
                    "UPDATE user_specialization_tests SET current_question_number = %s WHERE id = %s",
                    (test_user[1] + 1, data.user_test_id)
                )
        
        return {"status": "success", "is_correct": is_correct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complete-test/{user_test_id}")
async def complete_test(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, completed_at, score FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()
                
                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                if test_data[1] is not None:
                    await cur.execute(
                        "SELECT recommendation_text FROM ai_recommendations WHERE user_test_id = %s",
                        (user_test_id,)
                    )
                    rec_row = await cur.fetchone()
                    recommendation = rec_row[0] if rec_row else None
                    
                    score = test_data[2]
                    percentage = (score / 24) * 100
                    level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
                    
                    return {
                        "status": "already_completed",
                        "score": score, "max_score": 24, "level": level,
                        "recommendation": recommendation
                    }
                
                await cur.execute(
                    "SELECT COUNT(*) FROM test_answers WHERE user_test_id = %s AND is_correct = true",
                    (user_test_id,)
                )
                score = (await cur.fetchone())[0]
                
                await cur.execute(
                    "UPDATE user_specialization_tests SET score = %s, completed_at = NOW() WHERE id = %s",
                    (score, user_test_id)
                )
        
        recommendation = await generate_ai_recommendation(user_test_id)
        percentage = (score / 24) * 100
        level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
        
        return {
            "status": "success",
            "score": score, "max_score": 24, "level": level,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/results/{user_test_id}")
async def get_results(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT ut.user_id, ut.score, ut.max_score, ut.completed_at, s.name, ar.recommendation_text
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
                
                score, max_score = row[1], row[2]
                percentage = (score / max_score) * 100
                level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
        
        return {
            "status": "success",
            "score": score, "max_score": max_score, "level": level,
            "specialization_name": row[4], "recommendation": row[5]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - ДАШБОРД
# =====================================================
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(DISTINCT id) FROM users")
                total_users = (await cur.fetchone())[0]
                
                await cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_specialization_tests WHERE completed_at IS NOT NULL")
                completed_users = (await cur.fetchone())[0]
                
                await cur.execute("""
                    SELECT COUNT(DISTINCT ut.user_id)
                    FROM user_specialization_tests ut
                    WHERE ut.completed_at IS NULL
                    AND EXISTS (SELECT 1 FROM test_answers ta WHERE ta.user_test_id = ut.id GROUP BY ta.user_test_id HAVING COUNT(*) >= 10)
                    AND NOT EXISTS (SELECT 1 FROM user_specialization_tests ut2 WHERE ut2.user_id = ut.user_id AND ut2.completed_at IS NOT NULL)
                """)
                in_progress = (await cur.fetchone())[0]
                
                await cur.execute("""
                    SELECT 
                        CASE WHEN (score::float / max_score * 100) >= 80 THEN 'Senior'
                             WHEN (score::float / max_score * 100) >= 50 THEN 'Middle'
                             ELSE 'Junior' END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                levels_data = await cur.fetchall()
                levels = {row[0]: row[1] for row in levels_data}
                
                await cur.execute("""
                    SELECT u.name, u.surname, ut.score, ut.max_score, s.name
                    FROM user_specialization_tests ut
                    JOIN users u ON u.id = ut.user_id
                    JOIN specializations s ON s.id = ut.specialization_id
                    WHERE ut.completed_at IS NOT NULL
                    ORDER BY ut.score DESC, ut.completed_at ASC
                    LIMIT 20
                """)
                top_results_data = await cur.fetchall()
                top_results = [
                    {"name": f"{row[0]} {row[1]}", "score": row[2], "max_score": row[3], "specialization": row[4]}
                    for row in top_results_data
                ]
                
                await cur.execute("""
                    SELECT s.name, COUNT(ut.id) as test_count
                    FROM specializations s
                    LEFT JOIN user_specialization_tests ut ON ut.specialization_id = s.id AND ut.completed_at IS NOT NULL
                    GROUP BY s.id, s.name
                    ORDER BY test_count DESC
                """)
                specializations_data = await cur.fetchall()
                top_specializations = [{"name": row[0], "count": row[1]} for row in specializations_data]
                
                return {
                    "users": {"total": total_users, "completed": completed_users, "in_progress": in_progress},
                    "levels": {"Senior": levels.get("Senior", 0), "Middle": levels.get("Middle", 0), "Junior": levels.get("Junior", 0)},
                    "top_results": top_results,
                    "top_specializations": top_specializations
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - HR PANEL
# =====================================================
HR_PASSWORD = "159753"

# =====================================================
# API - HR LOGIN (ОБНОВЛЕННЫЙ!)
# =====================================================
@app.post("/api/hr/login")
async def hr_login(password: str, response: Response):
    """Вход в HR панель - устанавливает cookie"""
    if password == HR_PASSWORD:
        token = create_access_token(user_id=0, phone="hr_admin")
        
        # Устанавливаем httpOnly cookie (защита от XSS)
        response.set_cookie(
            key="hr_token",
            value=token,
            httponly=True,  # Нельзя прочитать через JavaScript
            secure=True,    # Только через HTTPS
            samesite="lax", # Защита от CSRF
            max_age=86400   # 24 часа
        )
        
        return {"status": "success"}
    else:
        raise HTTPException(status_code=401, detail="Неверный пароль")

@app.post("/api/hr/logout")
async def hr_logout(response: Response):
    """Выход из HR панели - удаляет cookie"""
    response.delete_cookie(key="hr_token")
    return {"status": "success"}

@app.get("/api/hr/tables")
async def get_hr_tables():
    tables = [
        "users", "profiles", "specializations", "competencies", "topics", "questions",
        "user_specialization_selections", "user_specialization_tests", "user_test_topics",
        "test_answers", "ai_recommendations"
    ]
    
    result = {}
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for table in tables:
                    await cur.execute(f"SELECT * FROM {table} LIMIT 5")
                    rows = await cur.fetchall()
                    
                    await cur.execute(f"""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = '{table}' ORDER BY ordinal_position
                    """)
                    columns = [row[0] for row in await cur.fetchall()]
                    result[table] = {"columns": columns, "rows": rows}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hr/sql")
async def execute_hr_sql(data: SQLQuery):
    query = data.query.lower().strip()
    if not query.startswith("select"):
        raise HTTPException(status_code=400, detail="Только SELECT запросы разрешены")
    
    forbidden = ["insert", "update", "delete", "drop", "create", "alter", "truncate"]
    if any(word in query for word in forbidden):
        raise HTTPException(status_code=400, detail="Запрещённые команды обнаружены")
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(data.query)
                rows = await cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                return {"columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка SQL: {str(e)}")

# =====================================================
# API - МОНИТОРИНГ
# =====================================================
def calculate_percentiles(values):
    if not values:
        return {"median": 0, "p95": 0}
    sorted_values = sorted(values)
    median = statistics.median(sorted_values)
    index_95 = int(len(sorted_values) * 0.95)
    p95 = sorted_values[min(index_95, len(sorted_values) - 1)]
    return {"median": round(median, 2), "p95": round(p95, 2)}

@app.get("/api/hr/monitoring/overview")
async def get_monitoring_overview():
    try:
        now = datetime.now()
        online_threshold = now - timedelta(minutes=5)
        online_count = sum(
            1 for last_activity in monitoring_data["active_users"].values()
            if last_activity > online_threshold
        )
        
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
    try:
        now = datetime.now()
        threshold = now - timedelta(seconds=10)
        
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
    try:
        now = datetime.now()
        threshold = now - timedelta(minutes=5)
        
        recent_requests = [
            req for req in monitoring_data["requests"]
            if req["timestamp"] > threshold
        ]
        
        operations = {
            "submit_answer": {"name": "💬 Ответы на вопросы", "endpoint": "/api/submit-answer", "times": []},
            "register": {"name": "📝 Регистрация", "endpoint": "/api/register", "times": []},
            "start_test": {"name": "▶️ Старт теста", "endpoint": "/api/start-test", "times": []},
            "get_questions": {"name": "📄 Получение вопросов", "endpoint_pattern": "/api/test/", "times": []}
        }
        
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

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)