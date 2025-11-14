from django.urls import path
from .views import RewardStatusView, RewardClaimView, WalletChargeView

urlpatterns = [
    path("<int:challenge_id>/rewards/", RewardStatusView.as_view()),
    path("<int:challenge_id>/rewards/claim/", RewardClaimView.as_view()),

    # 지갑 충전
    path("wallet/charge/", WalletChargeView.as_view()),
]
