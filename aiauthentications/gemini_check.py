import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("=== Available models ===")
print("\n".join(m.name for m in genai.list_models()))

# ✅ 여기만 바꿔주세요
MODEL_ID = "gemini-2.0-flash-lite"  # 안되면 아래 두 개 중 하나로
# MODEL_ID = "gemini-2.0-flash-lite-001"
# MODEL_ID = "gemini-flash-lite-latest"

model = genai.GenerativeModel(MODEL_ID)
resp = model.generate_content("Say 'connected' if you can read this.")
print("=== Model:", MODEL_ID, "===")
print(resp.text)
