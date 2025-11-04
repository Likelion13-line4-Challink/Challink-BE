# challenges/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path("", ChallengeListView.as_view()),                 # GET /challenges/
    path("my/", MyChallengeListView.as_view()),            # GET /challenges/my/
    path("my/completed/", MyCompletedChallengeListView.as_view()),  # GET /challenges/my/completed/
    path("<int:challenge_id>/", ChallengeDetailView.as_view()),    # GET /challenges/{id}/
    # 기록 사진 상세 조회
    path("detail/<int:photo_id>/", CompleteImageDetailView.as_view()),
    # 댓글 작성
    path("detail/<int:photo_id>/comments/", CommentCreateView.as_view()),
    # 기록 사진 목록
    path("<int:challenge_id>/", ChallengeImageListView.as_view()),
]
