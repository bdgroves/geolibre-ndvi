"""Recompute the NDVI composite and rewrite the GeoLibre project.

Driven by .github/workflows/refresh-ndvi.yml, but runs fine by hand:

    pixi run refresh
    BBOX=-121.2,38.6,-120.4,39.2 WINDOW_DAYS=90 pixi run refresh

Writes data/ndvi_latest.tif and projects/ndvi-latest.geolibre.json.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geolibre_ndvi.ndvi import (  # noqa: E402
    compute_ndvi,
    load_bands,
    median_composite,
    search_scenes,
    write_cog,
)

ROOT = Path(__file__).resolve().parents[1]
COG_PATH = ROOT / "data" / "ndvi_latest.tif"
PROJECT_PATH = ROOT / "projects" / "ndvi-latest.geolibre.json"

# Point this at wherever the COG is actually served from. A local path will
# not survive a project reopen -- GeoLibre's localhost server is session-scoped.
COG_URL = os.environ.get(
    "COG_URL",
    "https://raw.githubusercontent.com/bdgroves/geolibre-ndvi/main/data/ndvi_latest.tif",
)


def main() -> int:
    bbox = [float(v) for v in os.environ.get(
        "BBOX", "-121.2,38.6,-120.4,39.2").split(",")]
    window = int(os.environ.get("WINDOW_DAYS", "60"))

    end = date.today()
    start = end - timedelta(days=window)
    datetime_range = f"{start.isoformat()}/{end.isoformat()}"

    print(f"bbox={bbox} window={datetime_range}")

    items = search_scenes(bbox, datetime_range, max_cloud=20.0)
    print(f"{len(items)} scenes under 20% cloud")
    if not items:
        print("No scenes matched -- leaving previous output in place.")
        return 0

    ds = load_bands(items, bbox)
    ndvi = median_composite(compute_ndvi(ds))
    write_cog(ndvi, COG_PATH)
    print(f"wrote {COG_PATH} ({COG_PATH.stat().st_size / 1e6:.1f} MB)")

    _write_project(bbox, datetime_range)
    print(f"wrote {PROJECT_PATH}")
    return 0


def _write_project(bbox, datetime_range) -> None:
    """Build the project headlessly.

    Map() spins up the bundled localhost server and expects a browser to
    talk to, which is wrong for CI. The builders underneath are the same
    ones the MCP server uses, so this stays interchangeable with anything
    the widget or the desktop app produces.
    """
    import json

    west, south, east, north = bbox
    project = {
        "version": 1,
        "name": f"NDVI {datetime_range}",
        "mapView": {
            "center": [(west + east) / 2, (south + north) / 2],
            "zoom": 9,
        },
        "basemap": "dark",
        "layers": [
            {
                "id": "ndvi",
                "name": f"NDVI median ({datetime_range})",
                "type": "raster",
                "source": {"type": "cog", "url": COG_URL},
                "style": {"colormap": "rdylgn", "rescale": [[-0.2, 0.9]]},
                "visible": True,
                "opacity": 1.0,
            }
        ],
    }
    PROJECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_PATH.write_text(json.dumps(project, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
