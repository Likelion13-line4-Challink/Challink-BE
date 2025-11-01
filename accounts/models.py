from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager
)
from django.utils import timezone

class ProfileManager(BaseUserManager):
    def create_user(self, email, password=None, name="", **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # 소셜/임시 계정 등 비밀번호가 없는 케이스 고려
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, name="admin", **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self.create_user(email, password, name=name, **extra_fields)


class Profile(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=100, blank=True)
    point_balance = models.IntegerField(default=0)  # 현재 포인트 잔액

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = ProfileManager()

    class Meta:
        db_table = "accounts_profile"
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"
        indexes = [
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"{self.name or ''}<{self.email}>"

    # 안전한 적립/차감 헬퍼 (정산/참가/충전 시 사용)
    def apply_points(self, delta: int, description: str = "", challenge=None, history_type: str = None):
        """
        delta: +적립 / -차감
        history_type: 'CHARGE' | 'JOIN' | 'REWARD'
        """
        # (선택) 음수 방지 정책이 필요하면 여기서 막기
        # if delta < 0 and (self.point_balance or 0) + delta < 0:
        #     raise ValueError("잔액이 부족합니다.")

        self.point_balance = (self.point_balance or 0) + int(delta)
        self.save(update_fields=["point_balance"])

        # 타입 자동 추론
        if history_type is None:
            history_type = "REWARD" if delta > 0 else "JOIN"

        ph = PointHistory.objects.create(
            user=self,
            challenge=challenge,
            type=history_type,
            amount=delta,
            balance_after=self.point_balance,
            description=description,
            occurred_at=timezone.now(),
        )
        return ph


class PointHistory(models.Model):
    class Type(models.TextChoices):
        CHARGE = "CHARGE", "충전"   # 유저가 충전
        JOIN   = "JOIN", "참가"     # 참가비 차감
        REWARD = "REWARD", "보상"   # 보상 적립

    point_history_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey("accounts.Profile", on_delete=models.CASCADE, related_name="point_histories")
    challenge = models.ForeignKey("challenges.Challenge", on_delete=models.SET_NULL, null=True, blank=True, related_name="point_histories")

    type = models.CharField(max_length=12, choices=Type.choices)  # ENUM
    amount = models.IntegerField()         # +적립 / -차감
    balance_after = models.IntegerField()  # 기록 시점의 잔액
    description = models.CharField(max_length=255, blank=True)

    occurred_at = models.DateTimeField(auto_now_add=True)  # 최신순 노출용
    created_at = models.DateTimeField(auto_now_add=True)   # DB에 기록 생성

    class Meta:
        db_table = "accounts_point_history"
        ordering = ["-occurred_at", "-point_history_id"]   # 최신 이벤트 우선
        indexes = [
            models.Index(fields=["user", "-occurred_at"]),
            models.Index(fields=["type"]),
            models.Index(fields=["challenge"]),
        ]

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"[{self.get_type_display()}] {sign}{self.amount} → {self.balance_after} ({self.user.email})"
