import os
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

MAX_GHOST_LISTINGS = 3  # cap how many "duplicate" listings we ever show


def clean_digits(s):
    return "".join(filter(str.isdigit, s or ""))


def score_listing(expected_name, expected_phone, expected_town, found_name, found_phone, found_address):
    issues = []

    if not found_name:
        name_pts = 0
        issues.append("Name: not found in listing")
    elif expected_name.strip().lower() == found_name.strip().lower():
        name_pts = 50
    else:
        name_pts = 15
        issues.append(f'Name: expected "{expected_name}", found "{found_name}"')

    if expected_phone:
        if not found_phone:
            phone_pts = 0
            issues.append("Phone: not listed")
        elif clean_digits(expected_phone) == clean_digits(found_phone):
            phone_pts = 30
        else:
            phone_pts = 0
            issues.append(f'Phone: expected "{expected_phone}", found "{found_phone}"')
    else:
        phone_pts = 30

    if expected_town:
        haystack = (found_address or "").strip().lower()
        if not haystack:
            town_pts = 0
            issues.append("Address: not listed")
        elif expected_town.strip().lower() in haystack:
            town_pts = 20
        else:
            town_pts = 0
            issues.append(f'Town: expected "{expected_town}", found in "{found_address}"')
    else:
        town_pts = 20

    score = name_pts + phone_pts + town_pts
    issue_text = " | ".join(issues) if issues else "Exact match on name, phone, and town"
    return score, issue_text


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
    """True if any meaningful word from the typed town appears in the found address."""
    if not town:
        return True  # nothing to check against
    if not address:
        return False
    town_words = [w.strip(",.") for w in town.lower().split() if len(w.strip(",.")) > 2]
    address_lower = address.lower()
    return any(w in address_lower for w in town_words)


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
    phone = (data.get("phone") or "").strip()

    if not name:
        return jsonify({"error": "Business name is required"}), 400

    # The search query ALWAYS includes both name and town when town is given.
    # This is the field that was previously being ignored.
    full_query = f"{name} {town}".strip() if town else name

    results = []
    verified_business = None
    ghost_count_shown = 0

    # 1. Google Maps — primary listing + ghost/duplicate detection
    try:
        res = serp_get({"engine": "google_maps", "q": full_query, "type": "search"})
        local_results = res.get("local_results") or ([res["place_results"]] if "place_results" in res else [])

        # If a town was given, filter out results that clearly aren't in that town/state
        if town and local_results:
            filtered = [r for r in local_results if town_in_address(town, r.get("address", ""))]
            # Only apply the filter if it actually leaves something — otherwise keep
            # the unfiltered list so we can surface "not found here" instead of hiding everything.
            if filtered:
                local_results = filtered
            else:
                local_results = []

        if local_results:
            top = local_results[0]
            found_title = top.get("title", "")
            found_phone = top.get("phone", "")
            found_address = top.get("address", "")
            place_id = top.get("place_id", "")

            verified_business = {
                "title": found_title,
                "address": found_address or "Not publicly listed",
                "phone": found_phone or "Not listed",
                "rating": top.get("rating", "N/A"),
                "reviews": top.get("reviews", 0),
                "map_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "#",
            }

            score, issue = score_listing(name, phone, town, found_title, found_phone, found_address)
            results.append({
                "node": "Google Maps",
                "icon": "fa-brands fa-google",
                "foundName": found_title,
                "score": score,
                "issue": issue,
                "isGhost": False,
            })

            for dup in local_results[1:]:
                if ghost_count_shown >= MAX_GHOST_LISTINGS:
                    break
                results.append({
                    "node": "Google Maps (duplicate)",
                    "icon": "fa-solid fa-ghost",
                    "foundName": dup.get("title", "Unknown"),
                    "score": 20,
                    "issue": f'Second, unmanaged listing at "{dup.get("address", "unknown address")}"',
                    "isGhost": True,
                })
                ghost_count_shown += 1
        else:
            note = f' in "{town}"' if town else ""
            results.append({
                "node": "Google Maps",
                "icon": "fa-brands fa-google",
                "foundName": "Not listed",
                "score": 0,
                "issue": f'No active Google Maps listing found for "{name}"{note}',
                "isGhost": False,
            })
    except Exception as e:
        results.append({
            "node": "Google Maps",
            "icon": "fa-brands fa-google",
            "foundName": "Error",
            "score": 0,
            "issue": f"Lookup failed: {e}",
            "isGhost": False,
        })

    # 2. Directory checks via Google site: search — town included in the query here too
    for label, domain, icon in DIRECTORY_SITES:
        try:
            q = f'site:{domain} {name} {town}'.strip()
            res = serp_get({"engine": "google", "q": q})
            organic = res.get("organic_results", [])
            if organic:
                raw_title = organic[0].get("title", "")
                found_title = raw_title.split("-")[0].split("|")[0].strip()
                snippet = organic[0].get("snippet", "")
                score, issue = score_listing(name, phone, town, found_title, "", snippet)
                results.append({
                    "node": label,
                    "icon": icon,
                    "foundName": found_title,
                    "score": score,
                    "issue": issue,
                    "isGhost": False,
                })
            else:
                results.append({
                    "node": label,
                    "icon": icon,
                    "foundName": "Not indexed",
                    "score": 0,
                    "issue": f"No {label} listing found — invisible to anyone checking there",
                    "isGhost": False,
                })
        except Exception as e:
            results.append({
                "node": label,
                "icon": icon,
                "foundName": "Error",
                "score": 0,
                "issue": f"Lookup failed: {e}",
                "isGhost": False,
            })

    return jsonify({"verified_business": verified_business, "results": results})


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
