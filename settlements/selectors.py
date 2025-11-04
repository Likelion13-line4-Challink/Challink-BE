from __future__ import annotations
from typing import List, Tuple
from dataclasses import dataclass
from datetime import date, timedelta, datetime

from django.utils import timezone
from challenges.models import Challenge, ChallengeMember, CompleteImage

KST = timezone.get_current_timezone()

# 한 참가자의 최종 집계 결과
@dataclass
class MemberProgress:
    cm: ChallengeMember
    success_days: int
    required_days: int
    is_success: bool   # success_days >= required_days

def _daterange(d0: date, d1: date):
    cur = d0
    while cur <= d1:
        yield cur
        cur += timedelta(days=1)

def _scheduled_at(ch: Challenge):
    if not ch.end_date:
        return None
    end_dt = datetime.combine(ch.end_date, datetime.min.time())
    end_dt = timezone.make_aware(end_dt, KST)
    return (end_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

def _required_days(ch: Challenge, *, weekly_bucket: bool = True) -> int:
    weeks = ch.duration_weeks or 1
    start, end = ch.start_date, ch.end_date
    if not (start and end):
        return weeks * 7

    if ch.freq_type == "매일":
        return weeks * 7

    days = list(_daterange(start, end))

    if ch.freq_type == "평일":
        return sum(1 for d in days if d.weekday() < 5)

    if ch.freq_type == "주말":
        return sum(1 for d in days if d.weekday() >= 5)

    if ch.freq_type == "주 N일":
        n = ch.freq_n_days or 1
        return n * weeks

    return weeks * 7

def _count_success_days(cm: ChallengeMember, start, end) -> int:
    qs = (CompleteImage.objects
        .filter(challenge_member=cm, status="approved")
        .values("date")
        .distinct())
    if start: qs = qs.filter(date__gte=start)
    if end:   qs = qs.filter(date__lte=end)
    return qs.count()

def collect_progress(ch: Challenge) -> List[MemberProgress]:
    req = _required_days(ch, weekly_bucket=True)
    members = (ChallengeMember.objects.select_related("user").filter(challenge=ch))
    res: List[MemberProgress] = []
    for cm in members:
        sd = _count_success_days(cm, ch.start_date, ch.end_date)
        res.append(MemberProgress(cm=cm, success_days=sd, required_days=req, is_success=(sd >= req)))
    return res

def get_or_create_settlement(challenge_id: int) -> Tuple[Challenge, object, str, object]:
    ch = Challenge.objects.filter(id=challenge_id).first()
    if not ch:
        return None, None, "not_found", None

    sched = _scheduled_at(ch)
    now = timezone.now()
    st = ch.settlements.order_by("-created_at").first()

    if not st:
        if sched and now < sched:
            return ch, None, "scheduled", sched
        return ch, None, "processing", sched
    return ch, st, st.status, sched
