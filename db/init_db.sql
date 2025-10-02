-- Drop tables if exist (для чистого старта)
DROP TABLE IF EXISTS ai_recommendations CASCADE;
DROP TABLE IF EXISTS test_answers CASCADE;
DROP TABLE IF EXISTS user_tests CASCADE;
DROP TABLE IF EXISTS user_profile_selections CASCADE;
DROP TABLE IF EXISTS questions CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS competencies CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 1. Профили (профессии)
CREATE TABLE profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    specialization VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Компетенции
CREATE TABLE competencies (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. Темы внутри компетенций
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER REFERENCES competencies(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. Вопросы
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

-- 5. Пользователи
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    surname VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    company VARCHAR(255),
    job_title VARCHAR(255),
    registered_at TIMESTAMP DEFAULT NOW()
);

-- 6. Выбор профессии пользователем
CREATE TABLE user_profile_selections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW()
);

-- 7. Прохождение компетенций пользователями
CREATE TABLE user_tests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    competency_id INTEGER REFERENCES competencies(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    score INTEGER DEFAULT 0, -- Баллы (0-6)
    max_score INTEGER DEFAULT 6, -- Максимум баллов
    UNIQUE(user_id, competency_id) -- Один тест на компетенцию
);

-- 8. Ответы пользователей на вопросы
CREATE TABLE test_answers (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER REFERENCES user_tests(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    user_answer INTEGER NOT NULL, -- 1, 2, 3, или 4
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMP DEFAULT NOW()
);

-- 9. AI рекомендации (привязаны к конкретной попытке)
CREATE TABLE ai_recommendations (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER REFERENCES user_tests(id) ON DELETE CASCADE,
    recommendation_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX idx_competencies_profile ON competencies(profile_id);
CREATE INDEX idx_topics_competency ON topics(competency_id);
CREATE INDEX idx_questions_topic ON questions(topic_id);
CREATE INDEX idx_user_profile_selections_user ON user_profile_selections(user_id);
CREATE INDEX idx_user_tests_user ON user_tests(user_id);
CREATE INDEX idx_test_answers_user_test ON test_answers(user_test_id);
CREATE INDEX idx_ai_recommendations_user_test ON ai_recommendations(user_test_id);

-- Тестовый пользователь
INSERT INTO users (name, surname, phone, company, job_title) 
VALUES ('Жанайдар', 'Тестовый', '+77001234567', 'Халык банк', 'HR Manager');