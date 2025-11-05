from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import CompleteImage, Comment


# 댓글 작성 서비스 로직
@transaction.atomic
def create_comment(photo_id: int, user, content: str, x_ratio=None, y_ratio=None):
     # 특정 인증 사진에 댓글을 작성 -> comment_count ++
     photo = get_object_or_404(CompleteImage, id=photo_id)

     # 댓글 생성
     comment = Comment.objects.create(
          complete_image=photo,
          user=user,
          content=content,
          x_ratio=x_ratio,
          y_ratio=y_ratio,
     )

     # 댓글 수 증가 (atomic)
     photo.comment_count = photo.comments.filter(is_deleted=False).count()
     photo.save(update_fields=["comment_count"])

     return comment
