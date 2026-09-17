from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


def evaluate_exact_match(target, found):
    if not found:
        return 0, "No Listing Found"
    if target == found:
        return 100, "100% Strict Match (Exact Case & Punctuation)"
    if target.lower() == found.lower():
        return (
            60,
            f'Capitalization/Punctuation Discrepancy (Found: "{found}")',
        )
    return 30, f'Formatting/Name Mismatch (Found: "{found}")'


@app.route("/")
def index():
    return send_from_directory(app.root_path, "auditapp.html")


@app.route("/api/health")
def health():
    """Cheap liveness probe. Pass ?deep=1 to also verify the SerpApi key.

    The deep check hits SerpApi's /account endpoint, which reports plan status
    without spending a search from the monthly quota.
    """
    body = {
        "status": "ok",
        "service": "truth-node",
        "serpapi_key_configured": bool(SERPAPI_KEY),
    }

    if request.args.get("deep"):
        if not SERPAPI_KEY:
            body["serpapi"] = {"ok": False, "error": "SERPAPI_KEY is not set"}
        else:
            try:
                account = requests.get(
                    "https://serpapi.com/account",
                    params={"api_key": SERPAPI_KEY},
                    timeout=12,
                ).json()
                if "error" in account:
                    body["serpapi"] = {"ok": False, "error": account["error"]}
                else:
                    body["serpapi"] = {
                        "ok": True,
                        "plan": account.get("plan_name"),
                        "searches_left": account.get("total_searches_left"),
                    }
            except Exception as e:
                body["serpapi"] = {"ok": False, "error": str(e)}

    return jsonify(body)


@app.route("/api/audit", methods=["POST"])
def audit():
    data = request.json or {}
    biz_name = data.get("name", "").strip()
    biz_location = data.get("location", "").strip()

    if not biz_name:
        return jsonify({"error": "Business Name is required"}), 400

    results = []
    verified_business = None

    full_query = (
        f"{biz_name} {biz_location}".strip() if biz_location else biz_name
    )

    google_params = {
        "engine": "google_maps",
        "q": full_query,
        "api_key": SERPAPI_KEY,
        "type": "search",
    }

    try:
        res = requests.get(
            "https://serpapi.com/search", params=google_params, timeout=12
        ).json()

        if "error" in res:
            raise Exception(res["error"])

        local_results = res.get("local_results", [])
        if not local_results and "place_results" in res:
            local_results = [res["place_results"]]

        if local_results:
            top_match = local_results[0]
            found_title = top_match.get("title", "")
            found_address = top_match.get("address", "")
            place_id = top_match.get("place_id", "")
            rating = top_match.get("rating", "N/A")
            reviews = top_match.get("reviews", 0)

            verified_business = {
                "title": found_title,
                "address": found_address or "Address not publicly listed",
                "rating": rating,
                "reviews": reviews,
                "place_id": place_id,
                "map_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                if place_id
                else "#",
            }

            score, msg = evaluate_exact_match(biz_name, found_title)

            results.append({
                "node": "Google Maps Local Pack",
                "icon": "fa-brands fa-google",
                "foundName": found_title,
                "score": score,
                "issue": msg,
                "isGhost": False,
            })

            if len(local_results) > 1:
                for duplicate in local_results[1:]:
                    dup_title = duplicate.get("title", "")
                    dup_addr = duplicate.get("address", "Legacy/Unverified")
                    results.append({
                        "node": "Google Unclaimed Duplicate Node",
                        "icon": "fa-solid fa-ghost",
                        "foundName": dup_title,
                        "score": 20,
                        "issue": f"Ghost profile detected at: {dup_addr}",
                        "isGhost": True,
                    })
        else:
            results.append({
                "node": "Google Maps Local Pack",
                "icon": "fa-brands fa-google",
                "foundName": "Not Listed",
                "score": 0,
                "issue": f"No active Google listing found for '{full_query}'",
                "isGhost": False,
            })
    except Exception as e:
        results.append({
            "node": "Google Maps Local Pack",
            "icon": "fa-brands fa-google",
            "foundName": "API Error",
            "score": 0,
            "issue": f"SerpApi Error: {str(e)}",
            "isGhost": False,
        })

    return jsonify(
        {"verified_business": verified_business, "results": results}
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))