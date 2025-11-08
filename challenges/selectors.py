from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from .models import CompleteImage, Comment
from accounts.models import Profile

from typing import Optional, Tuple
from django.db import models
from django.db.models import Q, Prefetch
from django.utils import timezone
from .models import Challenge, ChallengeMember, CompleteImage, Comment
from typing import Optional


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

    base_qs = Challenge.objects.select_related("category", "owner")

    # --- (1) 초대코드 검색 여부 분기 ---
    if search and search.strip().lower().startswith("challink_"):
        qs = base_qs.filter(
            invite_codes__code=search.strip(),   # 대소문자 구분
            invite_codes__expires_at__gte=now
        ).distinct()
    else:
        qs = base_qs.filter(status="active")

        # --- (2) 일반 검색 조건 ---
        if search and search.strip():
            keyword = search.strip()
            qs = qs.filter(
                Q(title__icontains=keyword) |
                Q(subtitle__icontains=keyword) |
                Q(category__name__icontains=keyword)
            )

    # --- (3) 카테고리 필터 ---
    if category_id:
        qs = qs.filter(category_id=category_id)

    # --- (4) 정원 제한 ---
    if not include_full_slots:
        qs = qs.filter(member_count_cache__lt=models.F("member_limit"))

    # --- (5) 정렬 ---
    if order == "popular":
        qs = qs.order_by("-member_count_cache", "-created_at", "-id")
    elif order == "oldest":
        qs = qs.order_by("created_at", "id")
    else:  # recent (기본)
        qs = qs.order_by("-created_at", "-id")

    # --- (6) 로그인 유저 참여 여부 프리패치 ---
    if user and getattr(user, "is_authenticated", False):
        qs = qs.prefetch_related(
            Prefetch(
                "members",
                queryset=ChallengeMember.objects.filter(user=user).only("id", "challenge_id", "user_id"),
                to_attr="__me_member__",
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

    # "나의 챌린지": 진행중만 / "완료": ended만
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

    # 정렬 active → created_at, ended → end_date
    if status == "ended":
        if order == "reward_desc":
            qs = qs.order_by("-final_points_awarded", "-challenge__end_date", "-id")
        elif order == "oldest":
            qs = qs.order_by("challenge__end_date", "id")
        else:
            qs = qs.order_by("-challenge__end_date", "-id")
    else:
        if order == "oldest":
            qs = qs.order_by("challenge__created_at", "id")
        else:
            qs = qs.order_by("-challenge__created_at", "-id")

    return qs


def challenge_detail_selector(challenge_id: int, *, user=None):
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
        date=today,
    ).count()

    return challenge, (my_member, success_today)
