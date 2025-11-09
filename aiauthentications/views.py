from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from challenges.models import Challenge, ChallengeMember, CompleteImage
from .serializers import AIVerifyImageSerializer
from .gemini_service import judge_image

# 로컬 중복 판정 유틸 (동일 파일 / pHash 유사)
from .utils.image_hashing import calc_sha1, calc_phash, hamming_distance64

PHASH_THRESHOLD = 6  # pHash 해밍거리 임계값(권장 6~8 사이 조정)


class ChallengeAIVerifyLiteView(APIView):
    """
    POST /aiauth/<int:challenge_id>/auth
    - 이미지 1장 업로드 후, Challenge.ai_condition 기준으로 승인/반려 판정
    - 업로드 즉시 CompleteImage(pending) 생성 → AI 결과 반영
    - 응답: {challenge_id, user_id, upload_date, approved, reasons[], complete_image{...}, raw_ai_response}
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

        # ─────────────────────────────────────────────────────────────────
        # [A-1] 동일 파일(SHA-1) 즉시 차단
        # ─────────────────────────────────────────────────────────────────
        try:
            file_sha1 = calc_sha1(file)
        except Exception as e:
            return Response({"detail": f"Hash error: {e}"}, status=400)

        # 같은 유저가 동일 파일 업로드 → 즉시 반려
        if CompleteImage.objects.filter(user=request.user, file_sha1=file_sha1).exists():
            return Response({
                "challenge_id": challenge_id,
                "user_id": request.user.id,
                "approved": False,
                "reasons": ["Duplicate upload: identical file (SHA-1 match)"],
                "raw_ai_response": None,
                "complete_image": None
            }, status=200)

        # 5) 먼저 pending 객체 생성(업로드 기록 보존)
        ci = CompleteImage.objects.create(
            challenge_member=cm,
            user=request.user,
            image=file,
            status=CompleteImage.Status.PENDING,
            date=timezone.localdate(),
            file_sha1=file_sha1,               # ← 저장
        )

        # ─────────────────────────────────────────────────────────────────
        # [A-2] pHash 계산 및 같은 챌린지 내 유사 보류(flagged_duplicate)
        # ─────────────────────────────────────────────────────────────────
        phash_val = None
        try:
            # 저장된 파일 핸들 기준으로 pHash 계산
            phash_val = calc_phash(ci.image)
            ci.phash = phash_val
            ci.save(update_fields=["phash"])
        except Exception:
            phash_val = None  # pHash 실패는 치명적 아님

        flagged = False
        similar_ids = []
        if phash_val is not None:
            # 같은 챌린지의 기존 pHash들과 해밍거리 비교 (최근 N개로 제한 가능)
            candidates = (
                CompleteImage.objects
                .filter(challenge_member__challenge_id=challenge_id, phash__isnull=False)
                .exclude(id=ci.id)
                .only("id", "phash")[:500]
            )
            for other in candidates:
                if hamming_distance64(phash_val, other.phash) <= PHASH_THRESHOLD:
                    flagged = True
                    similar_ids.append(other.id)
                    if len(similar_ids) >= 3:  # 충분하면 중단해도 됨
                        break

        if flagged:
            # 보수적 운영: 보류 플래그만 세우고 최종 상태는 AI/사람 검수로 결정
            ci.flagged_duplicate = True
            ci.save(update_fields=["flagged_duplicate"])

        # 6) AI 판정
        verdict = judge_image(ch.ai_condition or "", file)

        approved = bool(verdict.get("approved"))
        reasons = verdict.get("reasons") or []
        uncertain = bool(verdict.get("uncertain"))
        raw_resp = verdict.get("raw")

        # 유사 보류를 응답 사유에 표시(원하면 비활성화해도 됨)
        if ci.flagged_duplicate and "Possible duplicate (pHash)" not in reasons:
            reasons = ["Possible duplicate (pHash)"] + reasons

        # 7) 상태 결정
        if uncertain:
            ci.status = CompleteImage.Status.PENDING
            ci.reviewed_at = None
        else:
            ci.status = CompleteImage.Status.APPROVED if approved else CompleteImage.Status.REJECTED
            ci.reviewed_at = timezone.now()

        ci.review_reasons = "\n".join(reasons)
        ci.save(update_fields=["status", "reviewed_at", "review_reasons"])

        # 8) 응답
        body = {
            "challenge_id": ch.id,
            "user_id": request.user.id,
            "upload_date": str(ci.date),
            "approved": approved,
            "reasons": reasons,
            "raw_ai_response": raw_resp,
            "complete_image": {
                "id": ci.id,
                "image_url": getattr(ci.image, "url", None),
                "status": ci.status,
                "created_at": ci.created_at,
                "reviewed_at": ci.reviewed_at,
                "flagged_duplicate": getattr(ci, "flagged_duplicate", False),
                "similar_example_ids": similar_ids,  # 참고용
            },
        }
        return Response(body, status=200)