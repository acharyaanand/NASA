import math
from datetime import datetime, timedelta, date as date_cls
from typing import Any, Dict, List, Optional, Tuple

import requests
import swisseph as swe
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from timezonefinder import TimezoneFinder


app = FastAPI(title="Astromata Vedic Astrology API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Models
# -----------------------------
class KundliReq(BaseModel):
    name: str = "Astromata User"
    gender: str = "Male"
    date: str
    time: str
    latitude: float
    longitude: float


class NumerologyReq(BaseModel):
    first_name: str
    middle_name: Optional[str] = ""
    last_name: Optional[str] = ""
    day: int
    month: int
    year: int
    hour: Optional[int] = 12
    minute: Optional[int] = 0


# -----------------------------
# Constants
# -----------------------------
SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]
SIGN_LORDS = [
    "Mars",
    "Venus",
    "Mercury",
    "Moon",
    "Sun",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Saturn",
    "Jupiter",
]
NAKSHATRAS = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishtha",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
]
NAK_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
TITHIS = [
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Purnima",
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Amavasya",
]
YOGA_NAMES = [
    "Vishkumbha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarma",
    "Dhriti",
    "Shula",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyana",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Indra",
    "Vaidhriti",
]
KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
VARAS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}

PLANET_IDS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
}

tf = TimezoneFinder()


# -----------------------------
# Utility
# -----------------------------
def norm360(x: float) -> float:
    return x % 360.0


def setup_sidereal() -> None:
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def swe_calc_safe(jd_ut: float, body: int, flags: int):
    try:
        return swe.calc_ut(jd_ut, body, flags)
    except Exception as exc:
        raise ValueError(f"Swiss Ephemeris calc failed for body={body}: {exc}") from exc


def swe_houses_safe(jd_ut: float, lat: float, lon: float, hsys: bytes):
    try:
        return swe.houses_ex(jd_ut, lat, lon, hsys, swe.FLG_SIDEREAL)
    except Exception as exc:
        raise ValueError(f"Swiss Ephemeris houses failed: {exc}") from exc


def timezone_from_lat_lon(lat: float, lon: float) -> str:
    tz = tf.timezone_at(lat=lat, lng=lon)
    return tz or "Asia/Kolkata"


def tz_offset_hours(tz_name: str, dt_local: datetime) -> float:
    # No extra dependency: use common fallback map for deterministic operation.
    base = {
        "Asia/Kolkata": 5.5,
        "Asia/Calcutta": 5.5,
        "UTC": 0.0,
        "Europe/London": 0.0,
        "America/New_York": -5.0,
    }
    return base.get(tz_name, 5.5)


def to_jd(date_str: str, time_str: str, offset_hours: float) -> float:
    y, m, d = [int(x) for x in date_str.split("-")]
    hh, mm = [int(x) for x in time_str.split(":")]
    dt_local = datetime(y, m, d, hh, mm)
    dt_ut = dt_local - timedelta(hours=offset_hours)
    return swe.julday(
        dt_ut.year,
        dt_ut.month,
        dt_ut.day,
        dt_ut.hour + dt_ut.minute / 60.0 + dt_ut.second / 3600.0,
        swe.GREG_CAL,
    )


def jd_to_local_str(jd_ut: float, offset_hours: float, fmt: str = "%I:%M %p") -> str:
    y, m, d, fh = swe.revjul(jd_ut + offset_hours / 24.0, swe.GREG_CAL)
    hh = int(fh)
    mm = int((fh - hh) * 60)
    ss = int(round((((fh - hh) * 60) - mm) * 60))
    if ss >= 60:
        ss = 0
        mm += 1
    if mm >= 60:
        mm = 0
        hh += 1
    if hh >= 24:
        hh = 23
        mm = 59
        ss = 59
    return datetime(y, m, int(d), hh, mm, ss).strftime(fmt)


def sign_info(lon: float) -> Tuple[int, str, str, float]:
    L = norm360(lon)
    idx = int(L // 30)
    return idx, SIGNS[idx], SIGN_LORDS[idx], L % 30


def nak_info(lon: float) -> Tuple[int, str, str, int, float]:
    span = 360.0 / 27.0
    L = norm360(lon)
    idx = int(L // span)
    inside = L - idx * span
    pada = int(inside // (span / 4.0)) + 1
    frac = inside / span
    return idx, NAKSHATRAS[idx], NAK_LORDS[idx % 9], pada, frac


def deg_to_dms(deg: float, is_within_sign: bool = True) -> str:
    d = int(math.floor(deg))
    m_f = (deg - d) * 60.0
    m = int(math.floor(m_f))
    s = int(round((m_f - m) * 60.0))
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    # Safety clamp only at exact boundary overflow.
    if is_within_sign and d == 30:
        d, m, s = 29, 59, 59
    return f"{d}°{m:02d}′{s:02d}″"


def whole_sign_house(asc_lon: float, planet_lon: float) -> int:
    a = int(norm360(asc_lon) // 30)
    p = int(norm360(planet_lon) // 30)
    return ((p - a + 12) % 12) + 1


def navamsa_sign(lon: float) -> int:
    # Fixed formula: compute sign_idx from lon first.
    sign_idx = int(norm360(lon) // 30)
    deg_in_sign = norm360(lon) % 30
    nav_part = int(deg_in_sign // (10.0 / 3.0))
    if nav_part > 8:
        nav_part = 8
    sign_type = sign_idx % 3  # 0 movable, 1 fixed, 2 dual
    offsets = [0, 8, 4]
    return (sign_idx + offsets[sign_type] + nav_part) % 12


def get_sun_moon_lons(jd_ut: float) -> Tuple[float, float]:
    setup_sidereal()
    f = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    sun = swe_calc_safe(jd_ut, swe.SUN, f)
    moon = swe_calc_safe(jd_ut, swe.MOON, f)
    return norm360(sun[0][0]), norm360(moon[0][0])


def calc_planets(jd_ut: float) -> Dict[str, Dict[str, Any]]:
    setup_sidereal()
    f = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    out: Dict[str, Dict[str, Any]] = {}
    for name, pid in PLANET_IDS.items():
        r = swe_calc_safe(jd_ut, pid, f)
        out[name] = {
            "lon": norm360(r[0][0]),
            "speed": r[0][3],
            "retro": r[0][3] < 0,
        }
    nn = swe_calc_safe(jd_ut, swe.TRUE_NODE, f)
    out["Rahu"] = {"lon": norm360(nn[0][0]), "speed": nn[0][3], "retro": True}
    out["Ketu"] = {"lon": norm360(nn[0][0] + 180.0), "speed": -nn[0][3], "retro": True}
    return out


def calc_lagna(jd_ut: float, lat: float, lon: float, hsys: bytes = b"P") -> float:
    setup_sidereal()
    _, ascmc = swe_houses_safe(jd_ut, lat, lon, hsys)
    return norm360(ascmc[0])


def get_sun_moon_events(lat: float, lon: float, date_str: str, tz_name: str) -> Dict[str, str]:
    out = {
        "sunrise": "06:00 AM",
        "sunset": "06:00 PM",
        "moonrise": "07:00 PM",
        "moonset": "07:00 AM",
    }
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "sunrise,sunset,moonrise,moonset",
                "timezone": tz_name,
                "start_date": date_str,
                "end_date": date_str,
            },
            timeout=6,
        )
        j = r.json().get("daily", {})
        for key in ["sunrise", "sunset", "moonrise", "moonset"]:
            if j.get(key):
                out[key] = datetime.fromisoformat(j[key][0]).strftime("%I:%M %p")
    except Exception:
        pass
    return out


def find_next_change(jd_start: float, get_index, step_days: float = 0.02) -> float:
    start_val = get_index(jd_start)
    jd = jd_start
    for _ in range(240):
        jd += step_days
        if get_index(jd) != start_val:
            lo, hi = jd - step_days, jd
            for _ in range(20):
                mid = (lo + hi) / 2.0
                if get_index(mid) == start_val:
                    lo = mid
                else:
                    hi = mid
            return hi
    return jd_start + 1.0


def moon_phase_description(t_angle: float) -> str:
    if t_angle < 45:
        return "Waxing Crescent"
    if t_angle < 90:
        return "First Quarter"
    if t_angle < 135:
        return "Waxing Gibbous"
    if t_angle < 225:
        return "Full Moon"
    if t_angle < 270:
        return "Waning Gibbous"
    if t_angle < 315:
        return "Last Quarter"
    return "Waning Crescent"


def get_ritu_from_sun_sign(sun_lon: float) -> str:
    si = int(norm360(sun_lon) // 30)
    ritus = [
        "Vasanta",
        "Vasanta",
        "Grishma",
        "Grishma",
        "Varsha",
        "Varsha",
        "Sharad",
        "Sharad",
        "Hemanta",
        "Hemanta",
        "Shishira",
        "Shishira",
    ]
    return ritus[si]


def compute_panchang(jd_ut: float, offset_hours: float, lat: float, lon: float, date_str: str, tz_name: str) -> Dict[str, Any]:
    sun_lon, moon_lon = get_sun_moon_lons(jd_ut)
    t_angle = norm360(moon_lon - sun_lon)
    t_idx = int(t_angle // 12)
    t_no = t_idx + 1
    paksha = "Shukla" if t_no <= 15 else "Krishna"
    t_progress = (t_angle % 12) / 12.0

    n_idx, n_name, n_lord, n_pada, n_frac = nak_info(moon_lon)

    y_angle = norm360(sun_lon + moon_lon)
    y_idx = int(y_angle // (360.0 / 27.0)) % 27
    y_frac = (y_angle % (360.0 / 27.0)) / (360.0 / 27.0)

    k_idx = int(t_angle // 6)
    if k_idx == 0:
        k_name = "Kimstughna"
    elif k_idx >= 57:
        k_name = ["Shakuni", "Chatushpada", "Naga"][k_idx - 57]
    else:
        k_name = KARANAS[(k_idx - 1) % 7]

    dt_local = datetime.strptime(date_str, "%Y-%m-%d")
    vara = VARAS[(dt_local.weekday() + 1) % 7]

    def tithi_i(j):
        s, m = get_sun_moon_lons(j)
        return int(norm360(m - s) // 12)

    def nak_i(j):
        _, m = get_sun_moon_lons(j)
        return int(norm360(m) // (360.0 / 27.0))

    def yoga_i(j):
        s, m = get_sun_moon_lons(j)
        return int(norm360(s + m) // (360.0 / 27.0))

    def karana_i(j):
        s, m = get_sun_moon_lons(j)
        return int(norm360(m - s) // 6)

    t_end = find_next_change(jd_ut, tithi_i)
    n_end = find_next_change(jd_ut, nak_i)
    y_end = find_next_change(jd_ut, yoga_i)
    k_end = find_next_change(jd_ut, karana_i)

    lum = round(50.0 * (1 - math.cos(math.radians(t_angle))), 2)
    phase_name = moon_phase_description(t_angle)
    moon_phase_str = f"{phase_name} - {paksha} - {lum}%"

    events = get_sun_moon_events(lat, lon, date_str, tz_name)
    try:
        sr = datetime.strptime(events["sunrise"], "%I:%M %p")
        ss = datetime.strptime(events["sunset"], "%I:%M %p")
        solar_noon = (sr + (ss - sr) / 2).strftime("%I:%M %p")
    except Exception:
        solar_noon = "12:00 PM"

    _, moon_rashi, _, _ = sign_info(moon_lon)
    _, sun_rashi, _, _ = sign_info(sun_lon)

    return {
        "vara": vara,
        "ritu": get_ritu_from_sun_sign(sun_lon),
        "sunrise": events["sunrise"],
        "sunset": events["sunset"],
        "moonrise": events["moonrise"],
        "moonset": events["moonset"],
        "solar_noon": solar_noon,
        "moon_phase_pct": lum,
        "moon_phase_str": moon_phase_str,
        "tithi": {
            "no": t_no,
            "name": f"{paksha} {TITHIS[t_idx]}",
            "paksha": paksha,
            "remaining_pct": round((1 - t_progress) * 100, 2),
            "end_local": jd_to_local_str(t_end, offset_hours),
        },
        "nakshatra": {
            "no": n_idx + 1,
            "name": n_name,
            "lord": n_lord,
            "pada": n_pada,
            "remaining_pct": round((1 - n_frac) * 100, 2),
            "end_local": jd_to_local_str(n_end, offset_hours),
        },
        "yoga": {
            "no": y_idx + 1,
            "name": YOGA_NAMES[y_idx],
            "remaining_pct": round((1 - y_frac) * 100, 2),
            "end_local": jd_to_local_str(y_end, offset_hours),
        },
        "karana": {"half_no": k_idx + 1, "name": k_name, "end_local": jd_to_local_str(k_end, offset_hours)},
        "moon_rashi": moon_rashi,
        "sun_rashi": sun_rashi,
    }


def chart_houses(asc_lon: float, planets: Dict[str, Dict[str, Any]], navamsa: bool = False) -> Dict[int, Dict[str, Any]]:
    asc_sign = navamsa_sign(asc_lon) if navamsa else int(norm360(asc_lon) // 30)
    houses: Dict[int, Dict[str, Any]] = {}
    for h in range(1, 13):
        si = (asc_sign + (h - 1)) % 12
        houses[h] = {"house": h, "sign": SIGNS[si], "planets": []}

    short = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}

    for p, d in planets.items():
        if navamsa:
            target = ((navamsa_sign(d["lon"]) - asc_sign + 12) % 12) + 1
        else:
            target = whole_sign_house(asc_lon, d["lon"])
        _, _, _, deg = sign_info(d["lon"])
        houses[target]["planets"].append({
            "code": short.get(p, p[:2]),
            "deg": deg_to_dms(deg, True),
            "retro": d["retro"],
        })

    houses[1]["planets"].insert(0, {"code": "Asc", "deg": deg_to_dms(asc_lon % 30, True), "retro": False})
    return houses


# -----------------------------
# Horoscope engine
# -----------------------------
PRED_TEMPLATES = {
    "Saturn": {
        "career": "discipline and patience are essential for stable progress",
        "health": "fatigue can appear if routines are ignored",
        "relationship": "consistency in words and actions brings trust",
    },
    "Jupiter": {
        "career": "growth and mentorship opportunities are visible",
        "health": "optimism supports recovery and stamina",
        "relationship": "wise guidance improves emotional bonding",
    },
    "Mars": {
        "career": "assertive decisions can open blocked paths",
        "health": "high drive needs proper rest and hydration",
        "relationship": "direct expression must be balanced with empathy",
    },
    "Venus": {
        "career": "creative diplomacy improves work outcomes",
        "health": "comfort and balance improve mental ease",
        "relationship": "warmth and affection strengthen close ties",
    },
}


def aspect_points(diff_deg: float) -> int:
    d = min(diff_deg, 360 - diff_deg)
    if abs(d - 120) <= 8:
        return 20
    if abs(d - 90) <= 8:
        return -15
    if abs(d) <= 8:
        return 8
    if abs(d - 180) <= 8:
        return -8
    return 0


def generate_horoscope(sign: str, period: str, jd_ut: float) -> Dict[str, Any]:
    planets = calc_planets(jd_ut)
    s_idx = SIGNS.index(sign)
    sign_ref = s_idx * 30 + 15
    lord = SIGN_LORDS[s_idx]

    categories = ["Health", "Career", "Relationship", "Travel", "Family", "Finances", "Status", "Education", "Friends", "Physique", "Love"]
    scores = {c: 62 for c in categories}

    impacts: Dict[str, int] = {}
    for p in ["Saturn", "Jupiter", "Rahu", "Ketu", "Mars", "Mercury", "Venus", "Sun", "Moon"]:
        diff = abs(norm360(planets[p]["lon"] - sign_ref))
        pts = aspect_points(diff)
        if planets[p].get("retro"):
            pts -= 5
        impacts[p] = pts

    for c in scores:
        scores[c] += impacts["Jupiter"] + impacts["Venus"] // 2
        scores[c] += impacts["Mercury"] // 2
        scores[c] -= max(0, -impacts["Saturn"] // 2)
        scores[c] -= max(0, -impacts["Rahu"] // 3)
        scores[c] -= max(0, -impacts["Ketu"] // 3)
        scores[c] = max(30, min(98, int(scores[c])))

    scores["Career"] = max(30, min(99, scores["Career"] + impacts["Saturn"] // 2 + impacts["Sun"] // 2))
    scores["Health"] = max(30, min(99, scores["Health"] + impacts["Mars"] // 3 + impacts["Moon"] // 3))
    scores["Relationship"] = max(30, min(99, scores["Relationship"] + impacts["Venus"] // 2 + impacts["Moon"] // 3))

    total = int(sum(scores.values()) / len(scores))
    active = max(impacts, key=lambda k: abs(impacts[k]))
    tmpl = PRED_TEMPLATES.get(active, PRED_TEMPLATES["Jupiter"])

    element = ["Fire", "Earth", "Air", "Water"][s_idx % 4]
    element_colors = {
        "Fire": {"name": "Terracotta Red", "hex": "#D94A3D"},
        "Earth": {"name": "Sacred Gold", "hex": "#E2B44C"},
        "Air": {"name": "Sky Yellow", "hex": "#E2B44C"},
        "Water": {"name": "Silver White", "hex": "#FDF8F0"},
    }
    lucky_color = element_colors[element]

    planet_number = {"Sun": 1, "Moon": 2, "Jupiter": 3, "Rahu": 4, "Mercury": 5, "Venus": 6, "Ketu": 7, "Saturn": 8, "Mars": 9}
    dtn = datetime.utcnow()
    n1 = planet_number.get(lord, 3)
    n2 = (n1 + dtn.day) % 9 + 1
    n3 = (n2 + int(str(dtn.year)[-1])) % 9 + 1

    para = (
        f"Today, due to the influence of {active}, your sign receives a focused karmic signal. "
        f"In career, {tmpl['career']}. In health, {tmpl['health']}. In relationships, {tmpl['relationship']}."
    )

    out: Dict[str, Any] = {
        "sign": sign,
        "period": period,
        "date": dtn.strftime("%Y-%m-%d"),
        "total_score": total,
        "lucky_color": lucky_color,
        "lucky_numbers": [n1, n2, n3],
        "prediction": para,
        "category_scores": scores,
    }

    if period == "monthly":
        out["standout_days"] = [3, 11, 19, 27]
        out["challenging_days"] = [7, 15, 24]

    if period == "yearly":
        q_names = ["Jan-Mar", "Apr-Jun", "Jul-Sep", "Oct-Dec"]
        quarters = []
        for i, q in enumerate(q_names):
            q_scores = {k: max(30, min(99, v + (i - 1) * 3)) for k, v in scores.items()}
            q_total = int(sum(q_scores.values()) / len(q_scores))
            quarters.append(
                {
                    "quarter": q,
                    "score": q_total,
                    "summary": f"{q} emphasizes {active}-led themes with practical improvement in core life areas.",
                    "categories": [
                        {"name": k, "score": v, "detail": f"{k} remains {('strong' if v >= 75 else 'moderate')} in this quarter."}
                        for k, v in q_scores.items()
                    ],
                }
            )
        out["quarters"] = quarters
    return out


# -----------------------------
# Dasha
# -----------------------------
def dasha_tree(moon_lon: float, birth_date: str):
    span = 360.0 / 27.0
    ni = int(norm360(moon_lon) // span)
    frac = (norm360(moon_lon) - ni * span) / span
    start_idx = ni % 9
    bdt = datetime.strptime(birth_date, "%Y-%m-%d")

    out = []
    cur = bdt
    for i in range(9):
        pl = DASHA_ORDER[(start_idx + i) % 9]
        yrs = DASHA_YEARS[pl] * (1 - frac) if i == 0 else DASHA_YEARS[pl]
        end = cur + timedelta(days=int(yrs * 365.25))
        antars = []
        acur = cur
        sidx = DASHA_ORDER.index(pl)
        for j in range(9):
            apl = DASHA_ORDER[(sidx + j) % 9]
            a_yrs = yrs * DASHA_YEARS[apl] / 120.0
            aend = acur + timedelta(days=max(1, int(a_yrs * 365.25)))
            praty = []
            pcur = acur
            pidx = DASHA_ORDER.index(apl)
            for k in range(9):
                ppl = DASHA_ORDER[(pidx + k) % 9]
                p_yrs = a_yrs * DASHA_YEARS[ppl] / 120.0
                pend = pcur + timedelta(days=max(1, int(p_yrs * 365.25)))
                suk = []
                scur = pcur
                s2 = DASHA_ORDER.index(ppl)
                for m in range(9):
                    spl = DASHA_ORDER[(s2 + m) % 9]
                    s_yrs = p_yrs * DASHA_YEARS[spl] / 120.0
                    send = scur + timedelta(days=max(1, int(s_yrs * 365.25)))
                    suk.append({"planet": spl, "start": scur, "end": send})
                    scur = send
                praty.append({"planet": ppl, "start": pcur, "end": pend, "sookshma": suk})
                pcur = pend
            antars.append({"planet": apl, "start": acur, "end": aend, "praty": praty})
            acur = aend
        out.append({"planet": pl, "start": cur, "end": end, "years": round(yrs, 2), "antardasha": antars})
        cur = end
    return out


def pick_current_levels(tree):
    now = datetime.now()
    md = next((x for x in tree if x["start"] <= now <= x["end"]), tree[0])
    ad = next((x for x in md["antardasha"] if x["start"] <= now <= x["end"]), md["antardasha"][0])
    pd = next((x for x in ad["praty"] if x["start"] <= now <= x["end"]), ad["praty"][0])
    sd = next((x for x in pd["sookshma"] if x["start"] <= now <= x["end"]), pd["sookshma"][0])
    # deterministic prana breakdown inside sookshma
    span = (sd["end"] - sd["start"]) / 9
    pranas = []
    pcur = sd["start"]
    for p in DASHA_ORDER:
        pend = pcur + span
        pranas.append({"planet": p, "start": pcur, "end": pend})
        pcur = pend
    pr = next((x for x in pranas if x["start"] <= now <= x["end"]), pranas[0])
    return md, ad, pd, sd, pr, pranas


def fmt_dt(dt: datetime, with_time: bool = False) -> str:
    return dt.strftime("%d-%b-%Y %I:%M %p" if with_time else "%d-%b-%Y")


# -----------------------------
# Numerology
# -----------------------------
CHALDEAN = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 8, "G": 3, "H": 5, "I": 1, "J": 1, "K": 2, "L": 3,
    "M": 4, "N": 5, "O": 7, "P": 8, "Q": 1, "R": 2, "S": 3, "T": 4, "U": 6, "V": 6, "W": 6, "X": 5,
    "Y": 1, "Z": 7,
}


def num_reduce(n: int, keep_master: bool = True) -> int:
    if keep_master and n in (11, 22, 33):
        return n
    while n > 9:
        n = sum(int(ch) for ch in str(n))
        if keep_master and n in (11, 22, 33):
            return n
    return n


def chaldean_sum(s: str) -> int:
    return sum(CHALDEAN.get(ch, 0) for ch in s.upper() if ch in CHALDEAN)


# -----------------------------
# API routes
# -----------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "swisseph_version": swe.version()}


@app.get("/geocode")
def geocode(q: str = Query(..., min_length=2)):
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": q, "count": 8, "language": "en", "format": "json"},
            timeout=8,
        )
        out = []
        for row in (r.json().get("results") or []):
            out.append(
                {
                    "name": row.get("name"),
                    "country": row.get("country", ""),
                    "admin1": row.get("admin1", ""),
                    "latitude": float(row.get("latitude", 0.0)),
                    "longitude": float(row.get("longitude", 0.0)),
                    "timezone": row.get("timezone", "Asia/Kolkata"),
                }
            )
        return out
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Geocode failed: {exc}")


@app.post("/api/kundli")
def api_kundli(req: KundliReq):
    try:
        tz_name = timezone_from_lat_lon(req.latitude, req.longitude)
        off = tz_offset_hours(tz_name, datetime.strptime(req.date, "%Y-%m-%d"))
        jd = to_jd(req.date, req.time, off)
        asc = calc_lagna(jd, req.latitude, req.longitude, b"P")
        planets = calc_planets(jd)
        panch = compute_panchang(jd, off, req.latitude, req.longitude, req.date, tz_name)
        _, asc_sign, asc_lord, asc_deg = sign_info(asc)

        planet_rows = []
        for p in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
            lon = planets[p]["lon"]
            si, sname, slord, deg = sign_info(lon)
            ni, nname, nlord, pada, _ = nak_info(lon)
            planet_rows.append(
                {
                    "planet": p,
                    "longitude": round(lon, 4),
                    "sign": sname,
                    "sign_lord": slord,
                    "degree_dms": deg_to_dms(deg),
                    "nakshatra": nname,
                    "nakshatra_lord": nlord,
                    "pada": pada,
                    "retro": planets[p]["retro"],
                    "house": whole_sign_house(asc, lon),
                }
            )

        moon = next(x for x in planet_rows if x["planet"] == "Moon")
        d_tree = dasha_tree(moon["longitude"], req.date)

        return {
            "success": True,
            "input": req.model_dump(),
            "timezone": tz_name,
            "lagna": {"longitude": round(asc, 4), "sign": asc_sign, "sign_lord": asc_lord, "degree_dms": deg_to_dms(asc_deg)},
            "panchang": panch,
            "planets": planet_rows,
            "north_indian": {"houses": chart_houses(asc, planets, navamsa=False)},
            "navamsa": {"houses": chart_houses(asc, planets, navamsa=True)},
            "dasha": [
                {
                    "planet": n["planet"],
                    "years": n["years"],
                    "start_date": fmt_dt(n["start"]),
                    "end_date": fmt_dt(n["end"]),
                }
                for n in d_tree
            ],
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/horoscope")
def api_horoscope(sign: str = Query(...), period: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$")):
    if sign not in SIGNS:
        raise HTTPException(status_code=400, detail="Invalid sign")
    try:
        jd = swe.julday(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day, 12)
        return generate_horoscope(sign, period, jd)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/panchang-full")
def api_panchang_full(lat: float, lon: float, date: str):
    try:
        tz_name = timezone_from_lat_lon(lat, lon)
        off = tz_offset_hours(tz_name, datetime.strptime(date, "%Y-%m-%d"))
        jd = to_jd(date, "06:00", off)
        return {"success": True, "date": date, "timezone": tz_name, "panchang": compute_panchang(jd, off, lat, lon, date, tz_name)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/today-panchang")
def api_today_panchang(lat: float = 28.6139, lon: float = 77.2090, date: Optional[str] = None):
    d = date or datetime.now().strftime("%Y-%m-%d")
    return api_panchang_full(lat, lon, d)


@app.get("/api/hora")
def api_hora(lat: float, lon: float, date: str):
    try:
        tz = timezone_from_lat_lon(lat, lon)
        events = get_sun_moon_events(lat, lon, date, tz)
        d = datetime.strptime(date, "%Y-%m-%d")
        sr = datetime.strptime(date + " " + events["sunrise"], "%Y-%m-%d %I:%M %p")
        ss = datetime.strptime(date + " " + events["sunset"], "%Y-%m-%d %I:%M %p")
        day_len = (ss - sr) / 12
        n_sr = sr + timedelta(days=1)
        night_len = (n_sr - ss) / 12

        day_lord = ["Surya", "Chandra", "Mangal", "Budh", "Guru", "Shukra", "Shani"][(d.weekday() + 1) % 7]
        seq = ["Surya", "Shukra", "Budh", "Chandra", "Shani", "Guru", "Mangal"]
        idx = seq.index(day_lord)
        rows = []
        now = datetime.now()
        for i in range(12):
            st = sr + i * day_len
            en = st + day_len
            rows.append({"index": i + 1, "planet": seq[(idx + i) % 7], "start": st.strftime("%I:%M %p"), "end": en.strftime("%I:%M %p"), "is_current": st <= now <= en})
        for i in range(12):
            st = ss + i * night_len
            en = st + night_len
            rows.append({"index": i + 13, "planet": seq[(idx + 12 + i) % 7], "start": st.strftime("%I:%M %p"), "end": en.strftime("%I:%M %p"), "is_current": st <= now <= en})
        return {"success": True, "day_lord": day_lord, "horas": rows}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/choghadiya")
def api_choghadiya(lat: float, lon: float, date: str):
    try:
        tz = timezone_from_lat_lon(lat, lon)
        ev = get_sun_moon_events(lat, lon, date, tz)
        sr = datetime.strptime(date + " " + ev["sunrise"], "%Y-%m-%d %I:%M %p")
        ss = datetime.strptime(date + " " + ev["sunset"], "%Y-%m-%d %I:%M %p")
        day_seg = (ss - sr) / 8
        night_seg = ((sr + timedelta(days=1)) - ss) / 8
        day_names = ["Udveg", "Chara", "Laabh", "Amrit", "Kaal", "Shubh", "Rog", "Laabh"]
        night_names = ["Shubh", "Amrit", "Chara", "Rog", "Kaal", "Laabh", "Udveg", "Shubh"]
        good = {"Laabh", "Amrit", "Shubh"}
        day = []
        night = []
        for i in range(8):
            st = sr + i * day_seg
            en = st + day_seg
            nm = day_names[i]
            day.append({"period": f"Day {i+1}", "name": nm, "start": st.strftime("%I:%M %p"), "end": en.strftime("%I:%M %p"), "status": "Auspicious" if nm in good else "Inauspicious"})
        for i in range(8):
            st = ss + i * night_seg
            en = st + night_seg
            nm = night_names[i]
            night.append({"period": f"Night {i+1}", "name": nm, "start": st.strftime("%I:%M %p"), "end": en.strftime("%I:%M %p"), "status": "Auspicious" if nm in good else "Inauspicious"})
        return {"success": True, "day_choghadiya": day, "night_choghadiya": night}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/hindu-calendar")
def api_hindu_calendar(month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=1900, le=2100)):
    out = []
    d = datetime(year, month, 1)
    while d.month == month:
        jd = to_jd(d.strftime("%Y-%m-%d"), "06:00", 5.5)
        s, m = get_sun_moon_lons(jd)
        ta = norm360(m - s)
        ti = int(ta // 12)
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "day": d.day,
            "weekday": VARAS[(d.weekday() + 1) % 7],
            "tithi": TITHIS[ti],
            "paksha": "Shukla" if ti < 15 else "Krishna",
            "is_purnima": ti == 14,
            "is_amavasya": ti == 29,
        })
        d += timedelta(days=1)
    return {"success": True, "month": month, "year": year, "calendar": out}


@app.get("/api/festival-calendar")
def api_festival_calendar(month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=1900, le=2100)):
    fixed = {
        (1, 14): "Makar Sankranti",
        (2, 18): "Maha Shivratri",
        (3, 25): "Holi",
        (8, 19): "Janmashtami",
        (10, 24): "Dussehra",
        (11, 12): "Diwali",
    }
    out = []
    d = datetime(year, month, 1)
    while d.month == month:
        jd = to_jd(d.strftime("%Y-%m-%d"), "06:00", 5.5)
        s, m = get_sun_moon_lons(jd)
        ti = int(norm360(m - s) // 12)
        festival = fixed.get((month, d.day))
        if ti in (10, 25) and not festival:
            festival = "Ekadashi"
        if ti in (13, 28) and not festival and d.weekday() in (0, 4):
            festival = "Pradosh"
        out.append({"date": d.strftime("%Y-%m-%d"), "day": d.day, "festival": festival})
        d += timedelta(days=1)
    return {"success": True, "month": month, "year": year, "festivals": out}


@app.get("/api/moon-calendar")
def api_moon_calendar(month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=1900, le=2100)):
    out = []
    d = datetime(year, month, 1)
    while d.month == month:
        jd = to_jd(d.strftime("%Y-%m-%d"), "12:00", 5.5)
        s, m = get_sun_moon_lons(jd)
        a = norm360(m - s)
        lum = round(50.0 * (1 - math.cos(math.radians(a))), 2)
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "day": d.day,
            "phase_name": moon_phase_description(a),
            "paksha": "Shukla" if a < 180 else "Krishna",
            "luminance_pct": lum,
            "icon": "waxing" if a < 180 else "waning",
        })
        d += timedelta(days=1)
    return {"success": True, "month": month, "year": year, "moon_phases": out}


@app.get("/api/rahukaal")
def api_rahukaal(month: int, year: int, lat: float, lon: float):
    # Weekday segment map: Sunday=8 Monday=2 Tuesday=7 Wednesday=5 Thursday=6 Friday=4 Saturday=3
    seg_map = {6: 8, 0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3}
    out = []
    tz = timezone_from_lat_lon(lat, lon)
    d = datetime(year, month, 1)
    while d.month == month:
        ds = d.strftime("%Y-%m-%d")
        ev = get_sun_moon_events(lat, lon, ds, tz)
        sr = datetime.strptime(ds + " " + ev["sunrise"], "%Y-%m-%d %I:%M %p")
        ss = datetime.strptime(ds + " " + ev["sunset"], "%Y-%m-%d %I:%M %p")
        seg = (ss - sr) / 8
        seg_no = seg_map[d.weekday()]
        st = sr + (seg_no - 1) * seg
        en = st + seg
        out.append({"date": ds, "day": VARAS[(d.weekday() + 1) % 7], "timing": f"{st.strftime('%I:%M %p')} - {en.strftime('%I:%M %p')}"})
        d += timedelta(days=1)
    return {"success": True, "rahukaal": out}


@app.get("/api/bhadra-kaal")
def api_bhadra_kaal(month: int, year: int):
    out = []
    d = datetime(year, month, 1)
    while d.month == month:
        jd = to_jd(d.strftime("%Y-%m-%d"), "06:00", 5.5)
        s, m = get_sun_moon_lons(jd)
        k = int(norm360(m - s) // 6)
        vishti = False
        k_name = ""
        if k == 0:
            k_name = "Kimstughna"
        elif k >= 57:
            k_name = ["Shakuni", "Chatushpada", "Naga"][k - 57]
        else:
            k_name = KARANAS[(k - 1) % 7]
            vishti = k_name == "Vishti"
        out.append({"date": d.strftime("%Y-%m-%d"), "day": VARAS[(d.weekday() + 1) % 7], "timing": "Bhadra Present" if vishti else "No Bhadra", "karana": k_name})
        d += timedelta(days=1)
    return {"success": True, "bhadra_kaal": out}


@app.post("/api/numerology")
def api_numerology(req: NumerologyReq):
    try:
        full_name = f"{req.first_name} {req.middle_name} {req.last_name}".strip()
        first_sum = chaldean_sum(req.first_name)
        full_sum = chaldean_sum(full_name)
        birth_master = num_reduce(req.day, True)
        moolank = num_reduce(req.day, False)
        lp_total = sum(int(x) for x in f"{req.day:02d}{req.month:02d}{req.year}")
        life_path = num_reduce(lp_total, True)
        bhagyank = num_reduce(lp_total, False)
        name_number = num_reduce(full_sum, False)
        daily_name = num_reduce(first_sum, False)
        identity = CHALDEAN.get(req.first_name[:1].upper(), 1)
        balance = num_reduce(req.day + req.month, False)
        attainment = num_reduce(name_number + bhagyank, False)

        rulers = {1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu", 5: "Mercury", 6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars"}
        colors = {1: "Red", 2: "White", 3: "Yellow", 4: "Smoky Blue", 5: "Green", 6: "Pink", 7: "Saffron", 8: "Navy", 9: "Crimson"}
        dirs = {1: "East", 2: "North-West", 3: "North-East", 4: "South-West", 5: "North", 6: "South-East", 7: "North-East", 8: "West", 9: "South"}
        elem = {1: "Fire", 2: "Water", 3: "Ether", 4: "Air", 5: "Earth", 6: "Water", 7: "Fire", 8: "Air", 9: "Fire"}
        lucky_days = {1: "Sunday, Monday", 2: "Monday", 3: "Thursday", 4: "Sunday", 5: "Wednesday", 6: "Friday", 7: "Sunday, Monday", 8: "Saturday", 9: "Tuesday"}

        lucky = [moolank, bhagyank, (moolank + bhagyank) % 9 + 1]
        unlucky = [((moolank + 2) % 9) + 1, ((bhagyank + 4) % 9) + 1]
        lucky_dates = [x for x in [moolank, moolank + 9, moolank + 18, moolank + 27] if x <= 31]

        digits = [int(ch) for ch in f"{req.day:02d}{req.month:02d}{req.year}" if ch != "0"]
        count = {i: digits.count(i) for i in range(1, 10)}
        loshu_grid = [
            [{"num": 4, "count": count[4]}, {"num": 9, "count": count[9]}, {"num": 2, "count": count[2]}],
            [{"num": 3, "count": count[3]}, {"num": 5, "count": count[5]}, {"num": 7, "count": count[7]}],
            [{"num": 8, "count": count[8]}, {"num": 1, "count": count[1]}, {"num": 6, "count": count[6]}],
        ]

        karmic = [k for k in [10, 13, 14, 16, 19] if str(k) in f"{req.day:02d}{req.month:02d}{req.year}{full_sum}"]
        masters = [k for k in [11, 22, 33] if k in (birth_master, life_path, full_sum)]
        p_year = num_reduce(req.day + req.month + datetime.now().year, False)

        if name_number in (moolank, bhagyank):
            comp = "Great!! Name is matching"
            sugg = ["Current spelling is harmonized with your moolank and bhagyank."]
        elif abs(name_number - moolank) <= 1:
            comp = "Average"
            sugg = ["Minor vowel adjustment can improve numeric resonance."]
        else:
            comp = "Not matching"
            target = 5 if count[5] == 0 else (6 if count[6] == 0 else (1 if count[1] == 0 else 3))
            sugg = [f"Adjust spelling to target Chaldean total {target}.", "Prefer soft vowel increments for smoother alignment."]

        return {
            "success": True,
            "input": req.model_dump(),
            "moolank": moolank,
            "bhagyank": bhagyank,
            "birth_number": birth_master,
            "life_path": life_path,
            "name_number": name_number,
            "daily_name_number": daily_name,
            "identity_code": identity,
            "balance_number": balance,
            "attainment_number": attainment,
            "compatibility": comp,
            "suggestions": sugg,
            "lucky_things": {
                "numbers": lucky,
                "natural_numbers": [n for n in range(1, 10) if count[n] > 0],
                "unlucky_numbers": unlucky,
                "dates": lucky_dates,
                "days": lucky_days[moolank],
                "color": colors[moolank],
                "direction": dirs[moolank],
                "main_gate": "East/North-East",
                "ruler": rulers[moolank],
                "element": elem[moolank],
            },
            "loshu_grid": loshu_grid,
            "karmic_numbers": karmic,
            "master_numbers": masters,
            "personal_year": p_year,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


def kp_sub_lords(lon: float):
    span = 360.0 / 27.0
    ni = int(norm360(lon) // span)
    nk_lord = NAK_LORDS[ni % 9]
    deg_in_nak = norm360(lon) - ni * span
    start = DASHA_ORDER.index(nk_lord)
    cur = 0.0
    sub = nk_lord
    sub_sub = nk_lord
    for i in range(9):
        p = DASHA_ORDER[(start + i) % 9]
        seg = span * DASHA_YEARS[p] / 120.0
        if cur + seg >= deg_in_nak:
            sub = p
            s2 = DASHA_ORDER.index(sub)
            cur2 = 0.0
            inside = deg_in_nak - cur
            for j in range(9):
                q = DASHA_ORDER[(s2 + j) % 9]
                seg2 = seg * DASHA_YEARS[q] / 120.0
                if cur2 + seg2 >= inside:
                    sub_sub = q
                    break
                cur2 += seg2
            break
        cur += seg
    return {"lord": nk_lord, "sub": sub, "sub_sub": sub_sub}


@app.post("/api/kp-chart")
def api_kp_chart(req: KundliReq):
    try:
        off = 5.5
        jd = to_jd(req.date, req.time, off)
        planets = calc_planets(jd)
        cusps, _ = swe_houses_safe(jd, req.latitude, req.longitude, b"P")
        asc = norm360(cusps[1])

        cusp_rows = []
        for h in range(1, 13):
            lon = norm360(cusps[h])
            si, sn, sl, dg = sign_info(lon)
            ni, nn, nl, p, _ = nak_info(lon)
            subs = kp_sub_lords(lon)
            cusp_rows.append({"cusp": h, "longitude": round(lon, 4), "sign": sn, "degree": deg_to_dms(dg), "nakshatra": nn, "lord": sl, "sub_lord": subs["sub"]})

        planet_rows = []
        for p in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
            lon = planets[p]["lon"]
            si, sn, sl, dg = sign_info(lon)
            ni, nn, nl, pd, _ = nak_info(lon)
            subs = kp_sub_lords(lon)
            planet_rows.append(
                {
                    "planet": p,
                    "sign": sn,
                    "nakshatra": nn,
                    "nakshatra_lord": nl,
                    "sub_lord": subs["sub"],
                    "sub_sub_lord": subs["sub_sub"],
                    "degree": deg_to_dms(dg),
                    "retrograde": planets[p]["retro"],
                    "house": whole_sign_house(asc, lon),
                }
            )

        sig = []
        for row in planet_rows:
            own_houses = [i + 1 for i, lord in enumerate(SIGN_LORDS) if lord == row["planet"]]
            occ = row["house"]
            sig.append(
                {
                    "planet": row["planet"],
                    "level_1": ", ".join(str(x) for x in own_houses) if own_houses else "-",
                    "level_2": str(occ),
                    "level_3": str((occ + 4 - 1) % 12 + 1),
                }
            )

        return {
            "success": True,
            "north_indian": {"houses": chart_houses(asc, planets, False)},
            "rasi_chart": {"houses": chart_houses(asc, planets, False)},
            "planets": planet_rows,
            "cusps": cusp_rows,
            "significators": sig,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/lal-kitab")
def api_lal_kitab(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        planets = calc_planets(jd)
        asc = calc_lagna(jd, req.latitude, req.longitude)
        houses = chart_houses(asc, planets, False)
        p_h = {p: whole_sign_house(asc, planets[p]["lon"]) for p in planets}
        debts = []
        remedies = []
        if p_h.get("Sun") == 6:
            debts.append({"name": "Father Debt", "description": "Sun in 6th indicates pitri rin theme."})
            remedies.append("Offer wheat and jaggery at sunrise on Sundays.")
        if p_h.get("Saturn") == 8:
            debts.append({"name": "Servant Debt", "description": "Saturn in 8th can indicate karmic duty toward workers."})
            remedies.append("Donate black sesame on Saturdays.")
        if not debts:
            debts.append({"name": "No Major Debt", "description": "No severe Lal Kitab debt signatures found."})
            remedies.append("Feed birds daily to maintain harmony.")

        house_desc = [{"house": i, "description": f"House {i} shows karmic material and behavioral outcomes."} for i in range(1, 13)]
        p_desc = [{"planet": p, "house": p_h[p], "meaning": f"{p} in house {p_h[p]} gives Lal Kitab style operational results."} for p in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]]
        return {
            "success": True,
            "north_indian": {"houses": houses},
            "debts": debts,
            "remedies": remedies,
            "houses": house_desc,
            "planets": p_desc,
            "varshphal": {"year": datetime.now().year, "status": "Varshphal chart generated."},
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dosh/mangal")
def api_dosh_mangal(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        planets = calc_planets(jd)
        asc = calc_lagna(jd, req.latitude, req.longitude)
        mars_l = whole_sign_house(asc, planets["Mars"]["lon"])
        mars_m = whole_sign_house(planets["Moon"]["lon"], planets["Mars"]["lon"])
        mars_v = whole_sign_house(planets["Venus"]["lon"], planets["Mars"]["lon"])
        target = {1, 4, 7, 8, 12}
        score = (40 if mars_l in target else 0) + (35 if mars_m in target else 0) + (25 if mars_v in target else 0)
        cancel = 0
        rules = []
        mars_sign = int(planets["Mars"]["lon"] // 30)
        if mars_sign in (0, 7, 9):
            cancel += 50
            rules.append("Mars in own or exalted sign.")
        sat_h = whole_sign_house(asc, planets["Saturn"]["lon"])
        if sat_h in target:
            cancel += 30
            rules.append("Saturn balancing placement in manglik houses.")
        if not rules:
            rules.append("Age-based reduction after maturity period.")
            cancel += 10
        present = max(0, score - cancel) >= 30
        return {
            "success": True,
            "is_present": present,
            "score": score,
            "anshik": 30 <= score < 70,
            "cancellation_score": min(100, cancel),
            "cancellation_rules": rules,
            "details": {"mars_from_lagna": mars_l, "mars_from_moon": mars_m, "mars_from_venus": mars_v},
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dosh/kaalsarp")
def api_dosh_kaalsarp(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        planets = calc_planets(jd)
        r = planets["Rahu"]["lon"]
        vals = [norm360(planets[p]["lon"] - r) for p in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]]
        present = all(0 <= v <= 180 for v in vals) or all(180 <= v <= 360 for v in vals)
        return {"success": True, "is_present": present, "description": "All planets lie within Rahu-Ketu axis." if present else "Planets are outside strict axis lock."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dosh/pitra")
def api_dosh_pitra(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        planets = calc_planets(jd)
        asc = calc_lagna(jd, req.latitude, req.longitude)
        aff = []
        score = 0
        for p in ["Rahu", "Saturn", "Sun"]:
            if whole_sign_house(asc, planets[p]["lon"]) == 9:
                aff.append(p)
                score += 35
        return {"success": True, "is_present": score >= 35, "score": score, "afflicting_planets": aff}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/yog")
def api_yog(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        planets = calc_planets(jd)
        asc = calc_lagna(jd, req.latitude, req.longitude)
        h = {p: whole_sign_house(asc, planets[p]["lon"]) for p in planets}
        s = {p: int(planets[p]["lon"] // 30) for p in planets}
        yogs = []
        gk = whole_sign_house(planets["Moon"]["lon"], planets["Jupiter"]["lon"]) in [1, 4, 7, 10]
        yogs.append({"name": "Gaja Kesari Yog", "present": gk, "strength": "High" if gk else "None", "description": "Jupiter in kendra from Moon."})
        ba = h["Sun"] == h["Mercury"]
        yogs.append({"name": "Budh-Aditya Yog", "present": ba, "strength": "High" if ba else "None", "description": "Sun-Mercury conjunction."})
        cm = h["Moon"] == h["Mars"]
        yogs.append({"name": "Chandra-Mangal Yog", "present": cm, "strength": "Medium" if cm else "None", "description": "Moon-Mars conjunction."})
        # Raja yoga simplified
        trine = [1, 5, 9]
        kendra = [1, 4, 7, 10]
        ry = any(h[p] in kendra for p in ["Jupiter", "Venus", "Mercury"]) and any(h[p] in trine for p in ["Sun", "Moon", "Mars"])
        yogs.append({"name": "Raja Yog", "present": ry, "strength": "High" if ry else "None", "description": "Trine-kendra linkage active."})
        pm = [
            ("Ruchaka", "Mars", [0, 7, 9]),
            ("Bhadra", "Mercury", [2, 5]),
            ("Hamsa", "Jupiter", [8, 11, 3]),
            ("Malavya", "Venus", [1, 6, 11]),
            ("Shasha", "Saturn", [9, 10, 6]),
        ]
        for nm, p, good in pm:
            ok = h[p] in kendra and s[p] in good
            yogs.append({"name": f"{nm} Mahapurush Yog", "present": ok, "strength": "Premium" if ok else "None", "description": f"{p} in own/exaltation sign and kendra."})
        return {"success": True, "yogas": yogs}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dasha/current")
def api_dasha_current(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        moon = calc_planets(jd)["Moon"]["lon"]
        tree = dasha_tree(moon, req.date)
        md, ad, pd, sd, pr, _ = pick_current_levels(tree)
        return {
            "success": True,
            "current_levels": [
                {"level": "Mahadasha", "planet": md["planet"], "start_date": fmt_dt(md["start"]), "end_date": fmt_dt(md["end"])},
                {"level": "Antardasha", "planet": ad["planet"], "start_date": fmt_dt(ad["start"]), "end_date": fmt_dt(ad["end"])},
                {"level": "Pratyantardasha", "planet": pd["planet"], "start_date": fmt_dt(pd["start"]), "end_date": fmt_dt(pd["end"])},
                {"level": "Sookshmadasha", "planet": sd["planet"], "start_date": fmt_dt(sd["start"]), "end_date": fmt_dt(sd["end"])},
                {"level": "Pranadasha", "planet": pr["planet"], "start_date": fmt_dt(pr["start"], True), "end_date": fmt_dt(pr["end"], True)},
            ],
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dasha/prana")
def api_dasha_prana(req: KundliReq):
    try:
        jd = to_jd(req.date, req.time, 5.5)
        moon = calc_planets(jd)["Moon"]["lon"]
        tree = dasha_tree(moon, req.date)
        _, _, _, _, _, pr = pick_current_levels(tree)
        return {
            "success": True,
            "prana_dasha_deep": [
                {"index": i + 1, "planet": x["planet"], "start_date": fmt_dt(x["start"], True), "end_date": fmt_dt(x["end"], True)}
                for i, x in enumerate(pr)
            ],
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/api/dasha/yogini")
def api_dasha_yogini(req: KundliReq):
    seq = [
        ("Mangala", "Moon", 1),
        ("Pingala", "Mars", 2),
        ("Dhanya", "Sun", 3),
        ("Bhramari", "Jupiter", 4),
        ("Bhadrika", "Mercury", 5),
        ("Ulka", "Saturn", 6),
        ("Siddha", "Venus", 7),
        ("Sankata", "Rahu", 8),
    ]
    try:
        cur = datetime.strptime(req.date, "%Y-%m-%d")
        out = []
        for _ in range(3):
            for n, l, y in seq:
                en = cur + timedelta(days=int(y * 365.25))
                out.append({"name": n, "lord": l, "years": y, "start_date": fmt_dt(cur), "end_date": fmt_dt(en)})
                cur = en
        return {"success": True, "yogini_dasha": out}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/")
def root():
    try:
        return FileResponse("index.html")
    except Exception:
        return {"message": "Astromata API running. Place index.html beside app.py"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
