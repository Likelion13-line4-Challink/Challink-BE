from django.db import models
from django.conf import settings


class ChallengeCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "challenges_category"

    def __str__(self):
        return self.name

# PointHistory.challenge FK 대상으로, 이에 필요한 최소 필드만 설계했습니다. 더 확장해주세요.
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
    cover_image = models.URLField(blank=True, default="")

    entry_fee = models.PositiveIntegerField(default=0)           # 참가비
    duration_weeks = models.PositiveIntegerField(default=1)
    freq_type = models.CharField(max_length=10, choices=FREQ_CHOICES, default="매일")
    freq_n_days = models.PositiveIntegerField(null=True, blank=True)  # freq_type=주 N일일 때 사용

    ai_condition_text = models.TextField(blank=True, default="")

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
    # 성능 때문에 캐시 쓰려면 유지, 아니면 제거 가능
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


# SettlementDetail.challenge_member FK 대상으로, 이에 필요한 최소 필드만 설계했습니다. 더 확장해주세요.
class ChallengeMember(models.Model):
    ROLE_CHOICES = (("owner", "owner"), ("member", "member"))

    challenge = models.ForeignKey("challenges.Challenge", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="challenge_members")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    # 완료 후 통계(마이페이지/완료 목록용)
    success_rate = models.FloatField(null=True, blank=True)          # %
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
