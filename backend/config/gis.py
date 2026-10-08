"""GeoDjango library discovery for Windows development machines.

On Linux (CI, VPS image) GDAL/GEOS/PROJ come from system packages and nothing here runs.
On Windows there is no system GDAL, so we reuse the libraries shipped with the local
PostgreSQL + PostGIS bundle. Override with GIS_BIN_DIR / GIS_PROJ_DIR when needed.
"""

import ctypes
import glob
import os
import sys
from pathlib import Path


def _find_bin_dir() -> Path | None:
    explicit = os.environ.get("GIS_BIN_DIR")
    candidates = (
        [explicit]
        if explicit
        else sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin"), reverse=True)
    )
    for candidate in candidates:
        if candidate and glob.glob(os.path.join(candidate, "libgdal-*.dll")):
            return Path(candidate)
    return None


def _find_proj_dir(bin_dir: Path) -> Path | None:
    explicit = os.environ.get("GIS_PROJ_DIR")
    candidates = (
        [explicit]
        if explicit
        else sorted(
            glob.glob(str(bin_dir.parent / "share" / "contrib" / "postgis-*" / "proj")),
            reverse=True,
        )
    )
    for candidate in candidates:
        if candidate and (Path(candidate) / "proj.db").exists():
            return Path(candidate)
    return None


def gis_library_settings() -> dict[str, str]:
    """Return GDAL_LIBRARY_PATH / GEOS_LIBRARY_PATH for Windows, or {} elsewhere."""
    if sys.platform != "win32":
        return {}
    bin_dir = _find_bin_dir()
    if bin_dir is None:
        return {}
    gdal_path = sorted(glob.glob(os.path.join(bin_dir, "libgdal-*.dll")))[-1]
    geos_path = os.path.join(bin_dir, "libgeos_c.dll")

    os.add_dll_directory(str(bin_dir))
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    # The bundled GDAL uses a different C runtime and does not see environment variables
    # set after process start, so PROJ's data dir must be given through GDAL's own API.
    proj_dir = _find_proj_dir(bin_dir)
    if proj_dir is not None:
        gdal = ctypes.CDLL(gdal_path)
        paths = (ctypes.c_char_p * 2)(str(proj_dir).encode(), None)
        gdal.OSRSetPROJSearchPaths.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        gdal.OSRSetPROJSearchPaths(paths)

    return {"GDAL_LIBRARY_PATH": gdal_path, "GEOS_LIBRARY_PATH": geos_path}
