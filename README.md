# geolibre-ndvi

Getting to know [GeoLibre](https://geolibre.app/) — Qiusheng Wu's cloud-native
GIS platform — with a working Sentinel-2 NDVI pipeline as the vehicle.

## What GeoLibre actually is

A lightweight GIS built on Tauri v2, React, MapLibre GL JS, DuckDB-WASM Spatial,
and deck.gl. One codebase runs as a desktop app, an Android app, in the browser
at [web.geolibre.app](https://web.geolibre.app/), and — via the `geolibre`
Python package — embedded in a Jupyter cell as an anywidget with a leafmap-style
API. Project state syncs both ways through a single `.geolibre.json` file.

## What it is not

**It is not an xarray replacement.** The app's Add Data menu reads
Cloud-Optimized NetCDF/HDF and Zarr, but the Python API has no `add_netcdf` or
`add_zarr` — those are UI-only. Checked against the installed package, not
assumed.

So the architecture here treats GeoLibre as the display and publication layer,
with xarray doing the raster work:

```
STAC search → odc-stac → xarray → NDVI → COG → GeoLibre → .geolibre.json / HTML
```

## Setup

```bash
pixi install
pixi run lab
```

Then work through `notebooks/` in order.

| Notebook | What it covers |
| --- | --- |
| `01_geolibre_basics.ipynb` | Map creation, two-way sync, layer handles, `list_algorithms()`, project export |
| `02_ndvi_sentinel2.ipynb` | Planetary Computer STAC → NDVI composite → COG → styled GeoLibre layer |

Shared logic lives in `src/geolibre_ndvi/ndvi.py` so the notebooks and CI run
the same code path.

## Gotchas worth knowing before you hit them

**Local rasters are session-scoped.** `add_raster()` accepts a local path via a
bundled localhost server, but a saved project won't restore it later, and it
fails entirely where the browser can't reach the kernel's localhost (Colab,
JupyterHub, remote servers). Anything you publish needs a hosted COG URL.

**Browser vs. desktop.** Local file dialogs, local MBTiles, local raster reads,
and PostgreSQL require the installed Tauri app. The web build is URL-sources
only.

**Credentials are redacted by default** on `save_project()`, `to_project()`,
and `to_html()`. Good default — but it means a project with an authenticated
layer quietly stops working on reopen unless you passed `keep_credentials=True`.

**Cast bands to float before differencing.** Sentinel-2 bands are unsigned
uint16, so `nir - red` *wraps around* wherever red > nir — water, cloud shadow,
burn scars. An NDVI of −0.5 silently becomes +15.9. See the docstring in
`compute_ndvi()`.

## Publishing

`.geolibre.json` files are interchangeable across desktop, web, and mobile. The
web app opens a public project URL directly:

```
https://web.geolibre.app/?url=https://<host>/ndvi-foothills.geolibre.json&layout=viewer
```

`layout=viewer` is read-only but explorable. `&maponly` strips all chrome.
`&layout=compact&panels=none` is the middle ground for a narrow embed. There's
also a typed `@geolibre/embed` client and a versioned `postMessage` API for
driving the map from a host page.

## MCP server

The same package ships an MCP server that authors `.geolibre.json` projects
from an AI client — no notebook, no running app:

```bash
pixi run mcp    # geolibre-mcp --root ./projects
```

Different shape from the QGIS MCP: less "drive a live session," more "generate
a portable artifact." Probably the more interesting long-term thread for
scheduled map outputs.

## License

MIT
