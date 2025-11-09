# aiauthentications/gemini_service.py
from google import genai
import os, json, re, base64, io, mimetypes, logging
from PIL import Image

logger = logging.getLogger(__name__) 
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

MODELS = ["gemini-2.0-flash-lite"]
# 우선 정식→프리뷰 순으로 재시도
# MODELS = ["gemini-2.5-flash-image", "gemini-2.5-flash-image-preview"]

# 관대해진 프롬프트
PROMPT = (
    "Return STRICT JSON ONLY with keys exactly: approved (boolean), reasons (array of strings). "
    "No prose, no markdown, no code fences.\n"
    "RULES:\n{rules}\n"  # ← 이건 그대로 둠
    "If the image seems to satisfy the rules but the decision is ambiguous or the description is slightly unclear, "
    "you MUST set approved to true and set reasons to an empty array.\n"
    "Only when the image clearly violates the rules, set approved to false and give specific reasons.\n"
    'EXAMPLES:\n'
    'PASS => {{"approved": true, "reasons": []}}\n'   # ← { 를 {{ 로
    'FAIL => {{"approved": false, "reasons": ["V sign not visible"]}}\n'  # ← 여기도
)

UNCERTAIN_REASON = "AI 판정 결과를 확실히 해석하지 못했습니다. 다시 시도하거나 수동 검토가 필요합니다."
NON_JSON_REASON = "AI 응답이 올바른 JSON 형식이 아닙니다."
EMPTY_RESP_REASON = "AI 응답이 비어 있습니다."
INVALID_JSON_REASON = "AI 응답 구조가 올바르지 않습니다."

def _resize_to_b64_inline(uploaded_file) -> dict:
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

def _normalize_raw_keys(raw: str) -> str:
    if not raw:
        return raw
    for k in ("approved","approve","result","pass","reasons","reason","why","notes"):
        raw = raw.replace(f'\\"{k}\\"', f'"{k}"')
    return raw

def _norm_keys(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(k, str):
            kk = k.strip().strip('\'"').strip().lower()
        else:
            kk = k
        out[kk] = v
    return out

def _get_bool_like(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true","yes","y","1","pass","passed","ok","approve","approved"):
            return True
        if s in ("false","no","n","0","fail","failed","reject","rejected"):
            return False
    return None

_APPROVED_RE = re.compile(
    r'(?:\\?"?approved\\?"?|\\?"?result\\?"?|\\?"?pass\\?"?)\s*:\s*(true|false|"true"|"false"|1|0)', re.I,
)
_REASONS_RE = re.compile(
    r'(?:\\?"?reasons\\?"?|\\?"?reason\\?"?|\\?"?why\\?"?|\\?"?notes\\?"?)\s*:\s*(\[[^\]]*\])', re.S | re.I,
)

def _fallback_from_raw(raw: str) -> dict | None:
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
    return {"approved": approved, "reasons": reasons, "uncertain": True}

def judge_image(ai_condition: str, uploaded_file) -> dict:
    raw = ""
    try:
        # 0) 이미지 준비
        try:
            image_part = _resize_to_b64_inline(uploaded_file)
        except Exception as e:
            logger.exception("image resize/b64 실패")
            return {
                "approved": False,
                "reasons": ["유효하지 않은 이미지입니다."],
                "uncertain": True,
                "raw": raw,
            }

        prompt = PROMPT.format(rules=ai_condition or "")
        logger.debug("gemini prompt = %s", prompt)

        # 1) 모델 이중 시도
        res = None
        for model_name in MODELS:
            try:
                tmp = client.models.generate_content(
                    model=model_name,
                    contents=[{"role": "user", "parts": [{"text": prompt}, image_part]}],
                    config={
                        "temperature": 0.0,
                        "max_output_tokens": 96,
                        "response_mime_type": "application/json",
                        "response_schema": {
                            "type": "OBJECT",
                            "properties": {
                                "approved": {"type": "BOOLEAN"},
                                "reasons":  {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["approved", "reasons"],
                        },
                    },
                )
                res = tmp
                logger.debug("gemini response from %s = %r", model_name, res)
                break
            except Exception:
                logger.exception("gemini 호출 실패(model=%s)", model_name)

        if res is None:
            logger.error("gemini 응답 없음 (두 모델 모두 실패)")
            return {
                "approved": False,
                "reasons": ["AI 서비스에 일시적 문제가 있습니다."],
                "uncertain": True,
                "raw": raw,
            }

        # 2) 응답에서 텍스트 뽑기 (1차: 편의 필드)
        raw = (getattr(res, "text", None) or getattr(res, "output_text", None) or "").strip()
        logger.debug("gemini raw(text/output_text) = %r", raw)

        # 3) 응답에서 텍스트 뽑기 (2차: candidates -> parts)
        if not raw:
            try:
                candidates = getattr(res, "candidates", None) or []
                parts = getattr(candidates[0].content, "parts", []) if candidates else []
                raw = "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()
                logger.debug("gemini raw(from candidates.parts) = %r", raw)
            except Exception:
                logger.exception("candidates.parts 에서 텍스트 추출 실패")

        if not raw:
            logger.error("gemini 응답이 비어 있음")
            return {
                "approved": False,
                "reasons": [EMPTY_RESP_REASON],
                "uncertain": True,
                "raw": raw,
            }

        # 4) 키 정규화 후 JSON 파싱
        raw = _normalize_raw_keys(raw)
        logger.debug("normalized raw = %r", raw)

        try:
            data = _json_only(raw)
            logger.debug("parsed json = %r", data)
        except Exception:
            logger.exception("json 파싱 실패, fallback 시도")
            fb = _fallback_from_raw(raw)
            if fb:
                fb["raw"] = raw
                return fb
            return {
                "approved": False,
                "reasons": [NON_JSON_REASON],
                "uncertain": True,
                "raw": raw,
            }

        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else None
        if not isinstance(data, dict):
            logger.error("json은 있었으나 dict 형태가 아님: %r", data)
            fb = _fallback_from_raw(raw)
            if fb:
                fb["raw"] = raw
                return fb
            return {
                "approved": False,
                "reasons": [INVALID_JSON_REASON],
                "uncertain": True,
                "raw": raw,
            }

        data = _norm_keys(data)
        logger.debug("normalized keys = %r", data)

        approved_raw = (
          data.get("approved")
          if "approved" in data
          else data.get("approve")
          if "approve" in data
          else data.get("result")
          if "result" in data
          else data.get("pass")
          )
        reasons_raw = (
            data.get("reasons") or data.get("reason") or data.get("why") or data.get("notes")
        )

        approved = _get_bool_like(approved_raw)
        if approved is None:
            logger.warning("approved 값을 해석하지 못해 통과로 처리함. approved_raw=%r", approved_raw)
            return {
                "approved": True,
                "reasons": [],
                "uncertain": False,
                "raw": raw,
            }

        if approved:
            reasons = []
        else:
            if isinstance(reasons_raw, list):
                reasons = [str(r) for r in reasons_raw if str(r).strip()]
            elif reasons_raw:
                reasons = [str(reasons_raw)]
            else:
                reasons = ["Did not meet the rules."]

        return {
            "approved": approved,
            "reasons": reasons,
            "uncertain": False,
            "raw": raw,
        }

    except Exception:
        logger.exception("judge_image 전체 예외 발생")
        fb = _fallback_from_raw(raw)
        if fb:
            fb["raw"] = raw
            return fb
        return {
            "approved": False,
            "reasons": [UNCERTAIN_REASON],
            "uncertain": True,
            "raw": raw,
        }
