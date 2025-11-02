from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .serializers import (
     CompleteImageDetailSerializer,
     CompleteImageListSerializer,
     CommentSerializer,
     CommentCreateSerializer,
)
from .selectors import (
     get_complete_image_with_comments,
     get_challenge_images,
)
from .services import create_comment


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
