# aiauthentications/urls.py
from django.urls import path
from .views import *

urlpatterns = [
     path("<int:challenge_id>/",  ChallengeAIVerifyLiteView.as_view()),
]
