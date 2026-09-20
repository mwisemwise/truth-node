import os
import re
from urllib.parse import urlparse
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

DIRECTORY_SITES = [
    ("Yelp", "yelp.com"),
    ("Facebook", "facebook.com"),
    ("Better Business Bureau", "bbb.org"),
    ("Foursquare", "foursquare.com"),
]

# Allows 0-2 extra comma segments (suite/unit, e.g. "Ste A") between the
# street and city/state/zip -- a plain "street, city, ST zip" snippet still
# matches fine, but so does "street, Ste A, city, ST zip".
ADDRESS_RE = re.compile(
    r"\d{1,6}\s+[A-Za-z0-9.'#\-/ ]+?(?:,\s*[A-Za-z0-9.'#\-/ ]+?){0,2},\s*[A-Za-z .'\-]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?"
)
PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
HOURS_RE = re.compile(
    r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s*(?:[-–—]\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*)?\s*[:\-]?\s*)?"
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)"
)


def extract_address(text):
    if not text:
        return None
    m = ADDRESS_RE.search(text)
    return m.group(0).strip(" ,") if m else None


def extract_phone(text):
    if not text:
        return None
    m = PHONE_RE.search(text)
    return m.group(0).strip() if m else None


def extract_hours(text):
    if not text:
        return None
    m = HOURS_RE.search(text)
    return m.group(0).strip() if m else None


def google_maps_hours(top):
    h = top.get("hours")
    if isinstance(h, str) and h.strip():
        return h.strip()
    oh = top.get("operating_hours")
    if isinstance(oh, dict) and oh:
        parts = [f"{day[:3].capitalize()} {hrs}" for day, hrs in oh.items() if hrs]
        return "; ".join(parts) if parts else None
    return None


def domain_matches(url, domain):
    """A `site:domain` Google search can silently fall back to unrelated
    general web results when it finds nothing on that domain (Google shows
    a "no results, here's the web instead" response). Without this check,
    that fallback link gets treated as if it were the real listing."""
    if not url:
        return False
    netloc = urlparse(url).netloc.lower()
    return domain.lower() in netloc


def best_directory_result(organic_results, domain):
    for item in organic_results:
        if domain_matches(item.get("link"), domain):
            return item
    return None


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


def best_match_by_name(items, name, title_field="title"):
    if not items:
        return None
    name_words = [w.strip(",.") for w in name.lower().split() if len(w.strip(",.")) > 1]
    if not name_words:
        return items[0]
    for item in items:
        title = (item.get(title_field) or "").lower()
        if any(w in title for w in name_words):
            return item
    return None


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

    raw_sources = data.get("sources")
    enabled = set(s.strip().lower() for s in raw_sources) if isinstance(raw_sources, list) else None

    def is_enabled(label):
        return enabled is None or label.lower() in enabled

    full_query = f"{name} {town}".strip() if town else name
    sources = []
    lat, lng = None, None

    # 1. Google Maps — now a normal toggle like every other engine. Off =
    # not queried, not in results, and lat/lng stay None (which means Bing
    # Maps / Apple Maps below won't have coordinates to work with either —
    # that's an honest consequence of the dependency, not a bug).
    if is_enabled("Google Maps"):
        try:
            res = serp_get({"engine": "google_maps", "q": full_query, "type": "search"})
            local_results = res.get("local_results") or ([res["place_results"]] if "place_results" in res else [])

            if town and local_results:
                filtered = [r for r in local_results if town_in_address(town, r.get("address", ""))]
                if filtered:
                    local_results = filtered

            if local_results:
                top = local_results[0]
                gps = top.get("gps_coordinates") or {}
                lat, lng = gps.get("latitude"), gps.get("longitude")
                place_id = top.get("place_id", "")
                sources.append({
                    "source": "Google Maps",
                    "address": top.get("address") or None,
                    "phone": top.get("phone") or None,
                    "hours": google_maps_hours(top),
                    "url": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None,
                })
            else:
                sources.append({"source": "Google Maps", "address": None, "phone": None, "hours": None, "url": None})
        except Exception as e:
            sources.append({"source": "Google Maps", "address": None, "phone": None, "hours": None, "url": None, "error": str(e)})

    # 2. Directory sites — address/phone/hours isolated via regex, never the
    # raw snippet. Skipped entirely (no entry) if toggled off.
    for label, domain in DIRECTORY_SITES:
        if not is_enabled(label):
            continue
        try:
            q = f"site:{domain} {name} {town}".strip()
            res = serp_get({"engine": "google", "q": q})
            organic = res.get("organic_results", [])
            top = best_directory_result(organic, domain)
            if top:
                snippet = top.get("snippet", "") or ""
                sources.append({
                    "source": label,
                    "address": extract_address(snippet),
                    "phone": extract_phone(snippet),
                    "hours": extract_hours(snippet),
                    "url": top.get("link"),
                })
            else:
                sources.append({"source": label, "address": None, "phone": None, "hours": None, "url": None})
        except Exception as e:
            sources.append({"source": label, "address": None, "phone": None, "hours": None, "url": None, "error": str(e)})

    # 3. Bing Maps — needs coordinates from Google Maps. Skipped entirely if
    # toggled off; if on but no coordinates available, still appears with
    # empty fields (it WAS queried/attempted, so it's not excluded — it just
    # has nothing to report).
    if is_enabled("Bing Maps"):
        if lat and lng:
            try:
                res = serp_get({"engine": "bing_maps", "q": full_query, "cp": f"{lat}~{lng}"})
                local = res.get("local_results") or [{}]
                items = local[0].get("items", []) if isinstance(local, list) else []
                match = best_match_by_name(items, name)
                if match:
                    sources.append({
                        "source": "Bing Maps",
                        "address": match.get("address"),
                        "phone": match.get("phone"),
                        "hours": match.get("hours"),
                        "url": match.get("url") or match.get("website"),
                    })
                else:
                    sources.append({"source": "Bing Maps", "address": None, "phone": None, "hours": None, "url": None})
            except Exception as e:
                sources.append({"source": "Bing Maps", "address": None, "phone": None, "hours": None, "url": None, "error": str(e)})
        else:
            sources.append({"source": "Bing Maps", "address": None, "phone": None, "hours": None, "url": None})

    # 4. Apple Maps — same coordinate dependency as Bing Maps above.
    if is_enabled("Apple Maps"):
        if lat and lng:
            try:
                res = serp_get({"engine": "apple_maps", "query": full_query, "center": f"{lat},{lng}"})
                items = res.get("local_results", [])
                match = best_match_by_name(items, name)
                if match:
                    sources.append({
                        "source": "Apple Maps",
                        "address": match.get("address"),
                        "phone": match.get("phone") or match.get("phone_number"),
                        "hours": match.get("hours"),
                        "url": match.get("url") or match.get("website"),
                    })
                else:
                    sources.append({"source": "Apple Maps", "address": None, "phone": None, "hours": None, "url": None})
            except Exception as e:
                sources.append({"source": "Apple Maps", "address": None, "phone": None, "hours": None, "url": None, "error": str(e)})
        else:
            sources.append({"source": "Apple Maps", "address": None, "phone": None, "hours": None, "url": None})

    return jsonify({"sources": sources})


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
