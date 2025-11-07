from rest_framework import serializers
from .models import CompleteImage, Comment, Challenge, ChallengeCategory

from django.utils.translation import gettext_lazy as _



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


class CompleteImageListSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

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
            "duration_weeks", "freq_type", "entry_fee",
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
            "entry_fee", "duration_weeks", "freq_type",
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


class ChallengeDetailForMemberSerializer(serializers.Serializer):
    # 참여 중(진행 화면)
    id = serializers.IntegerField()
    title = serializers.CharField()
    entry_fee = serializers.IntegerField()
    duration_weeks = serializers.IntegerField()
    freq_type = serializers.CharField()
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







class ChallengeCreateSerializer(serializers.Serializer):
    # API 명세 입력 스키마 (클라이언트가 보내는 키 그대로)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, required=False)
    category_id = serializers.IntegerField()
    cover_image = serializers.URLField(required=False, allow_blank=True)
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

    SUPPORTED_SETTLEMENT_METHODS = {"PROPORTIONAL"}

    # ChoiceField도 같이 줄이기
    settlement_method = serializers.ChoiceField(choices=["PROPORTIONAL"])


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
                "settlement_method": "현재 지원하지 않는 방식입니다. (지원: PROPORTIONAL)"
            })

        return attrs

    def create(self, validated):
        # 카테고리 확인
        try:
            category = ChallengeCategory.objects.get(pk=validated["category_id"])
        except ChallengeCategory.DoesNotExist:
            raise serializers.ValidationError({"category_id": "존재하지 않는 카테고리입니다."})

        # API → 모델 매핑
        freq_type_model = self.FREQ_IN_MAP[validated["freq_type"]]
        method_str = validated["settlement_method"]  # 현재는 PROPORTIONAL만 지원
        if method_str == "PROPORTIONAL":
            settle_model = Challenge.SettleMethod.PROPORTIONAL
        else:
            # 방어적 코드 (실제로는 validate에서 걸러짐)
            raise serializers.ValidationError({"settlement_method": "현재 지원하지 않는 방식입니다. (지원: PROPORTIONAL)"})

        challenge = Challenge.objects.create(
            title=validated["title"],
            subtitle="",
            cover_image=validated.get("cover_image", "") or "",
            entry_fee=validated["entry_fee"],
            duration_weeks=validated["duration_weeks"],
            freq_type=freq_type_model,
            freq_n_days=validated.get("freq_n_days"),
            ai_condition=validated.get("ai_condition_text", "") or "",
            settle_method=settle_model,
            status=validated.get("status", "draft"),
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            category=category,
            owner=self.context["request"].user,  # 생성자 자동 지정(creator)
        )
        return challenge


class ChallengeCreateOutSerializer(serializers.ModelSerializer):
    # 모델 → API 응답 매핑 (키 이름 맞춤)
    description = serializers.CharField(read_only=True, required=False, allow_blank=True)
    challenge_id = serializers.IntegerField(source="id", read_only=True)
    creator_id = serializers.IntegerField(source="owner_id", read_only=True)
    category_id = serializers.IntegerField(read_only=True)

    # 빈도/정산/AI 문구/상태 등 변환
    freq_type = serializers.SerializerMethodField(allow_null=True)
    freq_n_days = serializers.IntegerField(allow_null=True)
    ai_condition_text = serializers.CharField(source="ai_condition")
    settlement_method = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = (
            "challenge_id", "creator_id", "category_id",
            "title", "description", "cover_image",
            "entry_fee", "duration_weeks",
            "freq_type", "freq_n_days",
            "ai_condition_text", "settlement_method",
            "status", "start_date", "end_date",
            "created_at", "updated_at",
        )

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