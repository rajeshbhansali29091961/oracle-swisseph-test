import os
import datetime
import flet as ft

# ---------------------------------------------------------
# Location: Mumbai, India
# ---------------------------------------------------------
MUMBAI_LAT = 19.0760
MUMBAI_LON = 72.8777
TZ_OFFSET_HOURS = 5.5  # IST, no DST

RASHI_NAMES = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"
]


def resolve_native_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "native"),
        os.path.join(here, "..", "native"),
        os.path.join(os.getcwd(), "native"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    raise RuntimeError(f"native/ folder not found. Checked: {candidates}")


def setup_swisseph():
    native_dir = resolve_native_dir()
    so_path = os.path.join(native_dir, "arm64-v8a", "libswe.so")
    ephe_path = os.path.join(native_dir, "ephe")

    if not os.path.exists(so_path):
        raise RuntimeError(f"libswe.so not found at {so_path}")

    os.environ["SWISSEPH_LIBRARY_PATH"] = so_path

    from swisseph_ffi import SwissEph
    swe = SwissEph()
    swe.swe_set_ephe_path(ephe_path.encode("utf-8"))
    return swe


def rashi_from_longitude(lon: float) -> int:
    return int(lon // 30)


def navamsha_from_longitude(lon: float) -> int:
    sign = rashi_from_longitude(lon)
    pos_in_sign = lon % 30.0
    pada = int(pos_in_sign // (30.0 / 9))
    group = sign % 4
    group_start = {0: 0, 1: 9, 2: 6, 3: 3}[group]  # Mesha, Makara, Tula, Karka
    return (group_start + pada) % 12


def compute_chart(swe, dt_local: datetime.datetime, tz_offset: float, lat: float, lon_geo: float):
    """
    dt_local: naive datetime representing local (IST) date/time.
    Returns dict of planet name -> {longitude, d1_sign, d9_sign}, plus ascendant info.
    """
    from swisseph_ffi import (
        c_double, c_char_p, create_string_buffer,
        SE_GREG_CAL, SEFLG_SWIEPH, SEFLG_SPEED, SEFLG_SIDEREAL,
        SE_SUN, SE_MOON, SE_MARS, SE_MERCURY, SE_JUPITER, SE_VENUS,
        SE_SATURN, SE_MEAN_NODE,
    )

    # 1. Set ayanamsa to Lahiri (Chitrapaksha) BEFORE any sidereal calc
    #    SE_SIDM_LAHIRI = 1 in the Swiss Ephemeris C header; if
    #    swisseph_ffi exports the named constant, prefer that instead.
    try:
        from swisseph_ffi import SE_SIDM_LAHIRI
        sidm_lahiri = SE_SIDM_LAHIRI
    except ImportError:
        sidm_lahiri = 1  # fallback: raw value from swephexp.h

    swe.swe_set_sid_mode(sidm_lahiri, 0, 0)

    # 2. Convert local (IST) time to UT
    ut_dt = dt_local - datetime.timedelta(hours=tz_offset)
    ut_hour = ut_dt.hour + ut_dt.minute / 60.0 + ut_dt.second / 3600.0
    jd_ut = swe.swe_julday(ut_dt.year, ut_dt.month, ut_dt.day, ut_hour, SE_GREG_CAL)

    # 3. Planetary longitudes (sidereal)
    planets = {
        "Sun": SE_SUN,
        "Moon": SE_MOON,
        "Mars": SE_MARS,
        "Mercury": SE_MERCURY,
        "Jupiter": SE_JUPITER,
        "Venus": SE_VENUS,
        "Saturn": SE_SATURN,
        "Rahu": SE_MEAN_NODE,
    }

    result = {}
    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL

    for name, pid in planets.items():
        xx = (c_double * 6)()
        serr = create_string_buffer(256)
        ret = swe.swe_calc_ut(jd_ut, pid, flags, xx, serr)
        if ret < 0:
            result[name] = {"error": serr.value.decode(errors="ignore")}
            continue
        lon = xx[0] % 360.0
        result[name] = {
            "longitude": round(lon, 4),
            "d1_sign": RASHI_NAMES[rashi_from_longitude(lon)],
            "d9_sign": RASHI_NAMES[navamsha_from_longitude(lon)],
        }

    # Ketu = Rahu + 180
    if "Rahu" in result and "longitude" in result["Rahu"]:
        ketu_lon = (result["Rahu"]["longitude"] + 180.0) % 360.0
        result["Ketu"] = {
            "longitude": round(ketu_lon, 4),
            "d1_sign": RASHI_NAMES[rashi_from_longitude(ketu_lon)],
            "d9_sign": RASHI_NAMES[navamsha_from_longitude(ketu_lon)],
        }

    # 4. Ascendant / houses (needs location) - Lahiri sidereal houses
    #    House system 'P' = Placidus; swap for 'W' (Whole Sign) if that's
    #    your engine's convention for Vedic charts.
    cusps = (c_double * 13)()
    ascmc = (c_double * 10)()
    swe.swe_houses_ex(jd_ut, SEFLG_SIDEREAL, lat, lon_geo, ord('W'), cusps, ascmc)
    asc_lon = ascmc[0] % 360.0

    result["Ascendant"] = {
        "longitude": round(asc_lon, 4),
        "d1_sign": RASHI_NAMES[rashi_from_longitude(asc_lon)],
        "d9_sign": RASHI_NAMES[navamsha_from_longitude(asc_lon)],
    }

    return result, jd_ut


def main(page: ft.Page):
    page.title = "Bhoovalaya Oracle - Live Chart (Mumbai)"
    page.scroll = ft.ScrollMode.AUTO

    status = ft.Text("Tap to compute current planetary positions")
    info = ft.Text("")
    result_column = ft.Column()

    def on_compute(e):
        result_column.controls.clear()
        try:
            swe = setup_swisseph()
            now_ist = datetime.datetime.now()  # assumes device clock is IST
            chart, jd_ut = compute_chart(
                swe, now_ist, TZ_OFFSET_HOURS, MUMBAI_LAT, MUMBAI_LON
            )

            status.value = "Computed OK ✅"
            info.value = (
                f"Local time (IST): {now_ist.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Location: Mumbai ({MUMBAI_LAT}, {MUMBAI_LON})\n"
                f"Julian Day (UT): {jd_ut:.5f}"
            )

            for planet, data in chart.items():
                if "error" in data:
                    result_column.controls.append(
                        ft.Text(f"{planet}: ERROR - {data['error']}", color=ft.Colors.RED)
                    )
                    continue
                result_column.controls.append(
                    ft.Row([
                        ft.Text(planet, width=100, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{data['longitude']:.2f}°", width=90),
                        ft.Text(f"D1: {data['d1_sign']}", width=140),
                        ft.Text(f"D9: {data['d9_sign']}", width=140),
                    ])
                )
        except Exception as ex:
            status.value = "FAILED ❌"
            info.value = str(ex)

        page.update()

    page.add(
        ft.ElevatedButton("Compute Current Chart", on_click=on_compute),
        status,
        info,
        ft.Divider(),
        result_column,
    )


ft.app(target=main)
