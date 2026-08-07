"""Guard the uint16 trap and the composite behaviour."""

import numpy as np
import pytest
import xarray as xr

from geolibre_ndvi.ndvi import compute_ndvi, median_composite


def _stack(red_vals, nir_vals):
    red = np.array(red_vals, dtype="uint16")
    nir = np.array(nir_vals, dtype="uint16")
    return xr.Dataset(
        {"B04": (("time", "y", "x"), red), "B08": (("time", "y", "x"), nir)},
        coords={"time": np.arange(red.shape[0])},
    )


def test_negative_ndvi_stays_negative():
    """Water: red > nir. The uint16 path wraps to +15.9; we must get -0.5."""
    ds = _stack([[[3000]]], [[[1000]]])
    ndvi = compute_ndvi(ds)
    assert ndvi.values[0, 0, 0] == pytest.approx(-0.5, abs=1e-4)


def test_output_is_float32():
    ds = _stack([[[600]]], [[[3400]]])
    assert compute_ndvi(ds).dtype == np.float32


def test_ndvi_stays_in_physical_range():
    rng = np.random.default_rng(0)
    red = rng.integers(200, 4000, (4, 20, 20))
    nir = rng.integers(200, 4000, (4, 20, 20))
    ndvi = compute_ndvi(_stack(red, nir))
    assert float(ndvi.min()) >= -1.0
    assert float(ndvi.max()) <= 1.0


def test_zero_pixels_become_nan_not_inf():
    """0/0 must land as NaN so nodata masking works, never as inf."""
    ds = _stack([[[0]]], [[[0]]])
    ndvi = compute_ndvi(ds)
    assert np.isnan(ndvi.values[0, 0, 0])
    assert not np.isinf(ndvi.values).any()


def test_median_ignores_nan_slices():
    ds = _stack([[[600]], [[0]], [[600]]], [[[3400]], [[0]], [[3400]]])
    med = median_composite(compute_ndvi(ds))
    assert med.values[0, 0] == pytest.approx(0.7, abs=1e-3)


# --- project schema -----------------------------------------------------
# Transcribed from a real GeoLibre 2.5.0 save_project() output. These pin
# the three things that are easy to get wrong and fail silently.

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture
def project(tmp_path, monkeypatch):
    import refresh_ndvi

    monkeypatch.setattr(refresh_ndvi, "PROJECT_PATH", tmp_path / "p.geolibre.json")
    refresh_ndvi._write_project([-121.2, 38.6, -120.4, 39.2], "2026-06-01/2026-08-01")
    return json.loads((tmp_path / "p.geolibre.json").read_text())


def test_colormap_lives_in_rasterstate_not_style(project):
    """Put these in `style` and the app silently renders grey."""
    layer = project["layers"][0]
    assert layer["metadata"]["rasterState"]["colormap"] == "rdylgn"
    assert layer["metadata"]["rasterState"]["rescale"] == [[-0.2, 0.9]]
    assert "colormap" not in layer["style"]
    assert "rescale" not in layer["style"]


def test_layer_type_and_source_type_differ(project):
    layer = project["layers"][0]
    assert layer["type"] == "cog"
    assert layer["source"]["type"] == "raster"


def test_native_layer_id_echoes_layer_id(project):
    layer = project["layers"][0]
    assert layer["metadata"]["nativeLayerIds"] == [layer["id"]]


def test_version_is_a_string(project):
    assert project["version"] == "0.1.0"


def test_cog_url_is_not_localhost(project):
    """Localhost URLs are session-scoped and die on reopen."""
    layer = project["layers"][0]
    for url in (layer["source"]["url"], layer["sourcePath"]):
        assert "127.0.0.1" not in url and "localhost" not in url
