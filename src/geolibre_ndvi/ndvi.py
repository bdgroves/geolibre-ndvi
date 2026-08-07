"""Sentinel-2 NDVI helpers.

Deliberately importable and side-effect free so the notebooks and the
GitHub Actions workflow run the *same* code path. Anything a notebook
proves out should end up here rather than being retyped into a script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
import rioxarray  # noqa: F401 -- registers the .rio accessor

__all__ = [
    "search_scenes",
    "load_bands",
    "compute_ndvi",
    "median_composite",
    "write_cog",
]

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
RED, NIR = "B04", "B08"


def search_scenes(bbox, datetime, max_cloud=10.0):
    """Return STAC items for a bbox/date range under a cloud threshold.

    bbox: [west, south, east, north] in EPSG:4326
    datetime: STAC datetime string, e.g. "2025-05-01/2025-06-30"
    """
    import planetary_computer
    import pystac_client

    catalog = pystac_client.Client.open(
        STAC_URL, modifier=planetary_computer.sign_inplace
    )
    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=datetime,
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    return list(search.items())


def load_bands(items, bbox, resolution=20, crs="EPSG:3857"):
    """Lazily load red + NIR into an xarray Dataset.

    Defaults to EPSG:3857 so GeoLibre can serve the resulting COG without
    reprojecting on the fly. 20 m instead of the native 10 m is a
    deliberate speed/detail trade -- bump it for final renders.
    """
    from odc.stac import stac_load

    return stac_load(
        items,
        bands=[RED, NIR],
        bbox=bbox,
        resolution=resolution,
        crs=crs,
        chunks={},
        groupby="solar_day",
    )


def compute_ndvi(ds: xr.Dataset) -> xr.DataArray:
    """(NIR - Red) / (NIR + Red), cast to float and de-infinited.

    The float32 cast is not optional, and not for the reason you might
    expect. Division isn't the problem -- numpy/xarray promote to float
    on true division anyway. The problem is the *subtraction*: the raw
    bands are unsigned uint16, so wherever red > nir (water, cloud
    shadow, burn scars, deep shade) `nir - red` wraps around instead of
    going negative.

        uint16: (1000 - 3000) / (1000 + 3000)  ->  +15.884
        float32: (1000 - 3000) / (1000 + 3000) ->   -0.5

    It fails silently, only on the pixels you most want to trust, and
    it produces plausible-looking rasters if your colour ramp clamps at
    1.0. Cast first, always.
    """
    red = ds[RED].astype("float32")
    nir = ds[NIR].astype("float32")

    ndvi = (nir - red) / (nir + red)
    ndvi = ndvi.where(np.isfinite(ndvi))
    ndvi.name = "NDVI"
    return ndvi


def median_composite(ndvi: xr.DataArray, crs="EPSG:3857") -> xr.DataArray:
    """Median across time -- a cheap and surprisingly effective cloud filter."""
    out = ndvi.median(dim="time", skipna=True)
    if hasattr(out, "compute"):
        out = out.compute()
    out.rio.write_crs(crs, inplace=True)
    out.rio.write_nodata(np.nan, inplace=True)
    out.name = "NDVI"
    return out


def write_cog(da: xr.DataArray, path: str | Path) -> Path:
    """Write a tiled, overviewed COG that GeoLibre can range-request."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    da.rio.to_raster(
        path,
        driver="COG",
        compress="DEFLATE",
        blocksize=512,
        overview_resampling="average",
        dtype="float32",
    )
    return path
