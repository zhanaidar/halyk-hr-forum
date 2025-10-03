from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os

# Секретный ключ для подписи токенов (в production должен быть в .env)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "halyk-hr-forum-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7  # Токен живет 7 дней

def create_access_token(user_id: int, phone: str) -> str:
    """Создать JWT токен для пользователя"""
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "user_id": user_id,
        "phone": phone,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Проверить JWT токен и вернуть данные"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        phone: str = payload.get("phone")
        
        if user_id is None or phone is None:
            return None
            
        return {"user_id": user_id, "phone": phone}
    except JWTError:
        return None