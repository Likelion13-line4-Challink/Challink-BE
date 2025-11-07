from datetime import timedelta
from django.utils import timezone

from django.shortcuts import render
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import GenericAPIView
from main.utils.pagination import StandardPagePagination
from django.conf import settings
from .models import CompleteImage, ChallengeMember, Challenge

from rest_framework.permissions import AllowAny






from .serializers import (
    CompleteImageDetailSerializer,
    CompleteImageListSerializer,
    CommentSerializer,
    CommentCreateSerializer,
    ChallengeCardSerializer,
    ChallengeDetailForGuestSerializer,
    ChallengeDetailForMemberSerializer,

    ChallengeCreateSerializer,
    ChallengeCreateOutSerializer,

    ChallengeJoinSerializer,
    ChallengeJoinOutSerializer,
)
from .selectors import (
    get_complete_image_with_comments,
    get_challenge_images,
    list_challenges_selector,
    my_challenges_selector,
    challenge_detail_selector,
)
from .services import create_comment, join_challenge, Conflict
DEFAULT_DISPLAY_THUMBNAIL = getattr(settings, "DEFAULT_DISPLAY_THUMBNAIL", None)



# 기록 사진 상세 조회 (댓글 포함)
class CompleteImageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, photo_id):
        photo = get_complete_image_with_comments(photo_id)
        if not photo:
            return Response({"detail": "해당 사진을 찾을 수 없습니다."}, status=404)

        serializer = CompleteImageDetailSerializer(photo)
        return Response(serializer.data, status=200)


# 댓글 작성
class CommentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, photo_id):
        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 서비스 호출 (트랜잭션)
        comment = create_comment(
            photo_id=photo_id,
            user=request.user,
            content=serializer.validated_data["content"],
        )

        # 응답: 생성된 댓글 정보 반환
        response_serializer = CommentSerializer(comment)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# 챌린지 내 사진 목록 조회 (이름 필터링)
class ChallengeImageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, challenge_id):
        name = request.query_params.get("name", None)
        photos = get_challenge_images(challenge_id, name)

        serializer = CompleteImageListSerializer(photos, many=True)
        return Response(serializer.data, status=200)


class ChallengeListView(GenericAPIView):
    """
    GET /challenges/
    - 공개 목록. 비로그인 허용.
    - "초대코드 유효기간 = 카드 노출기간" 강제
    (selectors에서 InviteCode.expires_at >= now 로 필터)
    - 정렬 기본: 최근 생성(created_at DESC)
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ChallengeCardSerializer
    pagination_class = StandardPagePagination

    def get(self, request):
        include_full = request.query_params.get("include_full", "false").lower() == "true"
        order = request.query_params.get("order", "recent")  # popular | recent | oldest
        category_id = request.query_params.get("category_id")
        search = request.query_params.get("search")

        qs = list_challenges_selector(
            user=request.user if request.user.is_authenticated else None,
            include_full_slots=include_full,
            order=order,
            category_id=int(category_id) if category_id else None,
            search=search,
        )

        page = self.paginate_queryset(qs)
        data = self.get_serializer(page if page is not None else qs, many=True, context={"request": request}).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response({"page": 1, "page_size": len(data), "total": len(data), "items": data})


class MyChallengeListView(GenericAPIView):
    """
    GET /challenges/my/
    - 내 챌린지 목록(진행/완료 스위치)
    - 로그인 필수
    - 정렬 기본: 최근 생성(created_at DESC)
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagePagination

    def get(self, request):
        status_q = request.query_params.get("status", "active")  # active | ended
        include_owner = request.query_params.get("include_owner", "true").lower() == "true"
        order = request.query_params.get("order", "recent")      # recent | oldest | reward_desc(ended)
        category_id = request.query_params.get("category_id")
        search = request.query_params.get("search")

        member_qs = my_challenges_selector(
            user=request.user,
            status=status_q,
            include_owner=include_owner,
            order=order,
            category_id=int(category_id) if category_id else None,
            search=search,
        )

        page = self.paginate_queryset(member_qs)
        rows = page if page is not None else member_qs

        items = []
        for cm in rows:
            ch = cm.challenge
            items.append({
                "challenge_member": {
                    "challenge_member_id": cm.id,
                    "challenge_id": cm.challenge_id,
                    "user_id": cm.user_id,
                    "role": cm.role,
                    "joined_at": cm.joined_at,
                },
                "challenge": {
                    "id": ch.id,
                    "title": ch.title,
                    "subtitle": ch.subtitle,
                    "cover_image": ch.cover_image,
                    "duration_weeks": ch.duration_weeks,
                    "freq_type": ch.freq_type,
                    "entry_fee": ch.entry_fee,
                    "category": {"id": ch.category_id, "name": ch.category.name if ch.category else None},
                    "member_count": ch.member_count_cache,
                    "member_limit": ch.member_limit,
                    "status": ch.status,
                    "start_date": ch.start_date,
                    "end_date": ch.end_date,
                }
            })

        if page is not None:
            return self.get_paginated_response(items)
        return Response({"page": 1, "page_size": len(items), "total": len(items), "items": items})


class MyCompletedChallengeListView(GenericAPIView):
    """
    GET /challenges/my/completed/
    - alias: /challenges/my/?status=ended
    - 로그인 필수
    - 정렬 기본: 최근 생성(created_at DESC)
    + 옵션: reward_desc (보상 많은 순)
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagePagination

    def get(self, request):
        order = request.query_params.get("order", "recent")  # recent | oldest | reward_desc
        category_id = request.query_params.get("category_id")
        search = request.query_params.get("search")

        member_qs = my_challenges_selector(
            user=request.user,
            status="ended",
            include_owner=True,
            order=order,
            category_id=int(category_id) if category_id else None,
            search=search,
        )

        page = self.paginate_queryset(member_qs)
        rows = page if page is not None else member_qs

        items = []
        for cm in rows:
            ch = cm.challenge
            items.append({
                "challenge_member": {
                    "challenge_member_id": cm.id,
                    "challenge_id": cm.challenge_id,
                    "user_id": cm.user_id,
                    "role": cm.role,
                    "joined_at": cm.joined_at,
                    "success_rate": cm.success_rate,
                    "final_points_awarded": cm.final_points_awarded or 0,
                    "final_rank": cm.final_rank,
                    "ended_at": cm.ended_at,
                },
                "challenge": {
                    "id": ch.id,
                    "title": ch.title,
                    "subtitle": ch.subtitle,
                    "cover_image": ch.cover_image,
                    "duration_weeks": ch.duration_weeks,
                    "freq_type": ch.freq_type,
                    "entry_fee": ch.entry_fee,
                    "category": {"id": ch.category_id, "name": ch.category.name if ch.category else None},
                    "member_count": ch.member_count_cache,
                    "member_limit": ch.member_limit,
                    "status": ch.status,
                    "start_date": ch.start_date,
                    "end_date": ch.end_date,
                }
            })

        if page is not None:
            return self.get_paginated_response(items)
        return Response({"page": 1, "page_size": len(items), "total": len(items), "items": items})

def _calc_streak_days(user_id: int, challenge_id: int) -> int:
    """
    오늘을 끝점으로 승인된 인증의 연속 일수
    """
    today = timezone.localdate()
    qs = (CompleteImage.objects
        .filter(challenge_member__challenge_id=challenge_id, user_id=user_id, status="approved")
        .values_list("date", flat=True)
        .distinct()
        .order_by("-date"))
    dates = list(qs)
    if not dates:
        return 0
    streak, cursor = 0, today
    for d in dates:
        if d == cursor:
            streak += 1
            cursor = cursor - timedelta(days=1)
        elif d < cursor:
            break
    return streak

class ChallengeDetailView(GenericAPIView):
    """
    GET /challenges/{challenge_id}/
    - 미참여: 팝업 스키마(가입 가능 여부 포함)
    - 참여  : 진행 스키마(progress_summary/participants/my_membership)
    - success_today: 오늘 날짜의 'approved' CompleteImage로 집계
    - participants: 추후 상세 데이터 연동 전까지는 빈 배열(TODO)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, challenge_id: int):
        challenge, extra = challenge_detail_selector(
            challenge_id,
            user=request.user if request.user.is_authenticated else None
        )
        if not challenge:
            return Response({"detail": "Not found."}, status=404)

        my_member, success_today = extra

        if not my_member:
            # is_joined 계산을 위해 __me_member__ 속성만 비워둠
            setattr(challenge, "__me_member__", [])
            ser = ChallengeDetailForGuestSerializer(challenge, context={"request": request})
            return Response(ser.data, status=200)

        # ✅ 참여자 응답(최소 구현)
        setattr(challenge, "__my_member__", my_member)
        today = timezone.localdate()

        members = (ChallengeMember.objects
                   .select_related("user")
                   .filter(challenge_id=challenge.id))

        today_approved_uids = set(CompleteImage.objects.filter(
            challenge_member__challenge_id=challenge.id,
            status="approved",
            date=today
        ).values_list("user_id", flat=True))

        latest_approved = (CompleteImage.objects
                           .filter(challenge_member__challenge_id=challenge.id, status="approved")
                           .order_by("user_id", "-date", "-id")
                           .values("user_id", "image"))

        latest_map = {}
        for row in latest_approved:
            uid = row["user_id"]
            if uid not in latest_map:
                latest_map[uid] = row["image"]

        participants = []
        for m in members:
            uid = m.user_id
            has_today = uid in today_approved_uids
            latest = latest_map.get(uid)
            display = latest if (has_today and latest) else (latest or DEFAULT_DISPLAY_THUMBNAIL)
            participants.append({
                "user_id": uid,
                "name": m.user.name if m.user and m.user.name else "",
                "avatar": None,
                "streak_days": _calc_streak_days(uid, challenge.id),
                "has_proof_today": has_today,
                "latest_proof_image": latest,
                "display_thumbnail": display,
                "is_owner": (m.role == "owner"),
            })

        payload = {
            "id": challenge.id,
            "title": challenge.title,
            "entry_fee": challenge.entry_fee,
            "duration_weeks": challenge.duration_weeks,
            "freq_type": challenge.freq_type,
            "category": {"id": challenge.category_id, "name": challenge.category.name if challenge.category else None},
            "status": challenge.status,
            "start_date": challenge.start_date,
            "end_date": challenge.end_date,
            "member_count": challenge.member_count_cache,
            "member_limit": challenge.member_limit,
            "progress_summary": {
                "success_today": success_today,
                "total_members": challenge.member_count_cache,
                "date": today,
            },
            "participants": participants,
            "my_membership": {
                "is_joined": True,
                "challenge_member_id": my_member.id,
                "role": my_member.role,
                "joined_at": my_member.joined_at,
            },
            "settlement_note": "🔥 총 참가비: N p / 모인 참가비를 성공자들에게 N:1 분배해요",
        }
        ser = ChallengeDetailForMemberSerializer(payload)
        return Response(ser.data, status=200)




class ChallengeCreateView(generics.CreateAPIView):
    """POST /challenges/ : 챌린지 생성 전용"""
    queryset = Challenge.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChallengeCreateSerializer

    def create(self, request, *args, **kwargs):
        in_ser = self.get_serializer(data=request.data, context={"request": request})
        in_ser.is_valid(raise_exception=True)
        instance = in_ser.save()
        out_ser = ChallengeCreateOutSerializer(instance)
        headers = self.get_success_headers(out_ser.data)
        return Response(out_ser.data, status=status.HTTP_201_CREATED, headers=headers)



class ChallengeJoinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, challenge_id: int):
        # 1) 입력 검증
        in_ser = ChallengeJoinSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        agree_terms = in_ser.validated_data.get("agree_terms", False)

        # 2) 서비스 호출 (내부에서 트랜잭션/검증/차감 처리)
        payload = join_challenge(
            user=request.user,
            challenge_id=challenge_id,
            agree_terms=agree_terms,
        )

        # 3) 응답 시리얼라이징 + 200
        out_ser = ChallengeJoinOutSerializer(payload)
        return Response(out_ser.data, status=status.HTTP_200_OK)
