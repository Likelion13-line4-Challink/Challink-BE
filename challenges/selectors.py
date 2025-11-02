from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from .models import CompleteImage, Comment
from accounts.models import Profile


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
