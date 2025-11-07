# challenges/urls.py
from django.urls import path
from .views import *

from .views import MyChallengeListView, MyCompletedChallengeListView, \
    ChallengeDetailView, CompleteImageDetailView, CommentCreateView, ChallengeCreateView


urlpatterns = [
    # 목록/생성 분리
    path("list/", ChallengeListView.as_view(), name="challenge-list"),   # GET 전용
    path("",      ChallengeCreateView.as_view(), name="challenge-create"),  # POST 전용

    path("my/", MyChallengeListView.as_view()),                           # GET /challenges/my/
    path("my/completed/", MyCompletedChallengeListView.as_view()),        # GET /challenges/my/completed/

    path("<int:challenge_id>/images/", ChallengeImageListView.as_view()), # GET /challenges/{id}/images/
    path("<int:challenge_id>/", ChallengeDetailView.as_view()),           # GET /challenges/{id}/

    # 기록 사진 상세 / 댓글
    path("detail/<int:photo_id>/", CompleteImageDetailView.as_view()),
    path("detail/<int:photo_id>/comments/", CommentCreateView.as_view()),
    
    path("<int:challenge_id>/albums/", ChallengeImageListView.as_view()),
]