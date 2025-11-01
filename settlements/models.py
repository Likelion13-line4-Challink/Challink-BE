from django.db import models
from django.utils import timezone

class Settlement(models.Model):
    class Method(models.IntegerChoices):
        N_TO_ONE_WINNER = 1, "성공자끼리 1/N 균등 분배"
        PROPORTIONAL    = 2, "성공률 비례 분배"
        REFUND_PLUS_ALL = 3, "성공자 환급 + 잔여 1/N 분배"
        DONATE_FAIL_FEE = 4, "실패자 참가비 기부"

    class Status(models.TextChoices):
        SCHEDULED  = "scheduled", "예정"   # 종료 다음날 자정 전
        PROCESSING = "processing", "진행중"   # 분배 로직 계산 중
        READY      = "ready", "완료(수령 대기)"   # 각 참가자 몫 계산 완료, 수령 대기
        PAID       = "paid", "지급 완료"   # 전원 수령 완료

    settlement_id = models.BigAutoField(primary_key=True)
    challenge = models.ForeignKey("challenges.Challenge", on_delete=models.CASCADE, related_name="settlements")

    total_pool_point = models.IntegerField(null=True, blank=True)  # 최종 분배 대상 금액
    method = models.IntegerField(choices=Method.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)

    scheduled_at = models.DateTimeField(null=True, blank=True)  # 정산 예정 시각(다음날 자정)
    settled_at = models.DateTimeField(null=True, blank=True)    # 실제 정산 계산 완료 시각
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "settlements_settlement"
        indexes = [
            models.Index(fields=["challenge"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-scheduled_at"]),
        ]

    def __str__(self):
        return f"#{self.settlement_id} ch={self.challenge_id} [{self.get_status_display()}]"

    @property
    def is_claimable(self):
        return self.status == self.Status.READY


class SettlementDetail(models.Model):
    detail_id = models.BigAutoField(primary_key=True)
    settlement = models.ForeignKey("settlements.Settlement", on_delete=models.CASCADE, related_name="details")
    challenge_member = models.ForeignKey("challenges.ChallengeMember", on_delete=models.CASCADE, related_name="settlement_details")   # 사용자와 챌린지를 함께 식별
    reward_point = models.IntegerField(null=True, blank=True)  # 0 포함
    claimed_at = models.DateTimeField(null=True, blank=True)  # 수령 시각(수령 전: null, 수령 후: 타임스탬프 기록)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "settlements_settlement_detail"
        indexes = [
            models.Index(fields=["settlement"]),
            models.Index(fields=["challenge_member"]),
        ]
        constraints = [
            # 하나의 settlement에서 동일한 member는 1건만
            models.UniqueConstraint(fields=["settlement", "challenge_member"], name="uniq_settlement_member")
        ]

    def __str__(self):
        return f"settle#{self.settlement_id} cm#{self.challenge_member_id} → {self.reward_point or 0}"
