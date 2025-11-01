# challenges/urls.py
from django.urls import path
from .views import (
    ChallengeListView,
    MyChallengeListView,
    MyCompletedChallengeListView,
    ChallengeDetailView,
)

urlpatterns = [
    path("", ChallengeListView.as_view()),                 # GET /challenges/
    path("my/", MyChallengeListView.as_view()),            # GET /challenges/my/
    path("my/completed", MyCompletedChallengeListView.as_view()),  # GET /challenges/my/completed
    path("<int:challenge_id>/", ChallengeDetailView.as_view()),    # GET /challenges/{id}/
]
