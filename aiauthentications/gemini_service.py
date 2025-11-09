from google import genai
import os, json, re, base64, io, mimetypes
from PIL import Image

# 환경변수 GOOGLE_API_KEY 사용
CLIENT = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# 이미지 입력 지원 모델 (lite는 이미지 불가)
MODEL = "gemini-2.5-flash-image"  # 안 되면 "gemini-2.5-flash-image-preview"

# 토큰 최소 + JSON 강제 프롬프트
PROMPT = (
    "Return STRICT JSON ONLY with keys exactly: approved (boolean), reasons (array of strings). "
    "No prose, no markdown, no code fences.\n"
    'Example: {"approved": false, "reasons": ["V sign not visible"]}\n'
    "RULES:\n{rules}"
)

def _resize_and_b64(uploaded_file) -> dict:
    """
    업로드 파일을 1024px로 축소 + JPEG 품질 80으로 재인코딩 후 base64 inline 데이터로 변환
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()
    ct = getattr(uploaded_file, "content_type", "") or mimetypes.guess_type(name)[0] or "image/jpeg"

    uploaded_file.seek(0)
    img = Image.open(uploaded_file).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    raw = buf.getvalue()

    b64 = base64.b64encode(raw).decode("utf-8")
    return {"inline_data": {"mime_type": ct, "data": b64}}

def _json_only(s: str):
    """백틱 감싸짐/잡텍스트 섞임 방지하고 JSON만 추출"""
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s).strip()
        s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}\s*$", s, re.S) or re.search(r"\[.*\]\s*$", s, re.S)
        if m:
            return json.loads(m.group(0))
        raise

def _norm_keys(d: dict) -> dict:
    """키에 붙은 따옴표/공백 제거하고 소문자로 통일."""
    out = {}
    for k, v in d.items():
        if isinstance(k, str):
            kk = k.strip().strip('\'"').strip().lower()
        else:
            kk = k
        out[kk] = v
    return out

def _get_bool_like(x):
    """'true'/'false', 'pass'/'fail' 같은 변형도 허용해 bool로 변환."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes", "y", "1", "pass", "passed", "ok", "approve", "approved"):
            return True
        if s in ("false", "no", "n", "0", "fail", "failed", "reject", "rejected"):
            return False
    return None

# ── 비상 백업: 원문에서 approved/reasons를 정규식으로 추출 ─────────────────────
_APPROVED_RE = re.compile(
    r'(?:\\?"?approved\\?"?|\\?"?result\\?"?|\\?"?pass\\?"?)\s*:\s*(true|false|"true"|"false"|1|0)',
    re.I,
)
_REASONS_RE = re.compile(
    r'(?:\\?"?reasons\\?"?|\\?"?reason\\?"?|\\?"?why\\?"?|\\?"?notes\\?"?)\s*:\s*(\[[^\]]*\])',
    re.S | re.I,
)

def _fallback_from_raw(raw: str) -> dict | None:
    """JSON 파싱이 꼬일 때 원문에서 직접 값 추출."""
    if not raw:
        return None
    m = _APPROVED_RE.search(raw)
    if not m:
        return None
    val = m.group(1).strip().strip('"').lower()
    approved = True if val in ("true", "1") else False
    reasons = []
    m2 = _REASONS_RE.search(raw)
    if m2:
        try:
            arr = json.loads(m2.group(1))
            if isinstance(arr, list):
                reasons = [str(x) for x in arr if str(x).strip()]
        except Exception:
            pass
    if approved and reasons:
        reasons = []
    if not approved and not reasons:
        reasons = ["Did not meet the rules."]
    # 백업 파스로 읽었으면 '불확실'로 표시
    return {"approved": approved, "reasons": reasons, "uncertain": True}

def judge_image(ai_condition: str, uploaded_file) -> dict:
    """이미지 1장 + 규칙으로 승인/반려 판단.
    어떤 경우에도 예외를 외부로 던지지 않고 dict 반환.
    반환 스키마: {"approved": bool, "reasons": [str,...], "uncertain": bool}
    """
    raw = ""  # 최후의 백업 파서용
    try:
        # 0) 파일 전처리
        try:
            image_part = _resize_and_b64(uploaded_file)
        except Exception as e:
            return {"approved": False, "reasons": [f"Invalid image: {e}"], "uncertain": True}

        prompt = PROMPT.format(rules=ai_condition or "")

        # 1) 모델 호출 (JSON 강제)
        try:
            res = CLIENT.models.generate_content(
                model=MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}, image_part]}],
                config={
                    "temperature": 0.0,
                    "max_output_tokens": 64,  # 토큰 최소
                    "response_mime_type": "application/json",
                },
            )
        except Exception as e:
            return {"approved": False, "reasons": [f"AI service unavailable: {e}"], "uncertain": True}

        # 2) 텍스트 추출
        raw = (getattr(res, "text", None) or getattr(res, "output_text", None) or "").strip()
        if not raw:
            try:
                parts = getattr(res.candidates[0].content, "parts", [])
                raw = "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()
            except Exception:
                raw = ""

        if not raw:
            return {"approved": False, "reasons": ["Empty response from model."], "uncertain": True}

        # 3) JSON 파싱(초방어)
        try:
            data = _json_only(raw)  # dict/array/str 등 가능
        except Exception:
            # JSON 파싱 실패 → 원문 정규식 백업 시도
            fb = _fallback_from_raw(raw)
            if fb:
                return fb  # uncertain=True
            return {"approved": False, "reasons": ["Non-JSON response from model."], "uncertain": True}

        # 4) 스키마 정규화
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else None
        if not isinstance(data, dict):
            fb = _fallback_from_raw(raw)
            if fb:
                return fb  # uncertain=True
            return {"approved": False, "reasons": ["Invalid JSON structure from model."], "uncertain": True}

        data = _norm_keys(data)

        # 다양한 키 변형 허용
        approved_raw = data.get("approved") or data.get("approve") or data.get("pass") or data.get("result")
        reasons_raw = data.get("reasons") or data.get("reason") or data.get("why") or data.get("notes")

        approved = _get_bool_like(approved_raw)
        if approved is None:
            # 값이 이상하면 백업 시도
            fb = _fallback_from_raw(raw)
            if fb:
                return fb  # uncertain=True
            approved = False

        if approved:
            reasons = []
        else:
            if isinstance(reasons_raw, list):
                reasons = [str(r) for r in reasons_raw if str(r).strip()]
            elif reasons_raw:
                reasons = [str(reasons_raw)]
            else:
                reasons = ["Did not meet the rules."]

        return {"approved": approved, "reasons": reasons, "uncertain": False}

    except Exception as e:
        # 최후의 방어막: 원문에서라도 추출 시도
        fb = _fallback_from_raw(raw)
        if fb:
            return fb  # uncertain=True
        return {"approved": False, "reasons": [f"Internal error: {e}"], "uncertain": True}
