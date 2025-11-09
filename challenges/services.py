import random
import string
from datetime import datetime, time, timedelta

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from rest_framework.exceptions import APIException, PermissionDenied, NotFound, ValidationError
from rest_framework import status

from .models import (
    CompleteImage,
    Comment,
    Challenge,
    ChallengeMember,
    InviteCode,
)



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




class Conflict(APIException):
    status_code = 409
    default_detail = "요청이 충돌합니다."


def generate_invite_code_for_challenge(*, challenge: Challenge, max_attempts: int = 5) -> InviteCode:
    """
    챌린지 생성 시 초대코드 1개를 발급한다.

    - 포맷: 'challink_' + 대문자/숫자 6자리
    - 만료:
        - end_date가 있으면 그날 23:59:59
        - 없으면 생성 시각 기준 30일 후
    - code 유니크 충돌 시 최대 max_attempts번 재시도
    """
    alphabet = string.ascii_uppercase + string.digits
    tz = timezone.get_current_timezone()
    now = timezone.now().astimezone(tz)

    # 만료 시각 계산
    if challenge.end_date:
        expires_at = datetime.combine(
            challenge.end_date,
            time(23, 59, 59),
            tzinfo=tz,
        )
    else:
        expires_at = now + timedelta(days=30)

    # 코드 생성 & 저장 (유니크 충돌 시 재시도)
    for _ in range(max_attempts):
        suffix = "".join(random.choices(alphabet, k=6))
        code = f"challink_{suffix}"
        try:
            invite = InviteCode.objects.create(
                challenge=challenge,
                code=code,
                expires_at=expires_at,
            )
            return invite
        except IntegrityError:
            # code 유니크 충돌 → 다시 시도
            continue

    # 모든 시도 실패 시 409 반환
    raise Conflict("초대코드 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")






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
    User = get_user_model()  # 모델 클래스 확보 (지연객체가 아님)
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






@transaction.atomic
def end_challenge(*, user, challenge_id: int) -> dict:
    """
    챌린지 종료 처리 서비스.
    - Challenge를 행 락(select_for_update)으로 가져옴
    - 권한 체크: owner 이거나 운영자(예: is_staff)만 가능
    - 이미 ended 상태면 ALREADY_ENDED 에러
    - status 를 ended 로 변경
    - ended_at = 지금 시간
    - settlement.scheduled_at = '챌린지 종료일의 다음날 0시' 기준으로 계산
    - 응답 payload(dict)를 리턴
    """

    # 1) 챌린지 조회 + 락
    try:
        challenge = (
            Challenge.objects.select_for_update()
            .select_related("owner")
            .get(pk=challenge_id)
        )
    except Challenge.DoesNotExist:
        raise NotFound("해당 챌린지를 찾을 수 없습니다.")

    # 2) 권한 체크: 생성자(owner) 이거나 운영자(여기선 is_staff 기준)만 허용
    is_owner = (challenge.owner_id == user.id)
    is_operator = getattr(user, "is_staff", False)

    if not (is_owner or is_operator):
        # 명세에 맞춘 에러 포맷
        raise PermissionDenied(
            {"error": "FORBIDDEN", "message": "종료 권한이 없습니다."}
        )

    # 3) 이미 종료된 챌린지인지 체크
    if challenge.status == "ended":
        raise ValidationError(
            {"error": "ALREADY_ENDED", "message": "이미 종료된 챌린지입니다."}
        )

    # 4) 상태 변경 및 종료 시각 기록
    now = timezone.now()
    challenge.status = "ended"
    # updated_at 이 auto_now=True 라면 아래 update_fields 에 넣지 않아도 자동으로 갱신됨
    challenge.save(update_fields=["status"])

    # 5) 정산 예정 시간 계산
    #    - 기본 정책: "챌린지 종료일 + 1일"의 00:00
    #    - end_date 가 비어 있으면, 오늘 날짜 기준으로 계산
    base_end_date: date = challenge.end_date or now.date()
    scheduled_date = base_end_date + timedelta(days=1)

    # 현재 타임존의 자정으로 만들기
    current_tz = timezone.get_current_timezone()
    scheduled_at = datetime.combine(
        scheduled_date,
        time(0, 0, 0),
        tzinfo=current_tz,
    )

    # 6) 응답 payload 구성
    payload = {
        "challenge_id": challenge.id,
        "status": challenge.status,
        "ended_at": now,
        "settlement": {
            "scheduled_at": scheduled_at,
            "status": "scheduled",
        },
    }
    return payload
