import os
import sys
import shutil
import ctypes
import flet as ft

def resolve_native_dir() -> str:
    """
    Find the 'native' folder no matter where serious_python extracts
    the app on-device. Falls back through a few candidate locations.
    """
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

    # This is the override hook swisseph-ffi exposes
    os.environ["SWISSEPH_LIBRARY_PATH"] = so_path

    from swisseph_ffi import SwissEph, SE_GREG_CAL, SEFLG_SPEED, SEFLG_SIDEREAL, SE_SUN
    from swisseph_ffi import c_double, c_char_p, create_string_buffer

    swe = SwissEph()
    swe.swe_set_ephe_path(ephe_path.encode("utf-8"))
    return swe

def compute_sun_longitude(swe, year, month, day, hour_ut):
    from swisseph_ffi import SE_GREG_CAL, SEFLG_SPEED, SEFLG_SIDEREAL, SE_SUN
    from swisseph_ffi import c_double, create_string_buffer

    jd = swe.swe_julday(year, month, day, hour_ut, SE_GREG_CAL)
    xx = (c_double * 6)()
    serr = create_string_buffer(256)
    ret = swe.swe_calc_ut(jd, SE_SUN, SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr)
    if ret < 0:
        raise RuntimeError(f"swe_calc_ut failed: {serr.value}")
    return xx[0]  # sidereal longitude in degrees

def main(page: ft.Page):
    page.title = "Bhoovalaya Oracle - Swiss Ephemeris Test"

    status = ft.Text("Tap to test native Swiss Ephemeris load")
    result = ft.Text("")

    def on_test(e):
        try:
            swe = setup_swisseph()
            lon = compute_sun_longitude(swe, 2024, 1, 1, 12.0)
            status.value = "libswe.so loaded OK ✅"
            result.value = f"Sun sidereal longitude: {lon:.4f}°"
        except Exception as ex:
            status.value = "FAILED ❌"
            result.value = str(ex)
        page.update()

    page.add(
        ft.ElevatedButton("Test Swiss Ephemeris", on_click=on_test),
        status,
        result,
    )

ft.app(target=main)
