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

# Pulls a US street address (number + street, City, ST ZIP) out of a raw
# snippet — never returns the whole snippet, only the address-shaped part.
ADDRESS_RE = re.compile(
    r"\d{1,6}\s+[A-Za-z0-9.'#\- ]+?,\s*[A-Za-z .'\-]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?"
)

# Standard US phone formats: (417) 335-2133, 417-335-2133, 417.335.2133, +1 417 335 2133
PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)

# Best-effort hours pattern: a day (optionally a day range) followed by a
# time range like "9 AM - 9 PM". Snippets vary a lot, so this only catches
# clean formats — anything murkier is left as "not found" rather than guessed.
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
    """SerpApi's google_maps engine sometimes returns a plain 'hours' string
    (e.g. 'Open - Closes 9PM'), sometimes a per-day 'operating_hours' dict.
    Handle both; return None rather than guessing if neither is present."""
    h = top.get("hours")
    if isinstance(h, str) and h.strip():
        return h.strip()
    oh = top.get("operating_hours")
    if isinstance(oh, dict) and oh:
        parts = [f"{day[:3].capitalize()} {hrs}" for day, hrs in oh.items() if hrs]
        return "; ".join(parts) if parts else None
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
    """Same relevance-filter idea as the directory sites: only accept a
    map-engine result if the business name actually overlaps the query,
    so we don't attach a same-named business from somewhere else."""
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

    # Which sources the frontend currently has toggled on, lowercased to
    # match each source's label.lower(). If the client doesn't send this
    # (older callers), fall back to querying everything, as before.
    raw_sources = data.get("sources")
    enabled = set(s.strip().lower() for s in raw_sources) if isinstance(raw_sources, list) else set()

    def is_enabled(label):
        return label.lower() in enabled

    full_query = f"{name} {town}".strip() if town else name
    sources = []
    ghosts = []
    verified_business = None
    lat, lng = None, None  # populated from the Google Maps match, feeds Bing/Apple below

    # 1. Google Maps — queried only when enabled. If disabled, it is not
    # queried and does not appear in the response.
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
                place_id = top.get("place_id", "")

                gps = top.get("gps_coordinates") or {}
                lat, lng = gps.get("latitude"), gps.get("longitude")

                sources.append({
                    "source": "Google Maps",
                    "icon": "fa-brands fa-google",
                    "name": top.get("title") or None,
                    "address": top.get("address") or None,
                    "phone": top.get("phone") or None,
                    "hours": google_maps_hours(top),
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
                    "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                })
        except Exception as e:
            sources.append({
                "source": "Google Maps", "icon": "fa-brands fa-google",
                "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                "error": str(e),
            })

    # 2. Directory sites — unquoted, broad search so we actually find the
    # listing. Only the address/phone/hours SHAPES are pulled out of the raw
    # snippet via regex — never the whole snippet — so a field only ever
    # shows what belongs in it.
    for label, domain, icon in DIRECTORY_SITES:
        if not is_enabled(label):
            continue  # toggled off client-side — skip the query entirely, don't show it
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
                    "name": found_title,
                    "address": extract_address(snippet),
                    "phone": extract_phone(snippet),
                    "hours": extract_hours(snippet),
                    "email": email_match.group(0) if email_match else None,
                    "url": top.get("link"),
                })
            else:
                sources.append({
                    "source": label, "icon": icon,
                    "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                })
        except Exception as e:
            sources.append({
                "source": label, "icon": icon,
                "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                "error": str(e),
            })

    # 3. Bing Maps — real map engine, needs coordinates (not just a town
    # string). Skipped entirely (no entry at all) if toggled off.
    if is_enabled("Bing Maps"):
        if lat and lng:
            try:
                res = serp_get({"engine": "bing_maps", "q": full_query, "cp": f"{lat}~{lng}"})
                local = res.get("local_results") or [{}]
                items = local[0].get("items", []) if isinstance(local, list) else []
                match = best_match_by_name(items, name)
                if match:
                    sources.append({
                        "source": "Bing Maps", "icon": "fa-brands fa-microsoft",
                        "name": match.get("title"),
                        "address": match.get("address"),
                        "phone": match.get("phone"),
                        "hours": match.get("hours"),
                        "email": None,
                        "url": match.get("url") or match.get("website"),
                    })
                else:
                    sources.append({
                        "source": "Bing Maps", "icon": "fa-brands fa-microsoft",
                        "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                    })
            except Exception as e:
                sources.append({
                    "source": "Bing Maps", "icon": "fa-brands fa-microsoft",
                    "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                    "error": str(e),
                })
        else:
            sources.append({
                "source": "Bing Maps", "icon": "fa-brands fa-microsoft",
                "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                "error": "No coordinates from Google Maps match — skipped",
            })

    # 4. Apple Maps — same deal, uses `query` + `center` param names instead
    # of q/cp. Skipped entirely if toggled off.
    if is_enabled("Apple Maps"):
        if lat and lng:
            try:
                res = serp_get({"engine": "apple_maps", "query": full_query, "center": f"{lat},{lng}"})
                items = res.get("local_results", [])
                match = best_match_by_name(items, name)
                if match:
                    sources.append({
                        "source": "Apple Maps", "icon": "fa-brands fa-apple",
                        "name": match.get("title"),
                        # NOTE: field name unverified against a live payload — check
                        # a real /search.json?engine=apple_maps response and adjust
                        # if it's actually "formatted_address" or nested differently.
                        "address": match.get("address"),
                        "phone": match.get("phone") or match.get("phone_number"),
                        "hours": match.get("hours"),
                        "email": None,
                        "url": match.get("url") or match.get("website"),
                    })
                else:
                    sources.append({
                        "source": "Apple Maps", "icon": "fa-brands fa-apple",
                        "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                    })
            except Exception as e:
                sources.append({
                    "source": "Apple Maps", "icon": "fa-brands fa-apple",
                    "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                    "error": str(e),
                })
        else:
            sources.append({
                "source": "Apple Maps", "icon": "fa-brands fa-apple",
                "name": None, "address": None, "phone": None, "hours": None, "email": None, "url": None,
                "error": "No coordinates from Google Maps match — skipped",
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
