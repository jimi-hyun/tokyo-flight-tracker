#!/usr/bin/env python3
"""
Tokyo Ariake Arena Flight Price Collector (SerpApi Google Flights)
- Uses ONLY Python 3 standard library (no pip install required, works on any PC & GitHub Actions)
- Queries 6 nonstop routes per run (6 SerpApi credits/run):
    1. Round-trip  ICN <-> NRT (2027-03-27 ~ 2027-03-29, out<=11:00, return Tokyo dep>=16:00)
    2. Round-trip  GMP <-> HND (2027-03-27 ~ 2027-03-29, out<=11:00, return Tokyo dep>=16:00)
    3. One-way out ICN  -> NRT (2027-03-27, dep<=11:00)
    4. One-way out GMP  -> HND (2027-03-27, dep<=11:00)
    5. One-way in  NRT  -> ICN (2027-03-29, Tokyo dep>=16:00)
    6. One-way in  HND  -> GMP (2027-03-29, Tokyo dep>=16:00)
- Calls SerpApi /account.json (FREE, 0 credits) to record exact monthly remaining quota.
- Preserves and appends daily KST snapshots to data/flights.json.

Usage:
    python fetch_flights.py              # Live fetch using SERPAPI_API_KEY (from env or .env)
    python fetch_flights.py --dry-run    # Test script without calling SerpApi (0 credits)
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KST = dt.timezone(dt.timedelta(hours=9))
ROOT_DIR = Path(__file__).resolve().parent
DATA_PATH = ROOT_DIR / "data" / "flights.json"
ENV_PATH = ROOT_DIR / ".env"

OUTBOUND_DATE = "2027-03-27"
INBOUND_DATE = "2027-03-29"
CREDITS_PER_REFRESH = 6

# Airline codes generally classified as LCC on Korea-Japan routes
LCC_CODES = {"7C", "TW", "LJ", "BX", "ZE", "RS", "RF", "YP", "MM", "ZG", "NQ", "GK"}

AIRLINE_KO_MAP = {
    "Jeju Air": "제주항공",
    "T'way Air": "티웨이항공",
    "Jin Air": "진에어",
    "Air Busan": "에어부산",
    "Eastar Jet": "이스타항공",
    "Air Seoul": "에어서울",
    "Aero K": "에어로케이",
    "Air Premia": "에어프레미아",
    "Peach": "피치항공",
    "Peach Aviation": "피치항공",
    "ZIPAIR": "집에어",
    "ZIPAIR Tokyo": "집에어",
    "Korean Air": "대한항공",
    "Asiana Airlines": "아시아나항공",
    "ANA": "전일본공수 (ANA)",
    "All Nippon Airways": "전일본공수 (ANA)",
    "JAL": "일본항공 (JAL)",
    "Japan Airlines": "일본항공 (JAL)",
}


def load_dotenv(path: Path) -> None:
    """Minimal .env parser so no third-party package is needed."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def http_get_json(url: str, params: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
    clean_params = {k: v for k, v in params.items() if v is not None}
    full_url = f"{url}?{urllib.parse.urlencode(clean_params)}"
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": "TokyoFlightTracker/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def parse_hhmm(time_str: Optional[str]) -> str:
    """Extract HH:MM from SerpApi datetime strings like '2027-03-27 08:10'."""
    if not time_str:
        return "--:--"
    m = re.search(r"(\d{1,2}):(\d{2})", str(time_str))
    if not m:
        return "--:--"
    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"


def hhmm_to_min(hhmm: str) -> Optional[int]:
    if not hhmm or ":" not in hhmm or "--" in hhmm:
        return None
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def fmt_duration(minutes: Optional[int]) -> str:
    if not minutes or minutes <= 0:
        return "-"
    h, m = divmod(int(minutes), 60)
    return f"{h}시간 {m}분"


def extract_airline_code(flight_no: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", flight_no or "").upper()
    m = re.match(r"^([A-Z0-9]{2})", cleaned)
    return m.group(1) if m else ""


def normalize_airline_name(name: str) -> str:
    return AIRLINE_KO_MAP.get(name, name or "항공사 미상")


def build_google_flights_url(origin: str, dest: str, out_date: str, in_date: Optional[str] = None) -> str:
    if in_date:
        q = f"Flights from {origin} to {dest} on {out_date} through {in_date} nonstop"
    else:
        q = f"One way flights from {origin} to {dest} on {out_date} nonstop"
    return f"https://www.google.com/travel/flights?{urllib.parse.urlencode({'q': q, 'curr': 'KRW', 'hl': 'ko'})}"


def fetch_serpapi_flights(api_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    query = {
        "engine": "google_flights",
        "currency": "KRW",
        "hl": "ko",
        "gl": "kr",
        "stops": "1",  # 1 = Nonstop only in SerpApi Google Flights
        "adults": "1",
        "api_key": api_key,
    }
    query.update(params)
    return http_get_json("https://serpapi.com/search.json", query)


def fetch_serpapi_account(api_key: str) -> Dict[str, Any]:
    """FREE endpoint (0 credits) returning real-time SerpApi monthly quota."""
    return http_get_json("https://serpapi.com/account.json", {"api_key": api_key})


def compute_quota(account: Dict[str, Any], now_kst: dt.datetime) -> Dict[str, Any]:
    monthly_limit = int(account.get("searches_per_month") or 250)
    this_month_usage = int(account.get("this_month_usage") or 0)
    remaining = account.get("total_searches_left")
    if remaining is None:
        remaining = account.get("plan_searches_left")
    if remaining is None:
        remaining = max(0, monthly_limit - this_month_usage)
    remaining = max(0, int(remaining))

    renewal_str = account.get("plan_renewal_date")
    days_until_renewal: int
    if renewal_str:
        try:
            renewal_date = dt.date.fromisoformat(str(renewal_str)[:10])
            days_until_renewal = max(0, (renewal_date - now_kst.date()).days)
        except ValueError:
            last_day = calendar.monthrange(now_kst.year, now_kst.month)[1]
            days_until_renewal = max(0, last_day - now_kst.day)
    else:
        last_day = calendar.monthrange(now_kst.year, now_kst.month)[1]
        days_until_renewal = max(0, last_day - now_kst.day)

    remaining_free_refreshes = remaining // CREDITS_PER_REFRESH
    extra_manual_safe = max(0, remaining_free_refreshes - days_until_renewal)

    return {
        "plan_name": account.get("plan_name") or "Free Plan",
        "monthly_limit": monthly_limit,
        "this_month_usage": this_month_usage,
        "remaining_credits": remaining,
        "credits_per_refresh": CREDITS_PER_REFRESH,
        "remaining_free_refreshes": remaining_free_refreshes,
        "remaining_midnight_runs_this_month": days_until_renewal,
        "extra_manual_refreshes_safe": extra_manual_safe,
        "plan_renewal_date": renewal_str,
    }


def extract_flight_rows(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    rows.extend(raw.get("best_flights") or [])
    rows.extend(raw.get("other_flights") or [])
    return rows


def parse_one_way_list(
    raw: Dict[str, Any],
    origin: str,
    dest: str,
    date_str: str,
    direction: str,  # "out" or "in"
    max_depart_min: Optional[int] = None,
    min_depart_min: Optional[int] = None,
) -> List[Dict[str, Any]]:
    fallback_url = (raw.get("search_metadata") or {}).get("google_flights_url") or build_google_flights_url(origin, dest, date_str)
    parsed: List[Dict[str, Any]] = []
    seen = set()

    for item in extract_flight_rows(raw):
        legs = item.get("flights") or []
        if not legs:
            continue
        leg = legs[0]
        flight_no = re.sub(r"\s+", "", str(leg.get("flight_number") or "")).upper()
        depart = parse_hhmm((leg.get("departure_airport") or {}).get("time"))
        arrive = parse_hhmm((leg.get("arrival_airport") or {}).get("time"))
        dep_min = hhmm_to_min(depart)

        if max_depart_min is not None and (dep_min is None or dep_min > max_depart_min):
            continue
        if min_depart_min is not None and (dep_min is None or dep_min < min_depart_min):
            continue

        dedup_key = (flight_no, depart)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        code = extract_airline_code(flight_no)
        duration_min = int(item.get("total_duration") or leg.get("duration") or 0)
        price_val = item.get("price")
        price = int(price_val) if isinstance(price_val, (int, float)) else None

        parsed.append({
            "id": f"ow-{direction}-{flight_no or origin + dest}-{depart.replace(':', '')}",
            "airline": normalize_airline_name(str(leg.get("airline") or "")),
            "airline_code": code,
            "is_lcc": code in LCC_CODES,
            "flight_no": flight_no or f"{origin}-{dest}",
            "origin": (leg.get("departure_airport") or {}).get("id") or origin,
            "destination": (leg.get("arrival_airport") or {}).get("id") or dest,
            "depart": depart,
            "arrive": arrive,
            "duration": fmt_duration(duration_min),
            "duration_min": duration_min,
            "price": price,
            "url": fallback_url,
        })

    parsed.sort(key=lambda x: (x["price"] is None, x["price"] or 99999999, x["depart"]))
    return parsed


def parse_round_trip_list(
    raw: Dict[str, Any],
    origin: str,
    dest: str,
    inbound_lookup: List[Dict[str, Any]],
    max_depart_min: int = 11 * 60,
) -> List[Dict[str, Any]]:
    fallback_url = (raw.get("search_metadata") or {}).get("google_flights_url") or build_google_flights_url(
        origin, dest, OUTBOUND_DATE, INBOUND_DATE
    )
    parsed: List[Dict[str, Any]] = []
    seen = set()

    for item in extract_flight_rows(raw):
        legs = item.get("flights") or []
        if not legs:
            continue
        leg = legs[0]
        flight_no = re.sub(r"\s+", "", str(leg.get("flight_number") or "")).upper()
        out_depart = parse_hhmm((leg.get("departure_airport") or {}).get("time"))
        out_arrive = parse_hhmm((leg.get("arrival_airport") or {}).get("time"))
        dep_min = hhmm_to_min(out_depart)

        if dep_min is None or dep_min > max_depart_min:
            continue

        dedup_key = (flight_no, out_depart)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        code = extract_airline_code(flight_no)
        out_dur_min = int(item.get("total_duration") or leg.get("duration") or 0)
        price_val = item.get("price")
        price = int(price_val) if isinstance(price_val, (int, float)) else None

        # Cross-match same airline & reverse route from one-way inbound (Tokyo dep >= 16:00)
        matched_in = next(
            (
                inb for inb in inbound_lookup
                if inb["origin"] == dest and inb["destination"] == origin and inb["airline_code"] == code
            ),
            None,
        )
        if matched_in:
            in_depart = matched_in["depart"]
            in_arrive = matched_in["arrive"]
            in_duration = matched_in["duration"]
            in_estimated = True
        else:
            # Google Flights return_times=16,23 already guarantees a 16:00+ Tokyo departure
            in_depart = "17:00+"
            in_arrive = "-"
            in_duration = "약 2시간 30분"
            in_estimated = True

        parsed.append({
            "id": f"rt-{flight_no or origin + dest}-{out_depart.replace(':', '')}",
            "airline": normalize_airline_name(str(leg.get("airline") or "")),
            "airline_code": code,
            "is_lcc": code in LCC_CODES,
            "flight_no": flight_no or f"{origin}-{dest}",
            "origin": (leg.get("departure_airport") or {}).get("id") or origin,
            "destination": (leg.get("arrival_airport") or {}).get("id") or dest,
            "out_depart": out_depart,
            "out_arrive": out_arrive,
            "out_duration": fmt_duration(out_dur_min),
            "out_duration_min": out_dur_min,
            "in_depart": in_depart,
            "in_arrive": in_arrive,
            "in_duration": in_duration,
            "in_time_estimated": in_estimated,
            "price": price,
            "url": fallback_url,
        })

    parsed.sort(key=lambda x: (x["price"] is None, x["price"] or 99999999, x["out_depart"]))
    return parsed


def load_existing_data() -> Dict[str, Any]:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"history": []}


def compute_summary_mins(
    round_trips: List[Dict[str, Any]],
    ow_out: List[Dict[str, Any]],
    ow_in: List[Dict[str, Any]],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    icn_nrt_prices = [x["price"] for x in round_trips if x["origin"] == "ICN" and x["destination"] == "NRT" and x["price"]]
    gmp_hnd_prices = [x["price"] for x in round_trips if x["origin"] == "GMP" and x["destination"] == "HND" and x["price"]]
    out_prices = [x["price"] for x in ow_out if x["price"]]
    in_prices = [x["price"] for x in ow_in if x["price"]]

    icn_min = min(icn_nrt_prices) if icn_nrt_prices else None
    gmp_min = min(gmp_hnd_prices) if gmp_hnd_prices else None
    combo_min = (min(out_prices) + min(in_prices)) if (out_prices and in_prices) else None
    return icn_min, gmp_min, combo_min


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Tokyo Ariake Arena flights via SerpApi")
    parser.add_argument("--dry-run", action="store_true", help="Validate config & local JSON without calling SerpApi")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    now_kst = dt.datetime.now(KST)
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    today_str = now_kst.strftime("%Y-%m-%d")

    existing = load_existing_data()

    if args.dry_run:
        print(f"[DRY-RUN] {now_str}")
        print(f"[DRY-RUN] Data file: {DATA_PATH} (exists={DATA_PATH.exists()})")
        print(f"[DRY-RUN] SERPAPI_API_KEY configured: {bool(os.environ.get('SERPAPI_API_KEY'))}")
        print("[DRY-RUN] Ready to query 6 SerpApi Google Flights routes + 1 free /account.json call.")
        return 0

    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: SERPAPI_API_KEY environment variable is not set.", file=sys.stderr)
        print("Set it in .env (local) or GitHub Repository Secrets (Actions).", file=sys.stderr)
        return 1

    errors: List[str] = []

    # 1) Query One-Way Inbound first (so round-trip parser can cross-reference Tokyo dep >= 16:00)
    ow_in: List[Dict[str, Any]] = []
    for origin, dest in [("NRT", "ICN"), ("HND", "GMP")]:
        try:
            raw = fetch_serpapi_flights(api_key, {
                "type": "2",
                "departure_id": origin,
                "arrival_id": dest,
                "outbound_date": INBOUND_DATE,
                "outbound_times": "16,23",  # Tokyo departure 16:00 ~ 23:59
            })
            ow_in.extend(parse_one_way_list(raw, origin, dest, INBOUND_DATE, "in", min_depart_min=16 * 60))
        except Exception as exc:
            errors.append(f"One-way {origin}->{dest}: {exc}")

    # 2) Query One-Way Outbound (Korea departure <= 11:00)
    ow_out: List[Dict[str, Any]] = []
    for origin, dest in [("ICN", "NRT"), ("GMP", "HND")]:
        try:
            raw = fetch_serpapi_flights(api_key, {
                "type": "2",
                "departure_id": origin,
                "arrival_id": dest,
                "outbound_date": OUTBOUND_DATE,
                "outbound_times": "0,11",  # 00:00 ~ 11:59, then strict <= 11:00 filter
            })
            ow_out.extend(parse_one_way_list(raw, origin, dest, OUTBOUND_DATE, "out", max_depart_min=11 * 60))
        except Exception as exc:
            errors.append(f"One-way {origin}->{dest}: {exc}")

    # 3) Query Round-Trips (out <= 11:00, return Tokyo dep >= 16:00)
    round_trips: List[Dict[str, Any]] = []
    for origin, dest in [("ICN", "NRT"), ("GMP", "HND")]:
        try:
            raw = fetch_serpapi_flights(api_key, {
                "type": "1",
                "departure_id": origin,
                "arrival_id": dest,
                "outbound_date": OUTBOUND_DATE,
                "return_date": INBOUND_DATE,
                "outbound_times": "0,11",
                "return_times": "16,23",
            })
            round_trips.extend(parse_round_trip_list(raw, origin, dest, ow_in, max_depart_min=11 * 60))
        except Exception as exc:
            errors.append(f"Round-trip {origin}<->{dest}: {exc}")

    # 4) Fetch real-time remaining quota (FREE, 0 credits)
    quota_info: Dict[str, Any]
    try:
        account = fetch_serpapi_account(api_key)
        quota_info = compute_quota(account, now_kst)
    except Exception as exc:
        errors.append(f"SerpApi account quota check failed: {exc}")
        quota_info = existing.get("serpapi_quota") or {
            "plan_name": "Free Plan",
            "monthly_limit": 250,
            "this_month_usage": 0,
            "remaining_credits": 0,
            "credits_per_refresh": CREDITS_PER_REFRESH,
            "remaining_free_refreshes": 0,
            "remaining_midnight_runs_this_month": 0,
            "extra_manual_refreshes_safe": 0,
            "plan_renewal_date": None,
        }

    # Fallback to previous lists if an entire section failed due to transient network error
    if not round_trips and existing.get("round_trips"):
        round_trips = existing["round_trips"]
    if not ow_out and existing.get("one_way_outbound"):
        ow_out = existing["one_way_outbound"]
    if not ow_in and existing.get("one_way_inbound"):
        ow_in = existing["one_way_inbound"]

    # 5) Update daily price history (upsert by KST YYYY-MM-DD)
    icn_min, gmp_min, combo_min = compute_summary_mins(round_trips, ow_out, ow_in)
    history: List[Dict[str, Any]] = list(existing.get("history") or [])
    today_point = {
        "date": today_str,
        "timestamp_kst": now_str,
        "icn_nrt_rt_min": icn_min,
        "gmp_hnd_rt_min": gmp_min,
        "one_way_combo_min": combo_min,
    }
    replaced = False
    for idx, entry in enumerate(history):
        if entry.get("date") == today_str:
            history[idx] = today_point
            replaced = True
            break
    if not replaced:
        history.append(today_point)
    history = history[-90:]  # Keep up to 90 days of daily history

    output = {
        "schema_version": "1.0",
        "trip": {
            "title": "도쿄 아리아케 아레나 (2027.03.27~03.29)",
            "outbound_date": OUTBOUND_DATE,
            "inbound_date": INBOUND_DATE,
            "outbound_target_before": "10:00",
            "outbound_flex_before": "11:00",
            "inbound_tokyo_depart_target_after": "17:00",
            "inbound_tokyo_depart_flex_after": "16:00",
        },
        "updated_at_kst": now_str,
        "data_source": "serpapi",
        "serpapi_quota": quota_info,
        "round_trips": round_trips,
        "one_way_outbound": ow_out,
        "one_way_inbound": ow_in,
        "history": history,
        "errors": errors,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Saved {DATA_PATH} at {now_str}")
    print(f"     Round trips: {len(round_trips)} | OW Out: {len(ow_out)} | OW In: {len(ow_in)}")
    print(
        f"     SerpApi Quota: {quota_info['remaining_credits']}/{quota_info['monthly_limit']} credits left "
        f"({quota_info['remaining_free_refreshes']} free refreshes left)"
    )
    if errors:
        print(f"     Warnings ({len(errors)}): {errors}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
