-- ==========================================
-- HALYK HR FORUM - ФИНАЛЬНАЯ СТРУКТУРА БД
-- ==========================================

-- Удаляем старые таблицы
DROP TABLE IF EXISTS ai_recommendations CASCADE;
DROP TABLE IF EXISTS test_answers CASCADE;
DROP TABLE IF EXISTS user_test_topics CASCADE;
DROP TABLE IF EXISTS user_specialization_tests CASCADE;
DROP TABLE IF EXISTS user_specialization_selections CASCADE;
DROP TABLE IF EXISTS user_tests CASCADE;
DROP TABLE IF EXISTS user_profile_selections CASCADE;
DROP TABLE IF EXISTS questions CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS competencies CASCADE;
DROP TABLE IF EXISTS specializations CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ==========================================
-- 1. USERS (пользователи)
-- ==========================================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    surname VARCHAR(255) NOT NULL,
    phone VARCHAR(50) UNIQUE,
    company VARCHAR(255),
    job_title VARCHAR(255),
    registered_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 2. PROFILES (профессии)
-- ==========================================
CREATE TABLE profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    has_specializations BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 3. SPECIALIZATIONS (специализации)
-- ==========================================
CREATE TABLE specializations (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 4. COMPETENCIES (компетенции)
-- НЕ показываем юзеру, но используем для группировки
-- ==========================================
CREATE TABLE competencies (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER REFERENCES specializations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    importance INTEGER DEFAULT 50, -- Важность из [CORE 90%]
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 5. TOPICS (темы - 4 на компетенцию)
-- ==========================================
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER REFERENCES competencies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 6. QUESTIONS (вопросы - 3 на тему)
-- ==========================================
CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    level VARCHAR(50) NOT NULL, -- Junior, Middle, Senior
    question_text TEXT NOT NULL,
    var_1 TEXT NOT NULL,
    var_2 TEXT NOT NULL,
    var_3 TEXT NOT NULL,
    var_4 TEXT NOT NULL,
    correct_answer INTEGER NOT NULL, -- 1, 2, 3, или 4
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- 7. USER_SPECIALIZATION_SELECTIONS (выбор специализации)
-- ==========================================
CREATE TABLE user_specialization_selections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    specialization_id INTEGER REFERENCES specializations(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, specialization_id)
);

-- ==========================================
-- 8. USER_SPECIALIZATION_TESTS (тест по специализации)
-- ==========================================
CREATE TABLE user_specialization_tests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    specialization_id INTEGER REFERENCES specializations(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    current_question_number INTEGER DEFAULT 1, -- Текущий вопрос (1-24)
    score INTEGER DEFAULT 0,
    max_score INTEGER DEFAULT 24, -- 8 тем × 3 вопроса
    UNIQUE(user_id, specialization_id)
);

-- ==========================================
-- 9. USER_TEST_TOPICS (8 зафиксированных тем для юзера)
-- ==========================================
CREATE TABLE user_test_topics (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    competency_id INTEGER REFERENCES competencies(id) ON DELETE CASCADE,
    topic_order INTEGER NOT NULL, -- 1-8 (группируется по компетенциям)
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_test_id, topic_id),
    UNIQUE(user_test_id, topic_order)
);

-- ==========================================
-- 10. TEST_ANSWERS (ответы на вопросы)
-- ==========================================
CREATE TABLE test_answers (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    user_answer INTEGER NOT NULL, -- 1, 2, 3, или 4
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_test_id, question_id)
);

-- ==========================================
-- 11. AI_RECOMMENDATIONS (AI рекомендации)
-- ==========================================
CREATE TABLE ai_recommendations (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
    recommendation_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ==========================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- ==========================================
CREATE INDEX idx_specializations_profile ON specializations(profile_id);
CREATE INDEX idx_competencies_specialization ON competencies(specialization_id);
CREATE INDEX idx_competencies_importance ON competencies(importance DESC);
CREATE INDEX idx_topics_competency ON topics(competency_id);
CREATE INDEX idx_questions_topic ON questions(topic_id);
CREATE INDEX idx_user_selections_user ON user_specialization_selections(user_id);
CREATE INDEX idx_user_tests_user ON user_specialization_tests(user_id);
CREATE INDEX idx_user_tests_specialization ON user_specialization_tests(specialization_id);
CREATE INDEX idx_user_test_topics_test ON user_test_topics(user_test_id);
CREATE INDEX idx_user_test_topics_order ON user_test_topics(topic_order);
CREATE INDEX idx_test_answers_user_test ON test_answers(user_test_id);
CREATE INDEX idx_test_answers_question ON test_answers(question_id);
CREATE INDEX idx_ai_recommendations_user_test ON ai_recommendations(user_test_id);

-- ⭐ НОВЫЕ ИНДЕКСЫ ДЛЯ ОПТИМИЗАЦИИ (добавь эти 3 строки):
CREATE INDEX IF NOT EXISTS idx_questions_topic_level ON questions(topic_id, level);
CREATE INDEX IF NOT EXISTS idx_test_answers_test_question ON test_answers(user_test_id, question_id);
CREATE INDEX IF NOT EXISTS idx_user_test_topics_test_order ON user_test_topics(user_test_id, topic_order);

-- ==========================================
-- ТЕСТОВЫЕ ДАННЫЕ
-- ==========================================
INSERT INTO users (name, surname, phone, company, job_title) 
VALUES ('Иван', 'Тестовый', '+77001234567', 'Халык банк', 'HR Manager');