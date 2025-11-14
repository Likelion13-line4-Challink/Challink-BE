from rest_framework import serializers
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Profile, PointHistory
from challenges.models import ChallengeMember   # /users/me/ 집계용

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = Profile
        fields = ("id", "name", "email", "password", "password_confirm", "point_balance", "created_at")
        read_only_fields = ("id", "point_balance", "created_at")

    def validate_email(self, value: str) -> str:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError({"code": "INVALID_EMAIL", "message": "이메일 형식이 잘못되었습니다."})
        return Profile.objects.normalize_email(value)

    def validate(self, attrs):
        pwd = attrs.get("password", "")
        pwd2 = attrs.pop("password_confirm", "")
        if pwd != pwd2:
            raise serializers.ValidationError({"code": "INVALID_INPUT", "message": "비밀번호가 일치하지 않습니다."})
        if len(pwd) < 8 or (not any(c.isalpha() for c in pwd)) or (not any(c.isdigit() for c in pwd)):
            raise serializers.ValidationError({"code": "INVALID_INPUT", "message": "비밀번호는 8자 이상 + 영문, 숫자 포함"})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = Profile.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """ 로그인 입력 검증용 """
    email = serializers.EmailField()
    password = serializers.CharField()
    remember_id = serializers.BooleanField(required=False, default=False)


class MeSerializer(serializers.ModelSerializer):
    """ /users/me/ 응답용 """
    completed_challenges_count = serializers.SerializerMethodField()   # 내가 속한 챌린지 중 status='ended' 개수

    class Meta:
        model = Profile
        fields = (
            "id",
            "name",
            "email",
            "point_balance",
            "completed_challenges_count",
            "created_at",
            "updated_at",
        )

    def get_completed_challenges_count(self, obj: Profile) -> int:
        return ChallengeMember.objects.filter(user=obj, challenge__status="ended").count()


class PointHistorySerializer(serializers.ModelSerializer):
    history_id = serializers.IntegerField(source="point_history_id")
    type = serializers.CharField(source="get_type_display")  # 충전/참가/보상
    title = serializers.SerializerMethodField()

    class Meta:
        model = PointHistory
        fields = (
            "history_id",
            "type",
            "title",
            "amount",
            "balance_after",
            "challenge_id",
            "occurred_at",
        )

    def get_title(self, obj):
        # description이 비어있지 않으면 그대로 사용
        # 없으면 challenge 제목 fallback
        if obj.description:
            return obj.description
        if obj.challenge:
            return obj.challenge.title
        return "포인트 내역"
