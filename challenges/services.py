from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from .models import CompleteImage, Comment
from django.contrib.auth import get_user_model


from rest_framework.exceptions import APIException, PermissionDenied, NotFound, ValidationError
from rest_framework import status

from .models import Challenge, ChallengeMember


# 댓글 작성 서비스 로직
@transaction.atomic
def create_comment(photo_id: int, user, content: str, x_ratio=None, y_ratio=None):
     # 특정 인증 사진에 댓글을 작성 -> comment_count ++
     photo = get_object_or_404(CompleteImage, id=photo_id)

     # 댓글 생성
     comment = Comment.objects.create(
          complete_image=photo,
          user=user,
          content=content,
          x_ratio=x_ratio,
          y_ratio=y_ratio,
     )

     # 댓글 수 증가 (atomic)
     photo.comment_count = photo.comments.filter(is_deleted=False).count()
     photo.save(update_fields=["comment_count"])

     return comment



class Conflict(APIException):
    status_code = 409
    default_detail = "요청이 충돌합니다."


# @transaction.atomic
# def join_challenge(*, user, challenge_id: int, agree_terms: bool = False):
#     """
#     챌린지 참가 처리:
#     - 상태 검증(active만)
#     - 중복 참가 금지
#     - 정원 체크
#     - entry_fee 차감(부족 시 409)
#     - ChallengeMember 생성
#     - member_count_cache 증가
#     - 결과 payload 리턴
#     """
#     # 1) 챌린지 락 걸고 조회
#     try:
#         challenge = (
#             Challenge.objects.select_for_update()
#             .select_related("owner")
#             .get(pk=challenge_id)
#         )
#     except Challenge.DoesNotExist:
#         raise NotFound("해당 챌린지를 찾을 수 없습니다.")
#
#     # 2) 상태 정책: active만 허용
#     if challenge.status != "active":
#         raise PermissionDenied("현재 상태에서는 참가할 수 없습니다.")
#
#     # 3) 중복 참가 검사
#     if ChallengeMember.objects.filter(challenge_id=challenge.id, user_id=user.id).exists():
#         # 명세에 따라 400 사용
#         raise ValidationError({"detail": "이미 참가한 사용자입니다."})
#
#     # 4) 정원 확인
#     #   member_limit 이 None 이거나 0이면 무제한으로 간주하지 않고, 현재 모델은 default=6이므로 비교 가능
#     if challenge.member_limit and challenge.member_count_cache >= challenge.member_limit:
#         raise Conflict("정원이 가득 찼습니다.")
#
#     # 5) 참가비 처리 (entry_fee > 0일 때만)
#     entry_fee_charged = 0
#     if challenge.entry_fee and challenge.entry_fee > 0:
#         # 유저 레코드도 잠금(경합 방지)
#         user_locked = type(user)._default_manager.select_for_update().get(pk=user.pk)
#
#         if (user_locked.point_balance or 0) < challenge.entry_fee:
#             raise Conflict("포인트가 부족합니다.")
#
#         # F()로 차감
#         type(user_locked)._default_manager.filter(pk=user_locked.pk).update(
#             point_balance=F("point_balance") - challenge.entry_fee
#         )
#         # 최신 잔액 반영
#         user_locked.refresh_from_db(fields=["point_balance"])
#         user_point_balance_after = user_locked.point_balance
#         entry_fee_charged = challenge.entry_fee
#     else:
#         user_point_balance_after = getattr(user, "point_balance", 0)
#
#     # 6) 멤버 생성
#     member = ChallengeMember.objects.create(
#         challenge=challenge,
#         user=user,
#         role="member",
#     )
#
#     # 7) 카운터 증가
#     Challenge.objects.filter(pk=challenge.pk).update(
#         member_count_cache=F("member_count_cache") + 1
#     )
#     challenge.refresh_from_db(fields=["member_count_cache"])
#
#     # 8) 결과 payload
#     payload = {
#         "challenge_member_id": member.id,
#         "challenge_id": challenge.id,
#         "user_id": user.id,
#         "role": member.role,
#         "joined_at": member.joined_at,
#         "entry_fee_charged": entry_fee_charged,
#         "user_point_balance_after": user_point_balance_after,
#         "message": "참가가 완료되었습니다.",
#     }
#     return payload






@transaction.atomic
def join_challenge(*, user, challenge_id: int, agree_terms: bool = False):
    """
    챌린지 참가 처리:
    - 상태 검증(active만)
    - 중복 참가 금지
    - 정원 체크
    - entry_fee 차감(부족 시 409)
    - ChallengeMember 생성
    - member_count_cache 증가
    - 결과 payload 리턴
    """
    # 1) 챌린지 락 걸고 조회
    try:
        challenge = (
            Challenge.objects.select_for_update()
            .select_related("owner")
            .get(pk=challenge_id)
        )
    except Challenge.DoesNotExist:
        raise NotFound("해당 챌린지를 찾을 수 없습니다.")

    # 2) 상태 정책: active만 허용
    if challenge.status != "active":
        raise PermissionDenied("현재 상태에서는 참가할 수 없습니다.")

    # 3) 중복 참가 검사
    if ChallengeMember.objects.filter(challenge_id=challenge.id, user_id=user.id).exists():
        # 명세에 따라 400 사용
        raise ValidationError({"detail": "이미 참가한 사용자입니다."})

    # 4) 정원 확인
    if challenge.member_limit and challenge.member_count_cache >= challenge.member_limit:
        # 409 충돌
        raise ValidationError({"detail": "정원이 가득 찼습니다."}, code=status.HTTP_409_CONFLICT)

    # 5) 참가비 처리 (entry_fee > 0일 때만)
    entry_fee_charged = 0
    User = get_user_model()  # ✅ 모델 클래스 확보 (지연객체가 아님)
    if challenge.entry_fee and challenge.entry_fee > 0:
        # 유저 레코드에 락
        u = User.objects.select_for_update().get(pk=user.pk)

        if (u.point_balance or 0) < challenge.entry_fee:
            # 409 충돌
            raise ValidationError({"detail": "포인트가 부족합니다."}, code=status.HTTP_409_CONFLICT)

        # F() 연산으로 차감
        User.objects.filter(pk=u.pk).update(point_balance=F("point_balance") - challenge.entry_fee)
        # 최신 잔액 반영
        u.refresh_from_db(fields=["point_balance"])
        user_point_balance_after = u.point_balance
        entry_fee_charged = challenge.entry_fee
    else:
        user_point_balance_after = getattr(user, "point_balance", 0)

    # 6) 멤버 생성
    member = ChallengeMember.objects.create(
        challenge=challenge,
        user=user,
        role="member",
    )

    # 7) 카운터 증가
    Challenge.objects.filter(pk=challenge.pk).update(
        member_count_cache=F("member_count_cache") + 1
    )
    challenge.refresh_from_db(fields=["member_count_cache"])

    # 8) 결과 payload
    return {
        "challenge_member_id": member.id,
        "challenge_id": challenge.id,
        "user_id": user.id,
        "role": member.role,
        "joined_at": member.joined_at,
        "entry_fee_charged": entry_fee_charged,
        "user_point_balance_after": user_point_balance_after,
        "message": "참가가 완료되었습니다.",
    }