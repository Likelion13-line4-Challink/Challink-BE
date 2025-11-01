# accounts/services.py
from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Profile

def authenticate_by_email_password(email: str, password: str) -> Profile | None:
    return authenticate(username=email, password=password)

def issue_access_token(user: Profile) -> tuple[str, int]:
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    expires_in = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    return str(access), expires_in
