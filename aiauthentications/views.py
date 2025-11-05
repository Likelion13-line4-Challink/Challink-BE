from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone  # NEW
from django.conf import settings   # NEW
from .serializers import AIVerifyImageSerializer
from .gemini_service import judge_image
from challenges.models import Challenge, ChallengeMember, CompleteImage  # CHANGED
from PIL import Image

class ChallengeAIVerifyLiteView(APIView):
     def post(self, request, challenge_id: int):
          # 0) 인증 필요(미들웨어/permission으로 처리하는 게 정석이지만 여기서도 가드)  # NEW
          if not request.user or not request.user.is_authenticated:   # NEW
               return Response({"detail": "Authentication required."}, status=401)  # NEW

          # 1) 요청 검증(이미지 1장)
          ser = AIVerifyImageSerializer(data=request.data)
          ser.is_valid(raise_exception=True)

          # 2) 챌린지 로드
          try:
               ch = Challenge.objects.get(id=challenge_id)
          except Challenge.DoesNotExist:
               return Response({"detail": "Challenge not found."}, status=404)

          # 3) 이 유저의 챌린지 멤버십 찾기(CompleteImage FK 필요)
          try:
               cm = ChallengeMember.objects.get(challenge_id=challenge_id, user=request.user)  # NEW
          except ChallengeMember.DoesNotExist:
               return Response({"detail": "User is not a member of this challenge."}, status=400)  # NEW

          # 4) 이미지 로드(PIL)
          file = ser.validated_data["image"]
          try:
               pil = Image.open(file)
          except Exception:
               return Response({"detail": "Invalid image file."}, status=400)

          # 5) 먼저 pending 객체 생성
          ci = CompleteImage.objects.create(
               challenge_member=cm,
               user=request.user,
               image=file,
               status=CompleteImage.Status.PENDING,
               date=timezone.localdate(),
          )

          # 6) AI 판정 (토큰 최소 모드)
          try:
               verdict = judge_image(ch.ai_condition or "", pil)
          except Exception as e:
               # AI 장애 시: pending 유지 + 안내  # NEW
               return Response(
                    {
                         "challenge_id": ch.id,
                         "user_id": request.user.id,
                         "upload_date": str(ci.date),
                         "approved": False,
                         "reasons": [f"AI service unavailable: {e}"],
                         "complete_image": {
                         "id": ci.id,
                         "image_url": ci.image.url if hasattr(ci.image, "url") else None,
                         "status": ci.status,
                         "created_at": ci.created_at,
                         "reviewed_at": None,
                         },
                    },
                    status=503
               )

          # 7) 판정 반영(approved/rejected)
          approved = bool(verdict.get("approved"))
          reasons = verdict.get("reasons") or []
          ci.status = CompleteImage.Status.APPROVED if approved else CompleteImage.Status.REJECTED
          ci.reviewed_at = timezone.now()
          ci.review_reasons = "\n".join(reasons)
          ci.save(update_fields=["status", "reviewed_at", "review_reasons"])

          # 8) 응답
          return Response(
               {
                    "challenge_id": ch.id,
                    "user_id": request.user.id,
                    "upload_date": str(ci.date),
                    "approved": approved,
                    "reasons": reasons,
                    "complete_image": {
                         "id": ci.id,
                         "image_url": ci.image.url if hasattr(ci.image, "url") else None,
                         "status": ci.status,
                         "created_at": ci.created_at,
                         "reviewed_at": ci.reviewed_at,
                    },
               },
               status=status.HTTP_200_OK
          )
