from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from .serializers import (
    SignupSerializer,
    LoginSerializer, MeSerializer, PointHistorySerializer,
)
from .selectors import is_email_taken, select_wallet_history
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


class WalletHistoryView(APIView, PageNumberPagination):
    permission_classes = [IsAuthenticated]
    page_size = 20

    def get(self, request):
        ph_type = request.query_params.get("type")
        since = request.query_params.get("since")
        until = request.query_params.get("until")
        challenge_id = request.query_params.get("challenge_id")
        page_size = request.query_params.get("page_size", self.page_size)

        # page_size validation
        try:
            page_size = int(page_size)
            if not (1 <= page_size <= 100):
                return Response({"detail": "page_size는 1~100 사이여야 합니다."}, status=400)
            self.page_size = page_size
        except ValueError:
            return Response({"detail": "page_size는 정수여야 합니다."}, status=400)

        qs = select_wallet_history(
            user=request.user,
            ph_type=ph_type,
            since=since,
            until=until,
            challenge_id=challenge_id,
        )

        page = self.paginate_queryset(qs, request, view=self)
        serializer = PointHistorySerializer(page, many=True)

        response_data = {
            "user_id": request.user.id,
            "page": int(request.query_params.get("page", 1)),
            "page_size": self.page_size,
            "total_count": self.page.paginator.count,
            "results": serializer.data,
        }
        return Response(response_data, status=200)
