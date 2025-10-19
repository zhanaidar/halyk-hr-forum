from locust import HttpUser, task, between, SequentialTaskSet
import random

class UserJourney(SequentialTaskSet):
    """Последовательный сценарий: регистрация → тест → завершение"""
    
    def on_start(self):
        """Инициализация при старте юзера"""
        self.token = None
        self.user_test_id = None
        self.questions = []
        self.current_question_index = 0
    
    @task
    def register(self):
        """1. Регистрация"""
        random_id = random.randint(10000, 99999)
        response = self.client.post("/api/register", json={
            "name": f"User{random_id}",
            "surname": f"Test{random_id}",
            "phone": f"+7700{random_id}",
            "company": "Test Company",
            "job_title": "QA Tester"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("token")
            print(f"✅ Registered: User{random_id}")
        else:
            print(f"❌ Registration failed: {response.status_code}")
            self.interrupt()  # Останавливаем этого юзера
    
    @task
    def select_specialization(self):
        """2. Выбор специализации и старт теста"""
        if not self.token:
            self.interrupt()
            return
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Выбираем случайную специализацию (1-6)
        specialization_id = random.randint(1, 6)
        
        response = self.client.post("/api/start-test", 
            json={"specialization_id": specialization_id},
            headers=headers,
            name="/api/start-test"
        )
        
        if response.status_code == 200:
            data = response.json()
            self.user_test_id = data.get("user_test_id")
            print(f"✅ Started test: {self.user_test_id}")
        else:
            print(f"❌ Start test failed: {response.status_code}")
            self.interrupt()
    
    @task
    def get_questions(self):
        """3. Получение вопросов"""
        if not self.token or not self.user_test_id:
            self.interrupt()
            return
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = self.client.get(
            f"/api/test/{self.user_test_id}/questions",
            headers=headers,
            name="/api/test/{id}/questions"
        )
        
        if response.status_code == 200:
            data = response.json()
            self.questions = data.get("questions", [])
            print(f"✅ Got {len(self.questions)} questions")
        else:
            print(f"❌ Get questions failed: {response.status_code}")
            self.interrupt()
    
    @task
    def answer_all_questions(self):
        """4. Ответить на ВСЕ 24 вопроса по очереди"""
        if not self.token or not self.questions:
            self.interrupt()
            return
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Отвечаем на каждый вопрос
        for i, question in enumerate(self.questions):
            # Случайный ответ (1-4)
            user_answer = random.randint(1, 4)
            
            response = self.client.post("/api/submit-answer",
                json={
                    "user_test_id": self.user_test_id,
                    "question_id": question["question_id"],
                    "user_answer": user_answer
                },
                headers=headers,
                name="/api/submit-answer"
            )
            
            if response.status_code != 200:
                print(f"❌ Answer {i+1} failed: {response.status_code}")
                break
            
            # Небольшая пауза между ответами (реалистично)
            self.wait_time = between(0.5, 2)
        
        print(f"✅ Answered all {len(self.questions)} questions")
    
    @task
    def complete_test(self):
        """5. Завершение теста"""
        if not self.token or not self.user_test_id:
            self.interrupt()
            return
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = self.client.post(
            f"/api/complete-test/{self.user_test_id}",
            headers=headers,
            name="/api/complete-test/{id}"
        )
        
        if response.status_code == 200:
            data = response.json()
            score = data.get("score", 0)
            level = data.get("level", "Unknown")
            print(f"✅ Test completed! Score: {score}/24, Level: {level}")
        else:
            print(f"❌ Complete test failed: {response.status_code}")
        
        # После завершения теста - останавливаем юзера
        self.interrupt()


class HRForumUser(HttpUser):
    """Пользователь форума"""
    tasks = [UserJourney]
    wait_time = between(1, 3)  # Пауза между действиями
    host = "https://halyk.qabylda.com"  # Можно переопределить через --host