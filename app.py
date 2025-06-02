from flask import Flask, render_template, request, jsonify
import json
import os
from googlesearch import search

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/result.html")
def result():
    return render_template("result.html")

@app.route("/api/questions")
def api_questions():
    with open(os.path.join(app.static_folder, "questions.json"), encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/keep-alive")
def receive_ping():
    return "true"

@app.route("/api/products")
def api_products():
    query = request.args.get("query", "")
    with open(os.path.join(app.static_folder, "products.json"), encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data.get(query, []))
    
# ✅ 추가: 실시간 구글 쇼핑 검색 API(상세페이지)
@app.route("/api/google_search")
def api_google_search():
    user_query = request.args.get("query", "")
    if not user_query:
        return jsonify({"error": "검색어가 없습니다."}), 400

    full_query = (
        f"{user_query} site:coupang.com/vp/products/ "
        f"OR site:smartstore.naver.com "
        f"OR site:shopping.naver.com"
    )

    try:
        urls = search(full_query, lang="ko", stop=5)
        return jsonify({"results": list(urls)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

