from __future__ import annotations
from django.db import transaction
from django.utils import timezone
from django.db.models import Count

from challenges.models import Challenge, ChallengeMember
from .models import Settlement, SettlementDetail
from .selectors import collect_progress


RULE_TEXT = {
    1: "모인 참가비를 성공자들끼리 N:1 분배해요",
    2: "참가비를 성공률에 따라 차등 분배해요",
    3: "성공자만 참가비를 돌려받고 남은 건 N:1 분배해요",
    4: "실패자 참가비는 Challink에게 기부해요❤",
}

def _actual_member_count(ch: Challenge) -> int:
    return ChallengeMember.objects.filter(challenge=ch).count()   # 실제 참가자 수

def _pot_total(ch: Challenge) -> int:
    return int(ch.entry_fee or 0) * _actual_member_count(ch)

def _distribute_method_1(ch, progress):
    pot = _pot_total(ch)
    winners = [p for p in progress if p.is_success]
    n = len(winners)
    if n == 0:
        return {p.cm.id: 0 for p in progress}, {"rule_text": RULE_TEXT[1]}
    base = pot // n
    rem = pot - base * n

    rewards = {}
    ordered = sorted([p.cm for p in winners], key=lambda cm: cm.user_id)
    for cm in ordered:
        add = 1 if rem > 0 else 0
        rewards[cm.id] = base + add
        rem -= add
    for p in progress:
        rewards.setdefault(p.cm.id, 0)
    return rewards, {"rule_text": RULE_TEXT[1]}

def _distribute_method_2(ch, progress):
    pot = _pot_total(ch)
    total_sd = sum(p.success_days for p in progress)
    if total_sd == 0:
        return {p.cm.id: 0 for p in progress}, {"rule_text": RULE_TEXT[2]}
    unit = pot // total_sd
    rewards = {p.cm.id: unit * p.success_days for p in progress}
    used = sum(rewards.values())
    rem = pot - used

    order = sorted(progress, key=lambda p: (-p.success_days, p.cm.user_id))
    for p in order:
        if rem <= 0: break
        rewards[p.cm.id] += 1
        rem -= 1
    return rewards, {"rule_text": RULE_TEXT[2]}

def _distribute_method_3(ch, progress):
    pot = _pot_total(ch)
    entry = int(ch.entry_fee or 0)
    winners = [p for p in progress if p.is_success]
    refund_total = entry * len(winners)
    remain = pot - refund_total

    people = len(progress) if progress else 1
    base = remain // people
    rem = remain - base * people

    rewards = {}
    rounded_up_ids = []
    ordered = sorted(progress, key=lambda p: (not p.is_success, p.cm.user_id))
    for p in ordered:
        extra = 1 if rem > 0 else 0
        if extra: rounded_up_ids.append(p.cm.user_id)
        rewards[p.cm.id] = (entry if p.is_success else 0) + base + extra
        rem -= extra

    meta = {
        "rule_text": RULE_TEXT[3],
        "rounding": {
            "base_share": base,
            "remainder": max(0, remain - base * people),
            "rounding_policy": "승자 우선 1p씩 가산",
            "rounded_up_user_ids": rounded_up_ids,
        },
    }
    return rewards, meta

def _distribute_method_4(ch, progress):
    pot = _pot_total(ch)
    entry = int(ch.entry_fee or 0)
    winners = [p for p in progress if p.is_success]
    rewards = {p.cm.id: entry for p in winners}
    for p in progress:
        rewards.setdefault(p.cm.id, 0)
    donate = pot - entry * len(winners)
    return rewards, {"rule_text": RULE_TEXT[4], "platform_gain_points": donate}

@transaction.atomic
def run_settlement(ch: Challenge) -> Settlement:
    st = (ch.settlements.select_for_update().order_by("-created_at").first())
    if st and st.status in (Settlement.Status.READY, Settlement.Status.PAID):
        return st

    method = int(ch.settle_method)
    st = st or Settlement.objects.create(
        challenge=ch,
        method=method,
        status=Settlement.Status.PROCESSING,
        total_pool_point=_pot_total(ch),
        scheduled_at=None,
    )

    progress = collect_progress(ch)
    if method == 1:
        rewards, meta = _distribute_method_1(ch, progress)
    elif method == 2:
        rewards, meta = _distribute_method_2(ch, progress)
    elif method == 3:
        rewards, meta = _distribute_method_3(ch, progress)
    else:
        rewards, meta = _distribute_method_4(ch, progress)

    existed = {d.challenge_member_id: d for d in SettlementDetail.objects.filter(settlement=st)}
    for p in progress:
        rp = int(rewards.get(p.cm.id, 0))
        d = existed.get(p.cm.id)
        if d:
            if d.reward_point != rp:
                d.reward_point = rp
                d.save(update_fields=["reward_point"])
        else:
            SettlementDetail.objects.create(settlement=st, challenge_member=p.cm, reward_point=rp)

    st.total_pool_point = _pot_total(ch)
    st.status = Settlement.Status.READY
    st.settled_at = timezone.now()
    st.save(update_fields=["total_pool_point", "status", "settled_at"])

    st._meta_info = meta
    st._progress = progress
    return st
