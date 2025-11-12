from datetime import timedelta
from django.utils import timezone


from django.shortcuts import render
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import GenericAPIView, ListCreateAPIView
from main.utils.pagination import StandardPagePagination
from django.conf import settings
from .models import CompleteImage, ChallengeMember, Challenge
from rest_framework.parsers import MultiPartParser, FormParser


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

    ChallengeEndResponseSerializer,

    ChallengeRuleUpdateSerializer,
    ChallengeRuleUpdateOutSerializer,

    InviteCodeJoinInSerializer,
    InviteCodeJoinOutSerializer,
)
from .selectors import (
    get_complete_image_with_comments,
    get_challenge_images,
    list_challenges_selector,
    my_challenges_selector,
    challenge_detail_selector,
)
from .services import create_comment, join_challenge, Conflict, end_challenge, validate_invite_code_and_build_join_payload
DEFAULT_DISPLAY_THUMBNAIL = getattr(settings, "DEFAULT_DISPLAY_THUMBNAIL", None)


# 절대 URL 생성 유틸
def _abs_image_url(request, image_field):
    """
    ImageField → 절대 URL 문자열로 안전 변환
    - 파일이 없으면 None 반환
    """
    if not image_field:
        return None
    try:
        url = image_field.url  # ex) /media/...
    except Exception:
        return None
    # 절대 URL로 통일
    return request.build_absolute_uri(url)


class ChallengeListCreateView(ListCreateAPIView):
    """
    GET/POST /challenges/
    - GET: 공개 목록 (challink_ 초대코드 or 키워드 검색)
    - POST: 챌린지 생성
    """
    permission_classes = [AllowAny]
    pagination_class = StandardPagePagination
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        """
        - GET  : 누구나 허용 (AllowAny)
        - POST : 로그인 필수 (IsAuthenticated)
        """
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]


    def get_queryset(self):
        req = self.request
        include_full = (req.query_params.get("include_full", "false").lower() == "true")
        order = req.query_params.get("order", "recent")
        category_id = req.query_params.get("category_id")
        search = req.query_params.get("search") or req.query_params.get("q")

        return list_challenges_selector(
            user=req.user if req.user.is_authenticated else None,
            include_full_slots=include_full,
            order=order,
            category_id=int(category_id) if category_id else None,
            search=search,
        )

    def get_serializer_class(self):
        return ChallengeCardSerializer if self.request.method == "GET" else ChallengeCreateSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        data_qs = page if page is not None else qs
        ser = ChallengeCardSerializer(data_qs, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(ser.data)
        return Response({"page": 1, "page_size": len(ser.data), "total": len(ser.data), "items": ser.data})

    def create(self, request, *args, **kwargs):
        # POST 그대로 유지
        in_ser = ChallengeCreateSerializer(data=request.data, context={"request": request})
        in_ser.is_valid(raise_exception=True)
        obj = in_ser.save()
        out_ser = ChallengeCreateOutSerializer(obj, context={"request": request})
        return Response(out_ser.data, status=201)



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
            x_ratio=serializer.validated_data.get("x_ratio"),
            y_ratio=serializer.validated_data.get("y_ratio"),
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
                    "cover_image": _abs_image_url(request, ch.cover_image),
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
                    "cover_image": _abs_image_url(request, ch.cover_image),
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

        latest_approved = (
            CompleteImage.objects
            .filter(challenge_member__challenge_id=challenge.id, status="approved")
            .order_by("user_id", "-date", "-id")
        )

        latest_map = {}
        for img in latest_approved:
            uid = img.user_id
            if uid not in latest_map:
                # ✅ /media/ → media/
                latest_map[uid] = img.image.url.lstrip("/") if img.image else None

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




class ChallengeEndView(APIView):
    """
    POST /challenges/{challenge_id}/end

    - 챌린지 생성자 또는 운영자만 호출 가능
    - 챌린지 상태를 ended 로 변경
    - 정산 예약 정보(scheduled_at, status)를 함께 응답
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, challenge_id: int):
        payload = end_challenge(user=request.user, challenge_id=challenge_id)
        serializer = ChallengeEndResponseSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)




class ChallengeRuleUpdateView(APIView):
    """
    PATCH /challenges/{challenge_id}/rules

    - 인증: 로그인 필수
    - 권한: challenge.owner 이거나, ChallengeMember(role='owner')
    - 상태: status='ended' 인 경우 409 Conflict
    - 부분 업데이트 허용 (freq_type, freq_n_days, ai_condition_text)
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, challenge_id: int):
        # 1) 챌린지 조회
        try:
            challenge = Challenge.objects.get(pk=challenge_id)
        except Challenge.DoesNotExist:
            return Response({"detail": "해당 챌린지를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # 2) 이미 종료된 챌린지는 규칙 변경 불가
        if challenge.status == "ended":
            return Response(
                {"detail": "이미 종료된 챌린지는 규칙을 수정할 수 없습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        user = request.user

        # 3) 권한 체크: 생성자(owner 필드) 또는 멤버 중 role='owner'
        is_owner_user = (challenge.owner_id == user.id)
        has_owner_membership = ChallengeMember.objects.filter(
            challenge=challenge,
            user=user,
            role="owner",
        ).exists()

        if not (is_owner_user or has_owner_membership):
            return Response(
                {"detail": "해당 챌린지를 수정할 권한이 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 4) 입력 검증 (부분 업데이트)
        serializer = ChallengeRuleUpdateSerializer(
            data=request.data,
            context={"request": request, "challenge": challenge},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not data:
            return Response(
                {"detail": "변경할 필드를 최소 한 개 이상 포함해야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5) 실제 필드 업데이트
        # freq_type: API → 모델 매핑 (영문 코드 → 한글)
        if "freq_type" in data:
            api_freq = data["freq_type"]
            challenge.freq_type = ChallengeCreateSerializer.FREQ_IN_MAP[api_freq]

        if "freq_n_days" in data:
            challenge.freq_n_days = data["freq_n_days"]

        if "ai_condition_text" in data:
            challenge.ai_condition = data["ai_condition_text"]

        challenge.save()  # updated_at 자동 갱신(auto_now)

        # 6) 응답 payload 구성 (모델 → API 표기)
        response_payload = {
            "challenge_id": challenge.id,
            "freq_type": ChallengeCreateSerializer.FREQ_OUT_MAP.get(challenge.freq_type, "DAILY"),
            "freq_n_days": challenge.freq_n_days,
            "ai_condition_text": challenge.ai_condition,
            "updated_at": challenge.updated_at,
        }
        out_ser = ChallengeRuleUpdateOutSerializer(response_payload)
        return Response(out_ser.data, status=status.HTTP_200_OK)






class InviteCodeJoinView(APIView):
    """
    POST /invites/join

    - 인증: 로그인 필수
    - Body: {"invite_code": "challink_XXXXXX"}
    - 기능: 초대코드 유효성 검증 + 참가 가능 여부(already_joined / can_join / message) 반환
    - 실제 챌린지 참가(ChallengeMember 생성)는 여기서 하지 않음.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1) 입력 검증
        in_ser = InviteCodeJoinInSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        invite_code = in_ser.validated_data["invite_code"]

        # 2) 서비스 호출 (초대코드 검증 + 상태 계산)
        payload = validate_invite_code_and_build_join_payload(
            user=request.user,
            invite_code=invite_code,
        )

        # 3) 응답 시리얼라이즈 + 200 OK
        out_ser = InviteCodeJoinOutSerializer(payload)
        return Response(out_ser.data, status=status.HTTP_200_OK)
