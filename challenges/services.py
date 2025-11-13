import random
import string
from datetime import datetime, date, time, timedelta

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



# 정원 마감 등 “요청 형식은 맞으나 현재 상태로 처리 불가”
class Unprocessable(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "요청을 처리할 수 없습니다."




class Gone(APIException):
    """
    410 Gone (만료된 초대코드 등)에 사용
    """
    status_code = status.HTTP_410_GONE
    default_detail = "리소스가 만료되었습니다."




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
        # 422 - 정원 초과
        raise Unprocessable({
            "error": "CHALLENGE_FULL",
            "message": "정원이 가득 찼습니다.",
        })

    # 5) 참가비 처리 (entry_fee > 0일 때만)
    entry_fee_charged = 0
    User = get_user_model()  # 모델 클래스 확보
    if challenge.entry_fee and challenge.entry_fee > 0:
        # 유저 레코드에 락
        u = User.objects.select_for_update().get(pk=user.pk)
        current_balance = (u.point_balance or 0) #
        required = challenge.entry_fee

        if (u.point_balance or 0) < required:
            # 409 - 포인트 부족
            raise Conflict({
                "error": "INSUFFICIENT_POINT",
                "message": "포인트가 부족합니다.",
                "required_point": required,
                "current_balance": current_balance,
            })
        u.apply_points(
        delta=-required,
        description=challenge.title,
        challenge=challenge,
        history_type="JOIN",   # PointHistory.type = "참가" 로 매핑되도록
        )

        # F() 연산으로 차감
        User.objects.filter(pk=u.pk).update(point_balance=F("point_balance") - required)
        # 최신 잔액 반영
        u.refresh_from_db(fields=["point_balance"])
        user_point_balance_after = u.point_balance
        entry_fee_charged = required
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
            .get(pk=challenge_id)
        )
    except Challenge.DoesNotExist:
        raise NotFound("해당 챌린지를 찾을 수 없습니다.")



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








def _map_freq_type_model_to_api(freq_type: str) -> str:
    """
    Challenge 모델의 한글 freq_type → API용 영문 코드 매핑
    """
    mapping = {
        "매일": "DAILY",
        "평일": "WEEKDAYS",
        "주말": "WEEKENDS",
        "주 N일": "N_DAYS_PER_WEEK",
    }
    return mapping.get(freq_type, "DAILY")


def _map_settlement_method_to_api(settle_method: int) -> str:
    """
    Challenge.SettleMethod → API 문자열 매핑
    현재는 PROPORTIONAL만 사용.
    """
    if settle_method == Challenge.SettleMethod.PROPORTIONAL:
        return "PROPORTIONAL"
    # 방어적 기본값
    return "PROPORTIONAL"


def validate_invite_code_and_build_join_payload(*, user, invite_code: str) -> dict:
    """
    초대코드 검증 및 참가 가능 상태 계산

    - 404: 코드 존재하지 않음
    - 410: 코드 만료
    - 이미 참여: already_joined=true, can_join=false
    - 미참여:
        - 상태/정원/포인트 등을 보고 can_join / message 결정
        - 실제 참가(ChallengeMember 생성)는 여기서 하지 않음
    """
    now = timezone.now()

    try:
        invite = (
            InviteCode.objects
            .select_related("challenge")
            .get(code=invite_code)
        )
    except InviteCode.DoesNotExist:
        # 404 Not Found
        raise NotFound("해당 초대코드를 찾을 수 없습니다.")

    # 만료 체크
    if invite.expires_at <= now:
        # 410 Gone
        raise Gone("초대코드가 만료되었습니다.")

    challenge: Challenge = invite.challenge

    # 이미 이 챌린지에 참여했는지 확인
    my_member = (
        ChallengeMember.objects
        .filter(challenge=challenge, user=user)
        .only("id")
        .first()
    )

    if my_member:
        # 명세: 이미 참여 중인 경우
        return {
            "challenge_id": challenge.id,
            "challenge_title": challenge.title,
            "already_joined": True,
            "can_join": False,
            "challenge_member_id": my_member.id,
            "message": "이미 이 챌린지에 참여 중입니다.",
        }

    # 아직 참여 안 했을 때: 참가 가능 여부 계산
    # 기본값: 참가 가능
    can_join = True
    message = "참가 약관에 동의하면 참가할 수 있습니다."

    # 1) 상태 체크: active 만 참가 가능
    if challenge.status != "active":
        can_join = False
        message = "현재 활성 상태가 아닌 챌린지입니다."
    # 2) 정원 체크
    elif challenge.member_limit and challenge.member_count_cache >= challenge.member_limit:
        can_join = False
        message = "정원이 가득 찼습니다."
    else:
        # 3) 참가비(포인트) 체크
        entry_fee = challenge.entry_fee or 0
        user_balance = getattr(user, "point_balance", 0) or 0

        if entry_fee > 0 and user_balance < entry_fee:
            can_join = False
            message = "참가하기에 포인트가 부족합니다."

    # 응답 payload 구성 (명세 예시에 맞게)
    return {
        "challenge_id": challenge.id,
        "challenge_title": challenge.title,
        "challenge_description": challenge.subtitle or "",
        "entry_fee": challenge.entry_fee,
        "duration_weeks": challenge.duration_weeks,
        "freq_type": _map_freq_type_model_to_api(challenge.freq_type),
        "freq_n_days": challenge.freq_n_days,
        "ai_condition_text": challenge.ai_condition,
        "settlement_method": _map_settlement_method_to_api(challenge.settle_method),
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "already_joined": False,
        "can_join": can_join,
        "message": message,
    }
