from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

from accounts.models import Profile


class ChallengeCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "challenges_category"

    def __str__(self):
        return self.name


class Challenge(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "초안"
        ACTIVE = "active", "진행 중"
        ENDED = "ended", "종료"
        CANCELED = "canceled", "취소됨"

    class FreqType(models.TextChoices):
        DAILY = "DAILY", "매일"
        WEEKDAYS = "WEEKDAYS", "주중(월~금)"
        WEEKENDS = "WEEKENDS", "주말(토~일)"
        N_DAYS_PER_WEEK = "N_DAYS_PER_WEEK", "주당 N회"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cover_image = models.URLField(blank=True, default="")

    entry_fee = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    duration_weeks = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    freq_type = models.CharField(max_length=20, choices=FreqType.choices, default=FreqType.DAILY)
    # N_DAYS_PER_WEEK일 때만 1~6 허용
    freq_n_days = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)])

    ai_condition_text = models.TextField(blank=True, default="")

    settlement_method = models.CharField(
        max_length=30,
        choices=[
            ("EQUAL", "균등 분배"),
            ("PROPORTIONAL", "기여 비례"),
            ("WINNER_TAKES_ALL", "승자 독식"),
            ("CUSTOM", "사용자 정의"),
        ],
        default="EQUAL",
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)



    category = models.ForeignKey(
        "challenges.ChallengeCategory",
        on_delete=models.SET_NULL,
        null=True,
        related_name="challenges",
    )
    # FK 필드명은 user/owner 처럼 도메인명 사용 (DB 컬럼은 owner_id 자동 생성)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_challenges",
    )

    member_limit = models.PositiveIntegerField(default=6, validators=[MinValueValidator(1)])
    member_count_cache = models.PositiveIntegerField(default=0)



    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "challenges_challenge"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-start_date"]),
            models.Index(fields=["-end_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"






class ChallengeMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "개설자"
        MEMBER = "member", "참여자"

    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='members')  # 참여중인 챌린지
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="challenge_members")

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True) # 참가일

    # 완료 통계
    success_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    final_points_awarded = models.IntegerField(null=True, blank=True)
    final_rank = models.PositiveIntegerField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "challenges_challenge_member"
        unique_together = [("challenge_id", "user_id")]
        indexes = [models.Index(fields=["challenge_id", "user_id"])]

    def __str__(self):
        return f"user#{self.user_id} in challenge#{self.challenge_id}"


class CompleteImage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "거절"

    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="complete_images")
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="complete_images")

    image = models.ImageField(upload_to="challenges/%Y/%m/%d/")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    proof_date = models.DateField(null=True, blank=True)
    comment_cnt = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Image#{self.challenge_id} {self.status} by {self.user_id}"


class Comment(models.Model):
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="comments")
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="comments")
    image_id = models.ForeignKey(CompleteImage, on_delete=models.CASCADE, related_name="comments")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment({self.challenge_id}) by {self.user_id} on Image {self.image_id}"


class InviteCode(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="invite_codes")
    code = models.CharField(max_length=32, unique=True)
    expire_at = models.DateTimeField(null=False)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({'활성' if self.is_active else '비활성'})"
