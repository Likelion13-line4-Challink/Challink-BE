from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

from .serializers import (
    SignupSerializer, CheckEmailQuerySerializer,
    LoginSerializer, MeSerializer,
)
from .selectors import is_email_taken
from .services import authenticate_by_email_password, issue_access_token
from .models import Profile

class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 1) 이메일 중복(409) — Serializer로 올리면 400이 되므로 여기서 선제 체크
        raw_email = request.data.get("email")
        if raw_email is not None:
            email = Profile.objects.normalize_email(raw_email)
            if is_email_taken(email):
                return Response(
                    {"code": "EMAIL_TAKEN", "message": "해당 이메일의 계정이 이미 존재합니다."},
                    status=status.HTTP_409_CONFLICT,
                )

        # 2) 일반 유효성 + 생성
        ser = SignupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()

        body = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "point_balance": user.point_balance,
            "created_at": user.created_at.isoformat().replace("+00:00", "Z") if user.created_at else None,
        }
        return Response(body, status=status.HTTP_201_CREATED)


class CheckEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        q = CheckEmailQuerySerializer(data=request.query_params)
        q.is_valid(raise_exception=True)
        email = q.validated_data["email"]
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response(
                {"code": "INVALID_EMAIL", "message": "이메일 형식이 잘못되었습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        taken = is_email_taken(email)
        msg = "해당 이메일의 계정이 이미 존재합니다." if taken else "사용 가능한 이메일입니다."
        return Response({"email": email, "available": (not taken), "message": msg}, status=200)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"]
        password = ser.validated_data["password"]

        user = authenticate_by_email_password(email, password)
        if not user:
            return Response(
                {"code": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        access_token, expires_in = issue_access_token(user)
        body = {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "point_balance": user.point_balance,
            },
            "access_token": access_token,   # 세션/쿠키 전략이면 생략하고 Set-Cookie 사용
            "expires_in": expires_in,
        }
        return Response(body, status=200)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ser = MeSerializer(request.user)
        return Response(ser.data, status=200)
