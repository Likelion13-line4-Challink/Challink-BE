from profile import Profile

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings



class Challenge(models.Model):

    class FreqType(models.TextChoices):
        DAILY = "DAILY", "매일"
        WEEKDAYS = "WEEKDAYS", "주중(월~금)"
        WEEKENDS = "WEEKENDS", "주말(토~일)"
        N_DAYS_PER_WEEK = "N_DAYS_PER_WEEK", "주당 N회"

    class SettlementMethod(models.TextChoices):
        EQUAL = "EQUAL", "균등 분배"
        PROPORTIONAL = "PROPORTIONAL", "기여 비례"
        WINNER_TAKES_ALL = "WINNER_TAKES_ALL", "승자 독식"
        CUSTOM = "CUSTOM", "사용자 정의"

    class Status(models.TextChoices):
        DRAFT = "draft", "초안"
        ACTIVE = "active", "진행 중"
        ENDED = "ended", "종료"
        CANCELED = "canceled", "취소됨"

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="challenges_created") # 챌린지 생성자
    category = models.ForeignKey("ChallengeCategory", on_delete=models.SET_NULL, null=True, blank=True,related_name="challenges")

    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    cover_image = models.URLField(blank=True)

    entry_fee = models.PositiveIntegerField()
    duration_weeks = models.PositiveIntegerField()

    freq_type = models.CharField(max_length=20, choices=FreqType.choices, default=FreqType.DAILY) # freq_type
    freq_n_days = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)]) # freq_n_days (N_DAYS_PER_WEEK일 때만 1~6중 선택)

    ai_condition = models.TextField() # AI 인증 조건 설명
    settlement_method = models.CharField(max_length=30, choices=SettlementMethod.choices, default=SettlementMethod.EQUAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)

    start_date = models.DateField() # 시작날
    end_date = models.DateField() # 종료날
    created_at = models.DateTimeField(auto_now_add=True) # 챌린지 생성일
    updated_at = models.DateTimeField(auto_now=True) # 수정시간추적용

    class Meta:
        ordering = ["-created_at"] # 내림차순으로

    def __str__(self): # 챌린지 제목 (시작일~종료일) 반환
        return f"{self.title} ({self.start_date}~{self.end_date})"






class CompleteImage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "거절"


    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="complete_images")
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='complete_images')

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
    content = models.TextField() # 댓글 내용
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="comments")
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="comments")
    image_id = models.ForeignKey(CompleteImage,on_delete=models.CASCADE,related_name="comments")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment({self.challenge_id}) by {self.user_id} on Image {self.image_id}"




class InviteCode(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE,)
    code = models.CharField(max_length=32, unique=True)
    expire_at = models.DateTimeField()
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"] # 내림차순

    def __str__(self):
        return f"{self.code} ({'활성' if self.is_active else '비활성'})"






class ChallengeMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "개설자"
        MEMBER = "member", "참여자"


    challenge_id = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='members') # 참여중인 챌린지
    user_id = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='challenge_memberships') # 참가중인 참가자

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True) # 참가일

    success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True, blank=True, # 종료 시 확정되므로 최초엔 NULL 허용
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    final_points_awarded = models.IntegerField(null=True, blank=True) # 정산 후 지급 금액
    final_rank = models.PositiveIntegerField(null=True, blank=True) # 최종 순위
    created_at = models.DateTimeField(auto_now_add=True) # 생성시각


    class Meta:
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user_id} -> {self.challenge_id} ({self.role})"




class ChallengeCategory(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name