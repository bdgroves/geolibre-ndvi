# GeoLibre findings

Empirical notes from working with **GeoLibre 2.5.0** (`geolibre` Python
package, Windows 11 25H2, local JupyterLab). Everything here was observed,
not inferred from documentation. Re-verify after a version bump — several of
these are implementation details that could reasonably change.

---

## 1. The widget reaches vector processing only

`m.list_algorithms()` returns **40 algorithms, all vector**:

| Group | Count | Algorithms |
| --- | --- | --- |
| Geometry | 13 | aggregate, bounding-box, buffer, cell-sectors, centroids, convex-hull, dissolve, explode, grid, reproject, simplify, smooth, voronoi |
| Spatial Statistics | 6 | average-nearest-neighbor, emerging-hot-spot, getis-ord-gi, global-morans-i, kernel-density, local-morans-i |
| Data quality | 4 | check-topology-rules, check-validity, fix-geometries, fix-topology |
| Overlay | 4 | clip, difference, intersection, union |
| DGGS | 3 | dggs-bin, dggs-compact, dggs-grid |
| Movement & time | 3 | detect-stops, space-time-proximity, trajectory-speed |
| Select | 3 | random-extract, select-by-location, select-by-value |
| Join | 2 | attribute-join, spatial-join |
| (no group) | 2 | calculate-bounds, count-features |

**No raster algorithms.** No hillshade, slope, aspect, raster calculator,
zonal statistics, or Spectral Index. The docs describe raster tools as running
on a *rasterio sidecar with a client-side fallback*; the sidecar is a desktop
component the notebook widget does not get.

### Consequence

NDVI cannot be computed through `run_algorithm()` from a notebook. The
architecture is therefore:

```
xarray computes  →  GeoLibre displays
```

which is what `scripts/refresh_ndvi.py` does. The in-app Spectral Index
toolbox is still worth using interactively in the **desktop** app, but it is
not scriptable from here and not a candidate for CI.

### Parameter shape

`parameters` is a list of dicts: `{id, label, type, required, default, ...}`.
Values passed to `run_algorithm()` key off the inner **`id`**, not `label`:

```python
m.run_algorithm("buffer", {"layer": layer_id, "distance": 1000})
```

Not every algorithm record has a `group` key — use `.get()` when grouping.

---

## 2. Project schema (`.geolibre.json`)

Transcribed from real `save_project()` output. Three traps, all of which fail
*silently*:

### `colormap` and `rescale` are not style properties

They live at **`metadata.rasterState`**. The `style` block holds only generic
raster adjustments (`rasterBrightnessMin/Max`, `rasterSaturation`,
`rasterContrast`, `rasterHueRotate`) — no colormap, no rescale. Writing them
into `style` renders a grey ramp with no error.

```json
"metadata": {
  "rasterState": { "colormap": "rdylgn", "rescale": [[-0.2, 0.9]] }
}
```

### Layer `type` and `source.type` disagree by design

A COG layer is `"type": "cog"` with `"source": {"type": "raster", "url": ...}`.

### `metadata` is load-bearing

`customLayerType`, `externalDeckLayer`, `externalNativeLayer`, `sourceKind`
(`"maplibre-gl-raster"`), `rasterOverlayMode`, and `nativeLayerIds` (which
echoes the layer's own id) wire the render path. A layer without them may not
draw.

### Other observed details

- `version` is the **string** `"0.1.0"`, not an integer.
- Basemap is `basemapStyleUrl` (a full OpenFreeMap style URL) plus
  `basemapVisible` / `basemapOpacity` — there is no `"basemap": "dark"` key in
  the saved file, even though the `Map()` constructor accepts that shorthand.
- Layer ids are UUIDs.
- Every layer carries the full ~37-key style bag regardless of type, including
  vector properties on raster layers.
- Top-level keys: `version`, `name`, `mapView`, `basemapStyleUrl`,
  `basemapVisible`, `basemapOpacity`, `layers`, `styles`, `preferences`,
  `metadata`.

Pinned by `tests/test_ndvi.py`.

---

## 3. Raster layers are not identifiable

Saved raster layers carry `"identifiable": false` in metadata, and
`m.identify()` returns `[]` over them. **Click-to-inspect will not read NDVI
pixel values.** Don't design a workflow around probing values on the map; read
them from the xarray side instead.

(`identify()` also returned `[]` over point markers at zoom 8 — untested at
closer zoom, so that one is unresolved rather than a known limitation.)

---

## 4. Local rasters are session-scoped, visibly so

`add_raster()` with a local path produces:

```
http://127.0.0.1:52983/_geolibre_local/yNTO-BMgR0yi9KOmDXQW1w/schema_probe.tif
```

An ephemeral port plus a per-session token, written into both `source.url` and
`sourcePath`. **Reopening the project later gives a dead link.** Anything
published must carry a hosted URL. A test asserts the generated project never
contains a loopback address.

This also fails entirely where the browser cannot reach the kernel's localhost
— Colab, JupyterHub, remote servers.

---

## 5. Two-way sync works

Confirmed, not assumed: setting `m.layers[0].opacity = 0.6` from Python
appeared as `"opacity": 0.6` in the subsequent `save_project()` output.

Note that `get_center()` returning the constructor value is **not** evidence of
sync — it's identical whether sync works or not. Pan the map first, then read.

Interactive queries block the kernel until the app replies, so the map must be
displayed in an earlier cell before calling them.

---

## 6. Environment: Smart App Control

Not a GeoLibre issue, but it cost an hour. Windows 11 Smart App Control
(enforced) blocks unsigned compiled extensions — conda-forge and PyPI wheels
alike:

```
DLL load failed while importing pandas_parser:
An Application Control policy has blocked this file.
```

CodeIntegrity event 3077/3118 names the file and policy. **SAC has no
per-file or per-folder exclusion mechanism** — it is off, or scientific Python
does not run. Since the April 2026 cumulative update the toggle is reversible
(Windows Security → App & browser control → Smart App Control settings);
before that it required a Windows reinstall.

WSL2 sidesteps it entirely and is the better long-term home for the GDAL stack.

---

## Open questions

- Does the desktop app's `run_algorithm()` expose the raster/Whitebox tools
  that the widget lacks? If so, a desktop-hosted kernel changes the picture.
- Does `identify()` work on point markers at closer zoom?
- What does the `geolibre-mcp` server emit, and does it match this schema?
