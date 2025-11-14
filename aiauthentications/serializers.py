from rest_framework import serializers

class AIVerifyImageSerializer(serializers.Serializer):
     """
     image: 사용자 업로드 이미지 (1장 필수)
     """
     image = serializers.ImageField()