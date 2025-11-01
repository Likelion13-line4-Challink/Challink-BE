from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from .models import CompleteImage, Comment
from accounts.models import Profile

from typing import Optional, Tuple
from django.db import models
from django.db.models import Q, Prefetch
from django.utils import timezone
from .models import Challenge, ChallengeMember, CompleteImage


# 사진 1개 상세 조회 (댓글 포함)
def get_complete_image_with_comments(photo_id: int):
    return (
        CompleteImage.objects
        .select_related("user")
        .prefetch_related(
            Prefetch("comments", queryset=Comment.objects.select_related("user").order_by("created_at"))
        )
        .filter(id=photo_id)
        .first()
    )


# 챌린지 내 모든 사진 조회 (+ 이름 필터링)
def get_challenge_images(challenge_id: int, name: str = None):
    qs = CompleteImage.objects.select_related("user", "challenge_member__challenge").filter(
        challenge_member__challenge_id=challenge_id
    )

    if name and name.strip():
        qs = qs.filter(user__name__icontains=name.strip())

    return qs.order_by("-created_at")


def list_challenges_selector(
    *,
    user=None,
    include_full_slots: bool = False,   # True면 정원 가득도 포함
    order: str = "recent",              # recent(=created_at desc) | popular | oldest
    category_id: Optional[int] = None,
    search: Optional[str] = None,
):
    now = timezone.now()

    # 1) 카테고리/소유자 join + "유효 초대코드 보유 챌린지" 필터
    qs = (Challenge.objects
        .select_related("category", "owner")
        # 초대코드가 최소 1개 이상, 만료 전이어야 함
        .filter(invite_codes__expires_at__gte=now)
        .distinct())  # 동일 챌린지가 invite_codes 개수만큼 중복될 수 있으므로 distinct()

    # 2) 정원 제한(기본: 꽉 찬 챌린지는 숨김)
    if not include_full_slots:
        qs = qs.filter(member_count_cache__lt=models.F("member_limit"))

    # 3) 카테고리/검색
    if category_id:
        qs = qs.filter(category_id=category_id)
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(subtitle__icontains=search) |
            Q(category__name__icontains=search)
        )

    # 4) 정렬
    #    - recent: "최신 생성된 챌린지" 우선 → created_at DESC, id DESC
    #    - popular: 참여자 많은 순 → member_count_cache DESC, created_at DESC
    #    - oldest: created_at ASC
    if order == "popular":
        qs = qs.order_by("-member_count_cache", "-created_at", "-id")
    elif order == "oldest":
        qs = qs.order_by("created_at", "id")
    else:  # recent
        qs = qs.order_by("-created_at", "-id")

    # 5) 로그인 유저 참여 여부 계산을 위한 prefetch (is_joined 판단)
    if user and getattr(user, "is_authenticated", False):
        qs = qs.prefetch_related(
            Prefetch(
                "members",
                queryset=ChallengeMember.objects.filter(user=user).only("id", "challenge_id", "user_id"),
                to_attr="__me_member__",   # serializer에서 is_joined 계산에 사용
            )
        )
    return qs


def my_challenges_selector(
    *,
    user,
    status: str = "active",             # active | ended
    include_owner: bool = True,
    order: str = "recent",              # recent=created_at desc | oldest | reward_desc(ended 전용)
    category_id: Optional[int] = None,
    search: Optional[str] = None,
):
    # 내 멤버십을 기준으로 조인(카드 필드 최소화를 위해 challenge/category select_related)
    qs = (ChallengeMember.objects
        .select_related("challenge", "challenge__category")
        .filter(user=user))

    # 상태 필터
    if status == "active":
        qs = qs.filter(challenge__status="active")
    elif status == "ended":
        qs = qs.filter(challenge__status="ended")

    # 생성자 포함 여부
    if not include_owner:
        qs = qs.exclude(role="owner")

    # 카테고리/검색
    if category_id:
        qs = qs.filter(challenge__category_id=category_id)
    if search:
        qs = qs.filter(
            Q(challenge__title__icontains=search) |
            Q(challenge__subtitle__icontains=search) |
            Q(challenge__category__name__icontains=search)
        )

    # 정렬
    # - 요구사항: "최신 생성된 챌린지 맨 위" → 기본 created_at DESC
    # - 완료 목록 특수 옵션: reward_desc
    if status == "ended" and order == "reward_desc":
        qs = qs.order_by("-final_points_awarded", "-challenge__created_at", "-id")
    elif order == "oldest":
        qs = qs.order_by("challenge__created_at", "id")
    else:
        qs = qs.order_by("-challenge__created_at", "-id")

    return qs


def challenge_detail_selector(challenge_id: int, *, user=None):
    # 디테일: challenge + (있으면) 내 membership + 오늘 성공 수
    challenge = (Challenge.objects
                .select_related("category", "owner")
                .filter(id=challenge_id)
                .first())
    if not challenge:
        return None, None

    my_member = None
    if user and getattr(user, "is_authenticated", False):
        my_member = (ChallengeMember.objects
                    .only("id", "role", "joined_at", "challenge_id", "user_id")
                    .filter(challenge_id=challenge_id, user=user)
                    .first())

    # 오늘 성공 수(success_today): 승인된(approved) 인증 이미지를 "오늘 날짜"로 집계
    today = timezone.localdate()
    success_today = CompleteImage.objects.filter(
        challenge_member__challenge_id=challenge_id,
        status="approved",
        date=today,  # 날짜 컬럼이 모델에 이미 존재
    ).count()

    return challenge, (my_member, success_today)
