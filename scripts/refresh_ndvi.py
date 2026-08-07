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
    talk to, which is wrong for CI -- so this writes the JSON directly.

    The schema below is transcribed from a real save_project() output
    (GeoLibre 2.5.0), not inferred. Three things are easy to get wrong:

    1. `colormap` and `rescale` live in `metadata.rasterState`, NOT in
       `style`. Put them in `style` and the app silently ignores them and
       renders a grey ramp.
    2. Layer `type` is "cog" while `source.type` is "raster". They
       disagree on purpose.
    3. The `metadata` block is load-bearing -- customLayerType,
       externalDeckLayer, sourceKind, and nativeLayerIds (which echoes the
       layer's own id) wire up the render path. Omit them and the layer
       may not draw at all.

    See docs/findings.md.
    """
    import json
    import uuid

    west, south, east, north = bbox
    layer_id = str(uuid.uuid4())

    project = {
        "version": "0.1.0",
        "name": f"NDVI {datetime_range}",
        "mapView": {
            "center": [(west + east) / 2, (south + north) / 2],
            "zoom": 9.0,
            "bearing": 0,
            "pitch": 0,
        },
        "basemapStyleUrl": "https://tiles.openfreemap.org/styles/dark",
        "basemapVisible": True,
        "basemapOpacity": 1,
        "layers": [
            {
                "id": layer_id,
                "name": f"NDVI median ({datetime_range})",
                "type": "cog",
                "visible": True,
                "opacity": 1,
                "style": _RASTER_STYLE_DEFAULTS,
                "metadata": {
                    "customLayerType": "raster",
                    "externalDeckLayer": True,
                    "externalNativeLayer": True,
                    "identifiable": False,
                    "nativeLayerIds": [layer_id],
                    "panelCollapsed": True,
                    "rasterOverlayMode": "interleaved",
                    "rasterSource": "url",
                    "rasterState": {
                        "rescale": [[-0.2, 0.9]],
                        "colormap": "rdylgn",
                    },
                    "sourceIds": [],
                    "sourceKind": "maplibre-gl-raster",
                },
                "source": {"type": "raster", "url": COG_URL},
                "sourcePath": COG_URL,
            }
        ],
        "styles": {},
        "preferences": {
            "map": {
                "restrictBounds": False,
                "bounds": [-180, -85, 180, 85],
                "minZoom": 0,
                "maxZoom": 24,
                "maxPitch": 85,
                "renderWorldCopies": True,
            },
            "environmentVariables": [],
        },
        "metadata": {},
    }
    PROJECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_PATH.write_text(json.dumps(project, indent=2))


# GeoLibre writes this full property bag onto every layer regardless of type.
# Reproduced verbatim so a hand-built project round-trips through the app
# without the diff noise of missing keys.
_RASTER_STYLE_DEFAULTS = {
    "minZoom": 0,
    "maxZoom": 24,
    "fillColor": "#3b82f6",
    "strokeColor": "#1e40af",
    "strokeWidth": 2,
    "fillOpacity": 0.6,
    "circleRadius": 6,
    "textColor": "#111827",
    "textHaloColor": "#ffffff",
    "textHaloWidth": 2,
    "textSize": 16,
    "extrusionEnabled": False,
    "extrusionColor": "#3b82f6",
    "extrusionOpacity": 0.8,
    "extrusionHeightProperty": "height",
    "extrusionHeightScale": 1,
    "extrusionBase": 0,
    "extrusionAdvancedStyleEnabled": False,
    "extrusionColorExpression": "",
    "extrusionHeightExpression": "",
    "vectorStyleMode": "single",
    "vectorStyleProperty": "",
    "vectorStyleClassCount": 5,
    "vectorStyleColorRamp": "viridis",
    "vectorStyleClassificationScheme": "equal-interval",
    "vectorStyleStops": [
        {"value": 0, "color": "#dbeafe"},
        {"value": 1, "color": "#2563eb"},
    ],
    "vectorStyleExpression": "",
    "pointRenderer": "single",
    "heatmapRadius": 30,
    "heatmapIntensity": 1,
    "clusterRadius": 50,
    "clusterMaxZoom": 14,
    "rasterBrightnessMin": 0,
    "rasterBrightnessMax": 1,
    "rasterSaturation": 0,
    "rasterContrast": 0,
    "rasterHueRotate": 0,
}


if __name__ == "__main__":
    raise SystemExit(main())
