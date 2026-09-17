import os
import re
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

DIRECTORY_SITES = [
    ("Yelp", "yelp.com", "fa-brands fa-yelp"),
    ("Facebook", "facebook.com", "fa-brands fa-facebook"),
    ("Better Business Bureau", "bbb.org", "fa-solid fa-building-shield"),
    ("Foursquare", "foursquare.com", "fa-brands fa-foursquare"),
]

MAX_GHOST_LISTINGS = 3

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def serp_get(params, timeout=12):
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY not configured on server")
    r = requests.get("https://serpapi.com/search", params={**params, "api_key": SERPAPI_KEY}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def town_in_address(town, address):
    if not town:
        return True
    if not address:
        return False
    town_words = [w.strip(",.") for w in town.lower().split() if len(w.strip(",.")) > 2]
    return any(w in address.lower() for w in town_words)


@app.route("/")
def index():
    return send_from_directory(".", "auditapp.html")


@app.route("/api/audit", methods=["POST"])
def audit():
    if not SERPAPI_KEY:
        return jsonify({"error": "Server misconfigured: SERPAPI_KEY not set"}), 500

    data = request.json or {}
    name = (data.get("name") or "").strip()
    town = (data.get("town") or "").strip()

    if not name:
        return jsonify({"error": "Business name is required"}), 400

    full_query = f"{name} {town}".strip() if town else name
    sources = []
    ghosts = []
    verified_business = None

    # 1. Google Maps — primary source + duplicate/ghost detection
    try:
        res = serp_get({"engine": "google_maps", "q": full_query, "type": "search"})
        local_results = res.get("local_results") or ([res["place_results"]] if "place_results" in res else [])

        if town and local_results:
            filtered = [r for r in local_results if town_in_address(town, r.get("address", ""))]
            if filtered:
                local_results = filtered

        if local_results:
            top = local_results[0]
            place_id = top.get("place_id", "")
            sources.append({
                "source": "Google Maps",
                "icon": "fa-brands fa-google",
                "name": top.get("title") or None,
                "address": top.get("address") or None,
                "phone": top.get("phone") or None,
                "email": None,
                "url": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None,
            })
            verified_business = {
                "title": top.get("title", ""),
                "address": top.get("address") or "Not publicly listed",
                "phone": top.get("phone") or "Not listed",
                "rating": top.get("rating", "N/A"),
                "reviews": top.get("reviews", 0),
                "map_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "#",
            }

            for dup in local_results[1:1 + MAX_GHOST_LISTINGS]:
                ghosts.append({
                    "name": dup.get("title", "Unknown"),
                    "address": dup.get("address", "unknown address"),
                })
        else:
            sources.append({
                "source": "Google Maps", "icon": "fa-brands fa-google",
                "name": None, "address": None, "phone": None, "email": None, "url": None,
            })
    except Exception as e:
        sources.append({
            "source": "Google Maps", "icon": "fa-brands fa-google",
            "name": None, "address": None, "phone": None, "email": None, "url": None,
            "error": str(e),
        })

    # 2. Directory sites — unquoted, broad search so we actually find the listing
    for label, domain, icon in DIRECTORY_SITES:
        try:
            q = f"site:{domain} {name} {town}".strip()
            res = serp_get({"engine": "google", "q": q})
            organic = res.get("organic_results", [])
            if organic:
                top = organic[0]
                raw_title = top.get("title", "")
                found_title = raw_title.split("-")[0].split("|")[0].strip() if raw_title else None
                snippet = top.get("snippet", "") or ""
                email_match = EMAIL_RE.search(snippet)
                sources.append({
                    "source": label, "icon": icon,
                    "name": found_title, "address": snippet or None,
                    "phone": None, "email": email_match.group(0) if email_match else None,
                    "url": top.get("link"),
                })
            else:
                sources.append({
                    "source": label, "icon": icon,
                    "name": None, "address": None, "phone": None, "email": None, "url": None,
                })
        except Exception as e:
            sources.append({
                "source": label, "icon": icon,
                "name": None, "address": None, "phone": None, "email": None, "url": None,
                "error": str(e),
            })

    return jsonify({"sources": sources, "ghosts": ghosts, "verified_business": verified_business})


@app.route("/api/health", methods=["GET"])
def health():
    deep = request.args.get("deep")
    payload = {"status": "ok", "service": "truth-node", "serpapi_key_configured": bool(SERPAPI_KEY)}

    if deep and SERPAPI_KEY:
        try:
            acct = requests.get("https://serpapi.com/account", params={"api_key": SERPAPI_KEY}, timeout=8)
            acct_data = acct.json()
            payload["serpapi"] = {
                "ok": "error" not in acct_data,
                "plan": acct_data.get("plan_name"),
                "searches_left": acct_data.get("total_searches_left"),
            }
        except Exception as e:
            payload["serpapi"] = {"ok": False, "error": str(e)}

    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
