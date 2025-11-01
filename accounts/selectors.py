from .models import Profile, PointHistory
from django.utils.dateparse import parse_datetime
from django.db.models import QuerySet

def is_email_taken(email: str) -> bool:
    return Profile.objects.filter(email=email).exists()   # 이메일 중복 여부 확인

def select_wallet_history(user, ph_type=None, since=None, until=None, challenge_id=None):
    qs = PointHistory.objects.filter(user=user).order_by("-occurred_at", "-point_history_id")

    # type: 한글 입력 시 내부 ENUM으로 매핑
    type_map = {"충전": "CHARGE", "참가": "JOIN", "보상": "REWARD"}
    if ph_type:
        mapped = type_map.get(ph_type, ph_type)  # 한글 or 영문 둘 다 허용
        qs = qs.filter(type=mapped)

    if since:
        dt_from = parse_datetime(since)
        if dt_from:
            qs = qs.filter(occurred_at__gte=dt_from)
    if until:
        dt_to = parse_datetime(until)
        if dt_to:
            qs = qs.filter(occurred_at__lte=dt_to)
    if challenge_id:
        qs = qs.filter(challenge_id=challenge_id)

    return qs
