import os, json
from dotenv import load_dotenv
from PIL import Image
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# 텍스트 전용 모델 (테스트중)
MODEL_ID = "models/gemini-2.0-flash-lite"  # or "models/gemini-flash-lite-latest"
_model = genai.GenerativeModel(MODEL_ID)

_PROMPT = (
     "Judge PASS/FAIL for this photo using RULES.\n"
     "Return strict JSON only: {\"approved\": true/false, \"reasons\": [string]}\n"
     "RULES:\n{rules}"
)

def _preprocess_image(pil: Image.Image) -> Image.Image:
     """토큰/용량 절약: 긴 변 1024px로 축소, JPEG로 재인코딩."""
     pil = pil.convert("RGB")
     pil.thumbnail((1024, 1024))        # 비율 유지 축소
     buf = io.BytesIO()
     pil.save(buf, format="JPEG", quality=80, optimize=True)
     buf.seek(0)
     # PIL Image로 다시 로드해서 SDK에 전달
     return Image.open(buf)

def judge_image(ai_condition: str, pil_image: Image.Image) -> dict:
     """
     입력: ai_condition(규칙 문자열), PIL 이미지 1장
     출력: {"approved": bool, "reasons": [...]}  # 실패시만 reasons 채움
     """
     if _MODEL is None:
          # 모델이 아예 생성 불가(의존성/버전/권한)일 때의 안전 응답
          return {
               "approved": False,
               "reasons": ["Image model unavailable on this project. (quota or model access)"]
          }

     img = _preprocess_image(pil_image)

     prompt = _PROMPT.format(rules=ai_condition or "")

     resp = _MODEL.generate_content(
          [prompt, img],
          generation_config={
               "temperature": 0.0,
               "max_output_tokens": 64,
               "response_mime_type": "application/json",
          },
     )

     # 모델이 JSON만 내도록 강제했지만 혹시 대비
     try:
          data = json.loads((resp.text or "").strip())
     except Exception:
          data = {"approved": False, "reasons": ["Non-JSON response from model."]}

     # reasons는 실패시에만 필요하지만, 포맷 안정성을 위해 기본값 제공
     if data.get("approved") is True:
          data.setdefault("reasons", [])
     else:
          if not isinstance(data.get("reasons"), list):
               data["reasons"] = ["Did not meet the rules."]
     return data