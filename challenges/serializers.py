from django.db import transaction
from django.db.models import F
from rest_framework import serializers
from .models import CompleteImage, Comment, Challenge, ChallengeCategory, InviteCode, ChallengeMember

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .services import generate_invite_code_for_challenge, Conflict


class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "user_id",
            "user_name",
            "content",
            "x_ratio",
            "y_ratio",
            "created_at",
        ]
        read_only_fields = ["id", "user_id", "user_name", "created_at"]


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["content", "x_ratio", "y_ratio"]

    def create(self, validated_data):
        """
        view에서 photo(CompleteImage)와 user를 넘겨줘야 함
        """
        photo = self.context["photo"]
        user = self.context["user"]
        return Comment.objects.create(
            complete_image=photo,
            user=user,
               **validated_data,
        )


class CompleteImageDetailSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = CompleteImage
        fields = [
            "id",
            "user_id",
            "user_name",
            "image",
            "status",
            "date",
            "comment_count",
            "created_at",
            "comments",
        ]
        read_only_fields = fields

    def get_image(self, obj):
        # 변환본이 있으면 우선 사용
        if getattr(obj, "converted_image", None):
            return obj.converted_image.url.lstrip("/")
        # 없으면 원본 사용
        return obj.image.url.lstrip("/") if obj.image else None


class CompleteImageListSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = CompleteImage
        fields = [
            "id",
            "user_id",
            "user_name",
            "image",
            "comment_count",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def get_image(self, obj):
        # 변환본이 있으면 우선 사용
        if getattr(obj, "converted_image", None):
            return obj.converted_image.url.lstrip("/")
        # 없으면 원본 사용
        return obj.image.url.lstrip("/") if obj.image else None



class CategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChallengeCategory
        fields = ("id", "name")

class CategoryMiniOut(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(allow_null=True, required=False)

class ChallengeCardSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer()
    is_joined = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()  # cache → public name 변환

    class Meta:
        model = Challenge
        fields = (
            "id", "title", "subtitle", "cover_image",
            "duration_weeks", "freq_type", "freq_n_days", "entry_fee",
            "category", "member_count", "member_limit",
            "status", "start_date", "end_date",
            "is_joined",
        )

    def get_is_joined(self, obj):
        # selectors에서 __me_member__에 "내 membership" 프리패치됨
        mem = getattr(obj, "__me_member__", None)
        return bool(mem) and len(mem) > 0

    def get_member_count(self, obj):
        return getattr(obj, "member_count_cache", 0)


class ChallengeDetailForGuestSerializer(serializers.ModelSerializer):
    # 미참여(게스트/팝업)
    # ai_condition = serializers.CharField(source="ai_condition")
    ai_condition = serializers.CharField()
    owner_name = serializers.SerializerMethodField()
    category = CategoryMiniSerializer()
    my_membership = serializers.SerializerMethodField()
    joinable = serializers.SerializerMethodField()
    join_block_reason = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = (
            "id", "title", "owner_name", "cover_image",
            "entry_fee", "duration_weeks", "freq_type", "freq_n_days",
            "subtitle", "ai_condition", "category",
            "status", "start_date", "end_date",
            "member_count", "member_limit",
            "my_membership", "joinable", "join_block_reason",
        )

    def get_owner_name(self, obj):
        owner = getattr(obj, "owner", None)
        return f"{owner.name}님의 챌린지" if owner and owner.name else "챌린지"

    def get_my_membership(self, obj):
        # 게스트 응답: is_joined만 전달
        return {"is_joined": bool(getattr(obj, "__me_member__", []))}

    def get_joinable(self, obj):
        # 가입 가능 조건: active + 정원 미달 + 미참여
        if obj.status != "active":
            return False
        if getattr(obj, "member_count_cache", 0) >= obj.member_limit:
            return False
        if bool(getattr(obj, "__me_member__", [])):
            return False
        return True

    def get_join_block_reason(self, obj):
        if obj.status != "active":
            return "활성 상태가 아닙니다."
        if getattr(obj, "member_count_cache", 0) >= obj.member_limit:
            return "정원이 가득 찼습니다."
        if bool(getattr(obj, "__me_member__", [])):
            return "이미 참여 중입니다."
        return None

    def get_member_count(self, obj):
        return getattr(obj, "member_count_cache", 0)


class ParticipantMiniSerializer(serializers.Serializer):
    # 추후 사용자/썸네일 연동 시 실제 데이터로 대체
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    avatar = serializers.CharField(allow_null=True)
    streak_days = serializers.IntegerField()
    has_proof_today = serializers.BooleanField()
    latest_proof_image = serializers.CharField(allow_null=True)
    display_thumbnail = serializers.CharField()
    is_owner = serializers.BooleanField()


class ProgressSummarySerializer(serializers.Serializer):
    success_today = serializers.IntegerField()
    total_members = serializers.IntegerField()
    date = serializers.DateField()

class InviteCodeMiniSerializer(serializers.Serializer):
    code = serializers.CharField()
    expires_at = serializers.DateTimeField()
    case_sensitive = serializers.BooleanField()
    
class ChallengeDetailForMemberSerializer(serializers.Serializer):
    # 참여 중(진행 화면)
    id = serializers.IntegerField()
    title = serializers.CharField()
    entry_fee = serializers.IntegerField()
    duration_weeks = serializers.IntegerField()
    freq_type = serializers.CharField()
    freq_n_days = serializers.IntegerField(allow_null=True)
    category = CategoryMiniOut()
    status = serializers.CharField()
    start_date = serializers.DateField(allow_null=True)
    end_date = serializers.DateField(allow_null=True)
    member_count = serializers.IntegerField()
    member_limit = serializers.IntegerField()
    progress_summary = ProgressSummarySerializer()
    participants = ParticipantMiniSerializer(many=True)
    my_membership = serializers.DictField()
    settlement_note = serializers.CharField()
    ai_condition = serializers.CharField()                 # ✅ 추가
    total_entry_pot = serializers.IntegerField()           # ✅ 추가
    invite_codes = InviteCodeMiniSerializer(many=True)   # ✅ 추가



class ChallengeCreateSerializer(serializers.Serializer):
    # API 명세 입력 스키마 (클라이언트가 보내는 키 그대로)
    title = serializers.CharField(max_length=200)
    subtitle = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.IntegerField()
    cover_image = serializers.ImageField(required=False, allow_null=True)
    entry_fee = serializers.IntegerField(min_value=0)
    duration_weeks = serializers.IntegerField(min_value=1)
    freq_type = serializers.ChoiceField(choices=["DAILY", "WEEKDAYS", "WEEKENDS", "N_DAYS_PER_WEEK"])
    freq_n_days = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=6)
    ai_condition_text = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.ChoiceField(choices=["draft", "active"], default="draft")

    # API → 모델 필드 매핑 테이블
    FREQ_IN_MAP = {
        "DAILY": "매일",
        "WEEKDAYS": "평일",
        "WEEKENDS": "주말",
        "N_DAYS_PER_WEEK": "주 N일",
    }
    FREQ_OUT_MAP = {v: k for k, v in FREQ_IN_MAP.items()}

    # settlement 매핑 (모델 choices 참조)

    SUPPORTED_SETTLEMENT_METHODS = {
        "N_TO_ONE_WINNER": Challenge.SettleMethod.N_TO_ONE_WINNER,
        "PROPORTIONAL": Challenge.SettleMethod.PROPORTIONAL,
        "REFUND_PLUS_ALL": Challenge.SettleMethod.REFUND_PLUS_ALL,
        "DONATE_FAIL_FEE": Challenge.SettleMethod.DONATE_FAIL_FEE,
    }
    settlement_method = serializers.ChoiceField(choices=list(SUPPORTED_SETTLEMENT_METHODS.keys()))


    def validate(self, attrs):
        # 날짜 유효성
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "end_date는 start_date 이후여야 합니다."})

        # freq_n_days 규칙
        if attrs["freq_type"] == "N_DAYS_PER_WEEK":
            if attrs.get("freq_n_days") is None:
                raise serializers.ValidationError({"freq_n_days": "N_DAYS_PER_WEEK에서는 1~6 사이의 정수가 필요합니다."})
        else:
            # 그 외 타입에서는 freq_n_days는 보내지 않거나 null이어야 함
            if "freq_n_days" in attrs and attrs["freq_n_days"] not in (None,):
                raise serializers.ValidationError({"freq_n_days": "이 빈도 타입에서는 freq_n_days를 보내지 않습니다."})

        # settlement 지원 여부
        if attrs["settlement_method"] not in self.SUPPORTED_SETTLEMENT_METHODS:
            raise serializers.ValidationError({
                "settlement_method": "지원하지 않는 정산 방식입니다."
            })

        return attrs

    @transaction.atomic
    def create(self, validated):
        # 카테고리 확인
        try:
            category = ChallengeCategory.objects.get(pk=validated["category_id"])
        except ChallengeCategory.DoesNotExist:
            raise serializers.ValidationError({"category_id": "존재하지 않는 카테고리입니다."})

        # API → 모델 매핑
        freq_type_model = self.FREQ_IN_MAP[validated["freq_type"]]
        method_str = validated["settlement_method"]  # 현재는 PROPORTIONAL만 지원
        settle_model = self.SUPPORTED_SETTLEMENT_METHODS[method_str]

        request_user = self.context["request"].user     # 요청자(생성자)
        status_fixed = "active"   # draft 불필요

        subtitle_val = validated.get("subtitle")
        if subtitle_val is None:
            subtitle_val = validated.get("description", "") or ""

        challenge = Challenge.objects.create(
            title=validated["title"],
            subtitle=subtitle_val,
            cover_image=validated.get("cover_image", "") or "",
            entry_fee=validated["entry_fee"],
            duration_weeks=validated["duration_weeks"],
            freq_type=freq_type_model,
            freq_n_days=validated.get("freq_n_days"),
            ai_condition=validated.get("ai_condition_text", "") or "",
            settle_method=settle_model,
            status=status_fixed,
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            category=category,
            owner=request_user,  # 생성자 지정
        )

        # 생성자 참가비 즉시 차감 (entry_fee > 0 일 때)
        entry_fee = challenge.entry_fee or 0
        if entry_fee > 0:
            User = get_user_model()
            # 생성자 레코드 락
            u = User.objects.select_for_update().get(pk=request_user.pk)
            current_balance = u.point_balance or 0
            if current_balance < entry_fee: # 현재잔고가 참가비보다 적다면
                # 409 Conflict - 포인트 부족
                raise Conflict({
                    "error": "INSUFFICIENT_POINT",
                    "message": "포인트가 부족합니다.",
                    "required_point": entry_fee,
                    "current_balance": current_balance,
                })
            # 포인트 차감(+ 히스토리 기록)
            u.apply_points(
                delta=-entry_fee,
                description=challenge.title,
                challenge=challenge,
                history_type="JOIN",
            )
            # 잔액
            u.refresh_from_db(fields=["point_balance"])




        # 생성자를 owner 멤버로 자동 참여
        ChallengeMember.objects.create(
            challenge=challenge,
            user=request_user,
            role="owner",
        )

        # 멤버 카운트 캐시 원자적 +1 & refresh
        Challenge.objects.filter(pk=challenge.pk).update(
            member_count_cache=F("member_count_cache") + 1
        )
        challenge.refresh_from_db(fields=["member_count_cache"])

        # 초대코드 생성 (챌린지 생성 직후)
        invite = generate_invite_code_for_challenge(challenge=challenge)
        # 나중에 응답 시 추가 쿼리 없이 쓰기 위해 인스턴스에 달아둠
        setattr(challenge, "_created_invite_code", invite)

        return challenge



class ChallengeCreateOutSerializer(serializers.ModelSerializer):
    # 모델 → API 응답 매핑 (키 이름 맞춤)
    subtitle = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, required=False, allow_blank=True)
    challenge_id = serializers.IntegerField(source="id", read_only=True)
    creator_id = serializers.IntegerField(source="owner_id", read_only=True)
    category_id = serializers.IntegerField(read_only=True)

    # 빈도/정산/AI 문구/상태 등 변환
    freq_type = serializers.SerializerMethodField(allow_null=True)
    freq_n_days = serializers.IntegerField(allow_null=True)
    ai_condition_text = serializers.CharField(source="ai_condition")
    settlement_method = serializers.SerializerMethodField()
    invite_code = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = (
            "challenge_id", "creator_id", "category_id",
            "title", "description", "subtitle", "cover_image",
            "entry_fee", "duration_weeks",
            "freq_type", "freq_n_days",
            "ai_condition_text", "settlement_method",
            "status", "start_date", "end_date",
            "invite_code",
            "created_at", "updated_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("description"):
            data["description"] = data.get("subtitle") or ""
        return data

    def get_cover_image(self, obj):
        # 파일이 없으면 null
        if not getattr(obj, "cover_image", None):
            return None
        try:
            url = obj.cover_image.url  # "/media/..." 상대경로
        except Exception:
            return None

        # request가 있으면 절대 URL로 빌드
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
    
    # 모델에는 description 필드가 없으므로, 안전하게 빈 문자열로 처리
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "description" not in data or data["description"] is None:
            data["description"] = ""  # 스펙에 맞춘 자리 채우기 (명세상 필드 존재)
        return data

    # 모델 한글 ↔ API 영문
    def get_freq_type(self, obj):
        mapper = ChallengeCreateSerializer.FREQ_OUT_MAP
        return mapper.get(obj.freq_type, "DAILY")

    def get_settlement_method(self, obj):
        # 런타임에 모델 상수 접근 (안전)
        if obj.settle_method == Challenge.SettleMethod.PROPORTIONAL:
            return "PROPORTIONAL"
        # 현재는 PROPORTIONAL만 지원 -> 혹시 모르는 값은 기본값으로 통일
        return "PROPORTIONAL"

    # 모델에는 description 필드가 없으므로, 안전하게 빈 문자열로 처리
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "description" not in data or data["description"] is None:
            data["description"] = ""  # 스펙에 맞춘 자리 채우기 (명세상 필드 존재)
        return data

    # 모델 한글 ↔ API 영문
    def get_freq_type(self, obj):
        mapper = ChallengeCreateSerializer.FREQ_OUT_MAP
        return mapper.get(obj.freq_type, "DAILY")

    def get_settlement_method(self, obj):
        # 런타임에 모델 상수 접근 (안전)
        if obj.settle_method == Challenge.SettleMethod.PROPORTIONAL:
            return "PROPORTIONAL"
        # 현재는 PROPORTIONAL만 지원 -> 혹시 모르는 값은 기본값으로 통일
        return "PROPORTIONAL"

    def get_invite_code(self, obj):
        """
        응답에 포함할 초대코드 정보 구성
        - 생성 직후에는 obj._created_invite_code 사용
        - 그 외에는 DB에서 가장 최근 초대코드를 조회
        """
        invite = getattr(obj, "_created_invite_code", None)
        if invite is None:
            invite = (
                InviteCode.objects.filter(challenge=obj)
                .order_by("-created_at")
                .first()
            )
        if not invite:
            return None

        return {
            "code": invite.code,
            "expires_at": invite.expires_at,
            "case_sensitive": True,
        }





class ChallengeJoinSerializer(serializers.Serializer):
    """참가 요청 입력 값 (선택 동의값 등)"""
    agree_terms = serializers.BooleanField(required=False, default=False)


class ChallengeJoinOutSerializer(serializers.Serializer):
    """참가 성공 응답 스펙 (API 명세서와 동일 키)"""
    challenge_member_id = serializers.IntegerField()
    challenge_id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    role = serializers.CharField()
    joined_at = serializers.DateTimeField()
    entry_fee_charged = serializers.IntegerField()
    user_point_balance_after = serializers.IntegerField()
    message = serializers.CharField()



# 챌린지 종료 응답용 시리얼라이저
class ChallengeSettlementInfoSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField()
    status = serializers.CharField()


class ChallengeEndResponseSerializer(serializers.Serializer):
    challenge_id = serializers.IntegerField()
    status = serializers.CharField()
    ended_at = serializers.DateTimeField()
    settlement = ChallengeSettlementInfoSerializer()







class ChallengeRuleUpdateSerializer(serializers.Serializer):
    """
    PATCH /challenges/{challenge_id}/rules 요청용 입력 스키마
    - 부분 업데이트 가능
    - freq_type / freq_n_days / ai_condition_text 중 일부만 보내도 됨
    """
    # API에서 사용하는 영문 코드 기준
    freq_type = serializers.ChoiceField(
        choices=["DAILY", "WEEKDAYS", "WEEKENDS", "N_DAYS_PER_WEEK"],
        required=False,
    )
    freq_n_days = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=6,
    )
    ai_condition_text = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        """
        - freq_type, freq_n_days가 함께/단독으로 들어와도 규칙을 지키도록 검증
        - challenge 현재 상태까지 고려해서 N_DAYS_PER_WEEK 규칙 체크
        """
        challenge = self.context["challenge"]  # view에서 넣어줄 것

        # 최종적으로 적용될 freq_type(모델 값: "매일", "평일", "주말", "주 N일")
        if "freq_type" in attrs:
            # API → 모델 매핑 재사용
            target_freq_type_model = ChallengeCreateSerializer.FREQ_IN_MAP[attrs["freq_type"]]
        else:
            target_freq_type_model = challenge.freq_type

        # 최종적으로 적용될 freq_n_days
        if "freq_n_days" in attrs:
            target_freq_n_days = attrs["freq_n_days"]
        else:
            target_freq_n_days = challenge.freq_n_days

        # 규칙 1) 주 N일인 경우 freq_n_days 반드시 필요
        if target_freq_type_model == "주 N일":
            if target_freq_n_days is None:
                raise serializers.ValidationError({
                    "freq_n_days": "freq_type이 N_DAYS_PER_WEEK인 경우 1~6 사이 정수를 반드시 보내야 합니다."
                })

        # 규칙 2) 주 N일이 아닌데 freq_n_days를 보내면 안 됨
        if target_freq_type_model != "주 N일":
            # attrs에 명시적으로 freq_n_days가 들어온 경우만 검사
            if "freq_n_days" in attrs and attrs["freq_n_days"] not in (None,):
                raise serializers.ValidationError({
                    "freq_n_days": "이 freq_type에서는 freq_n_days를 보내지 않습니다."
                })

        return attrs


class ChallengeRuleUpdateOutSerializer(serializers.Serializer):
    """
    PATCH /challenges/{challenge_id}/rules 응답 스키마
    API 명세서의 정상 응답 형식과 동일
    """
    challenge_id = serializers.IntegerField()
    freq_type = serializers.CharField()
    freq_n_days = serializers.IntegerField(allow_null=True)
    ai_condition_text = serializers.CharField()
    updated_at = serializers.DateTimeField()



class InviteCodeJoinInSerializer(serializers.Serializer):
    """
    POST /invites/join 요청용 입력 스키마
    {
      "invite_code": "challink_XXXXXX"
    }
    """
    invite_code = serializers.CharField()

    def validate_invite_code(self, value):
        code = value.strip()
        if not code:
            raise serializers.ValidationError("invite_code는 비어 있을 수 없습니다.")
        return code


class InviteCodeJoinOutSerializer(serializers.Serializer):
    """
    초대코드 검증 결과 응답 스키마
    - 이미 참여: 최소 정보 + already_joined, can_join, message
    - 아직 미참여: 챌린지 상세 정보 + already_joined, can_join, message
    """
    challenge_id = serializers.IntegerField()
    challenge_title = serializers.CharField()
    challenge_description = serializers.CharField(required=False, allow_blank=True)
    entry_fee = serializers.IntegerField(required=False)
    duration_weeks = serializers.IntegerField(required=False)
    freq_type = serializers.CharField(required=False, allow_null=True)
    freq_n_days = serializers.IntegerField(required=False, allow_null=True)
    ai_condition_text = serializers.CharField(required=False, allow_blank=True)
    settlement_method = serializers.CharField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)

    already_joined = serializers.BooleanField()
    can_join = serializers.BooleanField()
    challenge_member_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField()

