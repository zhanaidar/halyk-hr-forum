from locust import HttpUser, task, between
import random

class ForumUser(HttpUser):
    wait_time = between(2, 5)
    
    def on_start(self):
        """Регистрация при старте"""
        phone = f"+7700{random.randint(1000000, 9999999)}"
        response = self.client.post("/api/register", json={
            "name": f"User{random.randint(1, 10000)}",
            "surname": "Test",
            "phone": phone,
            "company": "Test Company",
            "job_title": "Tester"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
    
    @task(5)
    def view_dashboard(self):
        """Смотрим публичный дашборд"""
        self.client.get("/api/dashboard/stats")
    
    @task(3)
    def browse_profiles(self):
        """Смотрим профессии"""
        self.client.get("/api/profiles")
    
    @task(2)
    def browse_specializations(self):
        """Смотрим специализации"""
        profile_id = random.randint(1, 3)
        self.client.get(f"/api/profiles/{profile_id}/specializations")
    
    @task(1)
    def complete_full_test(self):
        """Проходим полный тест"""
        if not hasattr(self, 'token') or not self.token:
            return
        
        response = self.client.post(
            "/api/start-test",
            json={"specialization_id": random.randint(1, 5)},
            headers=self.headers
        )
        
        if response.status_code != 200:
            return
        
        data = response.json()
        user_test_id = data.get("user_test_id")
        
        if not user_test_id:
            return
        
        questions_response = self.client.get(
            f"/api/test/{user_test_id}/questions",
            headers=self.headers
        )
        
        if questions_response.status_code != 200:
            return
        
        questions_data = questions_response.json()
        questions = questions_data.get("questions", [])
        
        for i, question in enumerate(questions):
            self.client.post(
                "/api/submit-answer",
                json={
                    "user_test_id": user_test_id,
                    "question_id": question["question_id"],
                    "user_answer": random.randint(1, 4)
                },
                headers=self.headers,
                name="/api/submit-answer"
            )
            
            if i < len(questions) - 1:
                self.wait()
        
        self.client.post(
            f"/api/complete-test/{user_test_id}",
            headers=self.headers
        )