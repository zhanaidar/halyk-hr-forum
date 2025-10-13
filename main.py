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

# ===== AI РЕКОМЕНДАЦИИ (БЕЗ ИЗМЕНЕНИЙ) =====
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
                
                # Получаем детали ответов С ТЕМАМИ
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
                percentage = (score / max_score) * 100
                if percentage >= 80:
                    level = "Senior"
                elif percentage >= 50:
                    level = "Middle"
                else:
                    level = "Junior"
                
                # Промпт для Claude
                prompt = f"""Ты - опытный HR-специалист Халык банка. 

Кандидат: {name} {surname}
Специализация: {specialization}
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
            "questions": all_questions,  # Плоский список для фронта
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)