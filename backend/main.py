import os
import json
import logging
import uuid
from datetime import datetime
import requests

from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import JSONResponse, FileResponse

from openai import OpenAI
from dotenv import load_dotenv

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.access")

if os.path.exists(".env"):
    load_dotenv()

# CORS 설정
origins = [
    "http://localhost:3000",  # React 개발 서버 주소
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # 쿠키 사용 시 필수
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("OPENAI_API_KEY")
naver_api_client_id = os.getenv("NAVER_API_CLIENT_ID")
naver_api_client_secret = os.getenv("NAVER_API_CLIENT_SECRET")
slack_api_key = os.getenv("SLACK_API_TOKEN")

if not api_key:
    raise EnvironmentError("❌ OPENAI_API_KEY가 설정되지 않았습니다!")
client = OpenAI(api_key=api_key)

def send_slack_alert(message: str):
    payload = {"text": message}
    requests.post(slack_api_key, json=payload)

# ---------------------
# 루트 API: React 프론트에서 호출해 쿠키 세팅용으로 사용
@app.get("/")
async def index(user_id: str | None = Cookie(default=None)):
    response = JSONResponse({"message": "React Frontend 별도 운영"})
    if not user_id:
        new_user_id = str(uuid.uuid4())
        response.set_cookie(key="user_id", value=new_user_id, max_age=60*60*24*30)
        logger.info(f"[LOG] 신규 사용자 방문 | ID: {new_user_id}")
        return response
    else:
        logger.info(f"[LOG] 기존 사용자 방문 | ID: {user_id}")
        return response

# 검색 결과 API도 React에서 화면 담당, 로그 + 쿠키 세팅만
@app.get("/search")
async def search_result(query: str = "", user_id: str | None = Cookie(default=None)):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    response = JSONResponse({"message": "검색 로그 기록됨"})
    new_user = False
    if not user_id:
        user_id = str(uuid.uuid4())
        new_user = True
    logger.info(f"{now} [LOG] 결과창 이동 | query = {query} | 사용자: {user_id}")
    #send_slack_alert(f"/search {query}")
    if new_user:
        response.set_cookie(key="user_id", value=user_id, max_age=60*60*24*30)
    return response

# 질문 리스트 API
@app.get("/api/questions")
async def api_questions():
    path = os.path.join("static", "data-json", "questions.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(data)

# 상품 추천 API
@app.get("/api/products")
async def api_products(query: str = ""):
    path = os.path.join("static", "data-json", "products.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(data)

# 클릭 로깅
@app.post("/log/click")
async def log_click(request: Request, user_id: str | None = Cookie(default="익명")):
    data = await request.json()
    product_name = data.get('product_name', 'Unknown')
    query = data.get('product_query', 'Unknown')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"[LOG] 상세클릭 {now} | {product_name} | {query} | 사용자: {user_id}")
    return Response(status_code=200)

# 404 핸들러는 React에서 처리하므로 FastAPI에선 별도 구현 안 해도 무방

# GPT 채팅 API
@app.post("/chat")
async def chat(request: Request, user_id: str | None = Cookie(default=None)):
    try:
        data = await request.json()
        if not data:
            return JSONResponse({'error': '데이터가 없습니다.'}, status_code=400)

        message = data.get('message', '')
        current_query = data.get('current_query', '')
        conversation_history = data.get('conversation_history', [])

        if not message:
            return JSONResponse({'error': '메시지가 비어있습니다.'}, status_code=400)

        system_content = f"""
            당신은 제품 추천 시스템의 핵심 응답 생성자입니다.  
            ❗당신이 생성하는 응답이 시스템 전체 작동에 영향을 주며, 규칙을 지키지 않으면 사용자에게 오류 메시지가 표시됩니다.  

            따라서 반드시 아래 형식과 지침을 지켜주세요.
            - 응답은 반드시 다음 JSON 형식만 사용해야 합니다.
            - 자연어 문장만 단독으로 응답하면 시스템 오류로 간주됩니다.
            - 필드는 모두 포함해야 하며, 값이 없을 경우 "없음"으로 명시하세요.
            - 절대로 설명이나 주석, 추가 문장은 포함하지 마세요.
            - 결과 메시지는 모두 response안에 담으면 됩니다!

            JSON 응답 형식:
            {{
                "should_search": false,
                "response": "",
                "is_final": false,
                "final_keywords": "",
                "conversation_summary": ""
            }}

            🧩 응답 작성 기준:
            - "response"에는 다음 질문 또는 안내 문장을 간결하게 작성합니다.
            - "conversation_summary"에는 지금까지 확인된 요구사항을 간단히 요약합니다.
            - "final_keywords"는 is_final이 true일 때만 작성하며, 검색에 바로 사용할 수 있도록 구성합니다.

            🔐 is_final 조건:
            - 다음 항목들이 모두 수집되면 is_final을 true로 설정하세요:
            - 가격대
            - 용도
            - 브랜드 선호도
            - 추가로 필요한 기능

            📌 current_query 사용 지침:
            - 사용자의 초기 요청은 다음과 같습니다:
            "{current_query}"
            - 이는 사용자의 최종 검색 목적을 나타냅니다.
            - final_keywords를 생성할 때 반드시 current_query를 참고하여 제품명(예: 이어폰, 모니터 등)을 포함하세요.
            - current_query는 누락된 제품 종류를 보완하는 데 사용됩니다.

            🚫 자연어 출력만 하는 잘못된 예시 (절대 이렇게 응답하지 마세요):
            특정 브랜드에 대한 선호도가 있으신가요?

            ✅ 올바른 형태 (예시 목적, 복사하지 마세요):
            {{
                "should_search": false,
                "response": "특정 브랜드에 대한 선호도가 있으신가요?",
                "is_final": false,
                "final_keywords": "",
                "conversation_summary": "가격대 - 3만원대, 용도 - 운동용"
            }}
            """

        messages = [{"role": "system", "content": system_content}]
        for msg in conversation_history:
            messages.append(msg)
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,
            max_tokens=300,
            timeout=10
        )

        bot_response = response.choices[0].message.content

        if not bot_response.startswith("{"):
            summary = " / ".join([msg["content"] for msg in conversation_history if msg["role"] == "user"][-3:]) or "요구사항 요약 실패"
            logger.warning(f"[WARNING] GPT 응답이 JSON 아님. fallback 적용.")
            logger.info(f'[LOG] 채팅 사용자: {user_id} | 입력: "{message}" → 응답: "{bot_response}"')
            return JSONResponse({
                "should_search": False,
                "response": bot_response,
                "is_final": False,
                "final_keywords": "",
                "conversation_summary": summary
            })

        response_data = json.loads(bot_response)
        if not isinstance(response_data, dict):
            raise ValueError("응답이 올바른 형식이 아닙니다.")

        for field in ["should_search", "response", "is_final", "conversation_summary"]:
            if field not in response_data:
                raise ValueError(f"필수 필드 '{field}'가 없습니다.")
        if response_data["is_final"] and "final_keywords" not in response_data:
            raise ValueError("최종 응답에는 final_keywords가 필요합니다.")

        logger.info(f'[LOG] 채팅 사용자: {user_id} | 입력: "{message}" → 응답: "{response_data["response"]}"')
        return JSONResponse(response_data)

    except Exception as e:
        logger.error(f"GPT 응답 처리 중 오류: {str(e)}")
        return JSONResponse({
            "should_search": False,
            "response": "죄송합니다. 잠시 후 다시 시도해주세요.",
            "is_final": False,
            "conversation_summary": "대화 요약을 생성할 수 없습니다."
        })

# 사용자 이벤트 로깅
@app.post("/log/event")
async def log_event(request: Request, user_id: str | None = Cookie(default="익명")):
    try:
        data = await request.json()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_type = data.get("type", "event")

        detail_str = " | ".join([f'{k}: "{v}"' for k, v in data.items() if k != "type"])
        log_msg = f'[LOG] {log_type} | 사용자: {user_id} | {detail_str}'

        logger.info(log_msg)
        return Response(status_code=204)
    except Exception as e:
        logger.error(f"[LOG] log_event 실패: {str(e)}")
        return JSONResponse({'error': '로깅 실패'}, status_code=500)

# SEO 관련 라우터
@app.get("/sitemap.xml")
async def sitemap():
    return FileResponse('public/sitemap.xml', media_type='application/xml')

@app.get("/robots.txt")
async def robots():
    return FileResponse('public/robots.txt', media_type='text/plain')

# 네이버 쇼핑 API - 가격 크롤링
def fetch_price_and_link(query: str):
    headers = {
        "X-Naver-Client-Id": naver_api_client_id,
        "X-Naver-Client-Secret": naver_api_client_secret
    }
    params = {
        "query": query,
        "display": 1,
        "sort": "sim"
    }

    res = requests.get("https://openapi.naver.com/v1/search/shop.json", headers=headers, params=params)

    if res.status_code == 200:
        data = res.json()
        if data["items"]:
            item = data["items"][0]
            return f"{int(item['lprice']):,}원", item["link"]
    return "정보 없음", ""

@app.post("/api/get_price")
async def get_price(request: Request):
    data = await request.json()
    query = data.get('question', '')
    price, link = fetch_price_and_link(query)
    return JSONResponse({"price": price, "link": link})
