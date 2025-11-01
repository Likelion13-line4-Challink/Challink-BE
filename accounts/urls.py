from django.urls import path
from .views import SignupView, CheckEmailView, LoginView, LogoutView, MeView, WalletHistoryView

urlpatterns = [
    path("auth/signup/", SignupView.as_view()),
    path("auth/check-email/", CheckEmailView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("users/me/", MeView.as_view()),
    path("wallet/history/", WalletHistoryView.as_view()),
]
