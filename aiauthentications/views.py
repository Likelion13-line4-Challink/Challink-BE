from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from challenges.models import Challenge, ChallengeMember, CompleteImage
from .serializers import AIVerifyImageSerializer
from .gemini_service import judge_image


class ChallengeAIVerifyLiteView(APIView):
    """
    POST /aiauth/<int:challenge_id>/auth
    - 이미지 1장 업로드 후, Challenge.ai_condition 기준으로 승인/반려 판정
    - 업로드 즉시 CompleteImage(pending) 생성 → AI 결과 반영
    - 응답: {challenge_id, user_id, upload_date, approved, reasons[], complete_image{...}}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, challenge_id: int):
        # 1) 요청 검증 (이미지 필수)
        ser = AIVerifyImageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # 2) 챌린지 로드
        try:
            ch = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return Response({"detail": "Challenge not found."}, status=404)

        # 3) 챌린지 멤버십 확인
        try:
            cm = ChallengeMember.objects.get(challenge_id=challenge_id, user=request.user)
        except ChallengeMember.DoesNotExist:
            return Response({"detail": "User is not a member of this challenge."}, status=400)

        # 4) 파일 추출
        file = ser.validated_data["image"]

        # 5) 먼저 pending 객체 생성(업로드 기록 보존)
        ci = CompleteImage.objects.create(
            challenge_member=cm,
            user=request.user,
            image=file,
            status=CompleteImage.Status.PENDING,
            date=timezone.localdate(),
        )

        # 6) AI 판정 (예외가 나도 서비스 내부에서 False/uncertain로 수습)
        verdict = judge_image(ch.ai_condition or "", file)

        approved = bool(verdict.get("approved"))
        reasons = verdict.get("reasons") or []
        uncertain = bool(verdict.get("uncertain"))

        # ✅ 상태 결정 규칙: 불확실하면 pending 유지
        if uncertain:
            ci.status = CompleteImage.Status.PENDING
            ci.reviewed_at = None
        else:
            ci.status = CompleteImage.Status.APPROVED if approved else CompleteImage.Status.REJECTED
            ci.reviewed_at = timezone.now()

        ci.review_reasons = "\n".join(reasons)
        ci.save(update_fields=["status", "reviewed_at", "review_reasons"])

        # 8) 표준 응답
        body = {
            "challenge_id": ch.id,
            "user_id": request.user.id,
            "upload_date": str(ci.date),
            "approved": approved,
            "reasons": reasons,
            "complete_image": {
                "id": ci.id,
                "image_url": getattr(ci.image, "url", None),
                "status": ci.status,
                "created_at": ci.created_at,
                "reviewed_at": ci.reviewed_at,
            },
        }
        return Response(body, status=200)
