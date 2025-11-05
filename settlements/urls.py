from django.urls import path
from .views import RewardStatusView, RewardClaimView

urlpatterns = [
    path("<int:challenge_id>/rewards", RewardStatusView.as_view()),
    path("<int:challenge_id>/rewards/claim", RewardClaimView.as_view()),
]
