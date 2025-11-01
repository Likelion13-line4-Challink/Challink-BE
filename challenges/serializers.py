from rest_framework import serializers
from .models import CompleteImage, Comment

from rest_framework import serializers
from .models import Challenge, ChallengeMember, ChallengeCategory

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
            "subtitle", "ai_condition_text", "category",
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
    # TODO: 추후 사용자/썸네일 연동 시 실제 데이터로 대체
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


class ChallengeDetailForMemberSerializer(serializers.ModelSerializer):
    # 참여 중(진행 화면)
    category = CategoryMiniSerializer()
    progress_summary = ProgressSummarySerializer()
    participants = ParticipantMiniSerializer(many=True)
    my_membership = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = (
            "id", "title", "entry_fee", "duration_weeks", "freq_type",
            "category", "status", "start_date", "end_date",
            "member_count", "member_limit",
            "progress_summary", "participants",
            "my_membership", "settlement_note",
        )

    def get_my_membership(self, obj):
        mm = getattr(obj, "__my_member__", None)
        if not mm:
            return {"is_joined": False}
        return {
            "is_joined": True,
            "challenge_member_id": mm.id,
            "role": mm.role,
            "joined_at": mm.joined_at,
        }

    def get_member_count(self, obj):
        return getattr(obj, "member_count_cache", 0)
