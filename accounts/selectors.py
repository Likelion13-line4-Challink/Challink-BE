# accounts/selectors.py
from .models import Profile

def is_email_taken(email: str) -> bool:
    return Profile.objects.filter(email=email).exists()   # 이메일 중복 여부 확인
