from __future__ import annotations
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from rest_framework import serializers
from rest_framework import status, permissions

from challenges.models import Challenge, ChallengeMember
from accounts.models import PointHistory

from .models import Settlement, SettlementDetail
from .selectors import get_or_create_settlement, collect_progress, _required_days
from .services import run_settlement

class RewardStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, challenge_id: int):
        ch, st, st_status, sched = get_or_create_settlement(challenge_id)
        if not ch:
            return Response({"detail": "Not found."}, status=404)

        if st is None and st_status == "scheduled":
            return Response({
                "challenge_id": ch.id,
                "status": "scheduled",
                "scheduled_at": sched,
                "message": "정산은 챌린지 종료 다음날 자정에 진행됩니다."
            }, status=200)

        if st is None and st_status == "processing":
            st = run_settlement(ch)

        progress = getattr(st, "_progress", None) or collect_progress(ch)
        req_days = _required_days(ch, weekly_bucket=True)
        details = (SettlementDetail.objects
                .select_related("challenge_member__user")
                .filter(settlement=st))

        allocations, me_reward, claimed_at = [], 0, None
        for d in details:
            cm = d.challenge_member
            pg = next((p for p in progress if p.cm.id == cm.id), None)
            sd = pg.success_days if pg else 0
            is_success = pg.is_success if pg else False
            allocations.append({
                "user_id": cm.user_id,
                "name": cm.user.name if cm.user and cm.user.name else "",
                "success_days": sd,
                "required_days": req_days,
                "is_success": is_success,
                "reward_points": d.reward_point or 0,
            })
            if cm.user_id == request.user.id:
                me_reward = d.reward_point or 0
                claimed_at = d.claimed_at

        meta = getattr(st, "_meta_info", {})
        body = {
            "challenge_id": ch.id,
            "title": ch.title,
            "entry_fee": ch.entry_fee,
            "pot_total": st.total_pool_point or 0,
            "participant_count": ChallengeMember.objects.filter(challenge=ch).count(),
            "required_days": req_days,
            "settlement_method": int(ch.settle_method),
            "status": st.status,
            "scheduled_at": sched,
            "processed_at": st.settled_at,
            **meta,
            "allocations": allocations,
            "my": {
                "user_id": request.user.id,
                "my_reward": me_reward,
                "can_claim": (st.status == Settlement.Status.READY) and (me_reward > 0) and (claimed_at is None),
                "claimed_at": claimed_at,
            },
        }
        return Response(body, status=200)

class RewardClaimView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, challenge_id: int):
        ch = Challenge.objects.filter(id=challenge_id).first()
        if not ch:
            return Response({"detail": "Not found."}, status=404)

        st = (Settlement.objects.select_for_update()
            .filter(challenge=ch)
            .order_by("-created_at").first())
        if not st or st.status != Settlement.Status.READY:
            return Response({"error": "NOT_READY", "message": "정산은 종료 다음날 자정 이후 가능합니다."}, status=400)

        cm = ChallengeMember.objects.filter(challenge=ch, user=request.user).first()
        if not cm:
            return Response({"error": "FORBIDDEN", "message": "참여자가 아닙니다."}, status=403)

        detail = (SettlementDetail.objects.select_for_update()
                .filter(settlement=st, challenge_member=cm).first())
        if not detail:
            return Response({"error": "NOT_ASSIGNED", "message": "분배 대상이 아닙니다."}, status=400)
        if detail.claimed_at:
            return Response({"error": "ALREADY_CLAIMED", "claimed_at": detail.claimed_at}, status=409)

        credited = int(detail.reward_point or 0)
        if credited <= 0:
            detail.claimed_at = timezone.now()
            detail.save(update_fields=["claimed_at"])
            return Response({
                "challenge_id": ch.id,
                "settlement_method": int(ch.settle_method),
                "credited_points": 0,
                "claimed_at": detail.claimed_at,
                "wallet_after": request.user.point_balance,
                "message": "수령할 보상이 없습니다."
            }, status=200)

        # 지갑에 적립 (PointHistory 생성)
        ph = request.user.apply_points(
            delta=credited,
            description=f"[정산] {ch.title}",
            challenge=ch,
            history_type="REWARD",
        )
        detail.claimed_at = ph.occurred_at  # 적립 시각으로 기록
        detail.save(update_fields=["claimed_at"])

        # 모두 수령하면 상태 PAID
        if not SettlementDetail.objects.filter(settlement=st, claimed_at__isnull=True).exists():
            st.status = Settlement.Status.PAID
            st.save(update_fields=["status"])

        return Response({
            "challenge_id": ch.id,
            "settlement_method": int(ch.settle_method),
            "credited_points": credited,
            "claimed_at": detail.claimed_at,
            "wallet_after": request.user.point_balance,
            "message": "정산 보상이 지갑에 적립되었습니다."
        }, status=200)






class WalletChargeSerializer(serializers.Serializer):
    """지갑 충전 요청 바디 검증용"""
    amount = serializers.IntegerField(min_value=1)
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )



class WalletChargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get("amount")
        description = request.data.get("description") or ""

        # 1) amount 검증
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise ValidationError({"amount": "유효한 숫자를 입력해주세요."})
        if amount <= 0:
            raise ValidationError({"amount": "0보다 큰 값만 허용됩니다."})

        user = request.user

        with transaction.atomic():
            history = user.apply_points(
                delta=amount,
                description=description,
                challenge=None,
                history_type=PointHistory.Type.CHARGE,  
            )

        return Response(
            {
                "user_id": user.id,
                "charged_amount": amount,
                "point_balance_after": history.balance_after,
                "history": {
                    # id 대신 pk 사용
                    "point_history_id": history.pk,
                    "type": history.type,
                    "amount": history.amount,
                    "balance_after": history.balance_after,
                    "description": history.description,
                    "created_at": history.created_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )