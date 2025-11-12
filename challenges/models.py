from django.db import models
from django.conf import settings
from PIL import Image
import io, os
from django.core.files.base import ContentFile
from pillow_heif import register_heif_opener
register_heif_opener()


# ✅ 챌린지 카테고리
class ChallengeCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "challenges_category"

    def __str__(self):
        return self.name


# ✅ 챌린지 본체
class Challenge(models.Model):
    STATUS_CHOICES = (
        ("draft", "draft"),
        ("active", "active"),
        ("ended", "ended"),
        ("canceled", "canceled"),
    )
    FREQ_CHOICES = (("매일", "매일"), ("평일", "평일"), ("주말", "주말"), ("주 N일", "주 N일"))

    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True, default="")
    cover_image = models.ImageField (
    upload_to="challenge_covers/",
    blank=True,
    null=True
    )

    entry_fee = models.PositiveIntegerField(default=0)
    duration_weeks = models.PositiveIntegerField(default=1)
    freq_type = models.CharField(max_length=10, choices=FREQ_CHOICES, default="매일")
    freq_n_days = models.PositiveIntegerField(null=True, blank=True)

    class SettleMethod(models.IntegerChoices):
        N_TO_ONE_WINNER = 1, "성공자끼리 1/N 균등 분배"
        PROPORTIONAL    = 2, "성공률 비례 분배"
        REFUND_PLUS_ALL = 3, "성공자 환급 + 잔여 1/N 분배"
        DONATE_FAIL_FEE = 4, "실패자 참가비 기부"
    
    ai_condition = models.TextField(blank=True, default="")
    settle_method = models.IntegerField(choices=SettleMethod.choices, default=SettleMethod.N_TO_ONE_WINNER)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    category = models.ForeignKey(
        "challenges.ChallengeCategory",
        on_delete=models.SET_NULL,
        null=True,
        related_name="challenges",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_challenges",
    )

    member_limit = models.PositiveIntegerField(default=6)
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


# ✅ 챌린지 멤버 (참여자)
class ChallengeMember(models.Model):
    ROLE_CHOICES = (("owner", "owner"), ("member", "member"))

    challenge = models.ForeignKey(
        "challenges.Challenge",
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_members",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    success_rate = models.FloatField(null=True, blank=True)
    final_points_awarded = models.IntegerField(null=True, blank=True)
    final_rank = models.IntegerField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "challenges_challenge_member"
        unique_together = [("challenge", "user")]
        indexes = [
            models.Index(fields=["challenge", "user"]),
        ]

    def __str__(self):
        return f"user#{self.user_id} in challenge#{self.challenge_id}"


# ✅ 인증 이미지 (AI 인증 대상)
class CompleteImage(models.Model):
    class Status(models.TextChoices):
        PENDING  = "pending", "대기중"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "거절"

    challenge_member = models.ForeignKey(
        "challenges.ChallengeMember",
        on_delete=models.CASCADE,
        related_name="complete_images",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="complete_images",
    )
    image = models.ImageField(upload_to="complete_images/")
    converted_image = models.ImageField(
        upload_to="complete_images/converted/",
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    date = models.DateField(null=True, blank=True)
    comment_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # AI 판정 완료 시각
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # 반려 사유 저장(줄바꿈으로 누적)
    review_reasons = models.TextField(blank=True, default="")
    
    file_sha1 = models.CharField(max_length=40, null=True, blank=True, db_index=True)  # 40 hex
    phash = models.BigIntegerField(null=True, blank=True, db_index=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    # 빠른 정책 로그용 필드
    flagged_duplicate = models.BooleanField(default=False)

    class Meta:
        db_table = "challenges_complete_image"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # 원본 먼저 저장
        if self.image and not self.converted_image:
            try:
                self.image.open()
                img = Image.open(self.image).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                filename = os.path.splitext(self.image.name)[0] + ".jpg"
                self.converted_image.save(filename, ContentFile(buf.getvalue()), save=False)
                super().save(update_fields=["converted_image"])
            except Exception as e:
                print("HEIC → JPEG 변환 실패:", e)

    def __str__(self):
        return f"Image #{self.id} by user#{self.user_id}"


# ✅ 댓글
class Comment(models.Model):
    complete_image = models.ForeignKey(
        "challenges.CompleteImage",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    content = models.TextField()

    x_ratio = models.FloatField(null=True, blank=True)
    y_ratio = models.FloatField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "challenges_comment"
        indexes = [
            models.Index(fields=["complete_image"]),
        ]

    def __str__(self):
        return f"Comment by user#{self.user_id} on image#{self.complete_image_id}"


# ✅ 초대코드
class InviteCode(models.Model):
    challenge = models.ForeignKey(
        "challenges.Challenge",
        on_delete=models.CASCADE,
        related_name="invite_codes",
    )
    code = models.CharField(max_length=32, unique=True)
    is_used = models.BooleanField(default=False)
    usage_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "challenges_invite_code"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"InviteCode({self.code}) for challenge#{self.challenge_id}"
