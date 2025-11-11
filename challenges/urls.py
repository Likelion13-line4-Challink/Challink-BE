from tkinter.font import names

from django.urls import path
from .views import *

from .views import (
    ChallengeListCreateView,
    MyChallengeListView, MyCompletedChallengeListView,
    ChallengeDetailView, CompleteImageDetailView, CommentCreateView,
    ChallengeImageListView, ChallengeJoinView, ChallengeEndView,
)


urlpatterns = [
    path("", ChallengeListCreateView.as_view(), name="challenges"),   # GET/POST /challenges/

    path("my/", MyChallengeListView.as_view()),                           # GET /challenges/my/
    path("my/completed/", MyCompletedChallengeListView.as_view()),        # GET /challenges/my/completed/

    path("<int:challenge_id>/images/", ChallengeImageListView.as_view()), # GET /challenges/{id}/images/
    path("<int:challenge_id>/", ChallengeDetailView.as_view()),           # GET /challenges/{id}/

    # 기록 사진 상세 / 댓글
    path("detail/<int:photo_id>/", CompleteImageDetailView.as_view()),
    path("detail/<int:photo_id>/comments/", CommentCreateView.as_view()),

    path("<int:challenge_id>/join/", ChallengeJoinView.as_view(), name="challenge-join"), # POST
    
    path("<int:challenge_id>/albums/", ChallengeImageListView.as_view()),

    path("<int:challenge_id>/rules/", ChallengeRuleUpdateView.as_view(), name="challenge-rule-update"),

    path("<int:challenge_id>/end/", ChallengeEndView.as_view(), name="challenge-end"),
]