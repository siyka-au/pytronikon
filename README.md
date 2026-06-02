# PyTronikon

Python client and CLI for Atlas Copco Elektronikon MkV controllers that expose `mkv.cgi`.

## Requirements

- Python 3.13+
- Network access to the controller (default host `192.168.100.100`)

**No external dependencies.** All transport and parsing use only the Python standard library.

## CLI

### Quick Queries (No Discovery Required)

Query a few raw selectors directly:

```bash
pytronikon query --selector 300201,300301,300701
```

Result:
```json
{
  "host": "192.168.100.100",
  "selector_count": 3,
  "direct_results": [
    {
      "selector": "300201",
      "index": 12290,
      "subindex": 1,
      "raw": "1AD90080"
    },
    ...
  ],
  "point_results": [],
  "catalog_summary": null
}
```

### Discovery and Catalog Files

Discover all active points on a controller and save to a file:

```bash
pytronikon discover --host 192.168.100.100 > catalog.json
```

This creates a reusable catalog with all points, families, units, and metadata:

```json
{
  "host": "192.168.100.100",
  "language": "English",
  "discovered_at": "2026-06-02T02:27:23.707288+00:00",
  "family_counts": {
    "analog_inputs": 4,
    "digital_inputs": 3,
    "digital_outputs": 6,
    "counters": 6,
    ...
  },
  "points": {
    "analog_inputs": [
      {
        "id": "analog_inputs:compressor-outlet",
        "label": "Compressor Outlet",
        "family": "analog_inputs",
        "unit": "bar",
        "input_type": 0,
        "display_precision": 1,
        "live_selectors": [{"index": 12290, "subindex": 1}],
        "index": 8208
      },
      ...
    ],
    ...
  }
}
```

### Enriched Queries with Catalog

Use a saved catalog to enrich query results with point metadata and automatically decode values:

```bash
pytronikon query --selector 300201 --catalog catalog.json --host 192.168.100.100
```

Result includes decoded values:
```json
{
  "host": "192.168.100.100",
  "selector_count": 1,
  "direct_results": [
    {
      "selector": "300201",
      "index": 12290,
      "subindex": 1,
      "raw": "1B550080",
      "point_id": "analog_inputs:compressor-outlet",
      "point_label": "Compressor Outlet",
      "point_family": "analog_inputs",
      "point_unit": "bar",
      "decoded": {
        "value": 6.997,
        "unit": "bar",
        "raw_value": 6997,
        "status": 128
      }
    }
  ],
  "catalog_source": "2026-06-02T02:27:23.707288+00:00"
}
```

### Query by Family (with Catalog)

Get all points in a specific family:

```bash
pytronikon query --family analog_inputs --catalog catalog.json --host 192.168.100.100
```

Returns all analog inputs with decoded values:
```json
{
  "selector_count": 4,
  "direct_results": [
    {
      "selector": "300201",
      "point_label": "Compressor Outlet",
      "decoded": {"value": 7.227, "unit": "bar", "raw_value": 7227, "status": 128}
    },
    {
      "selector": "300202",
      "point_label": "Element Outlet",
      "decoded": {"value": 68.1, "unit": "°C", "raw_value": 681, "status": 128}
    },
    ...
  ]
}
```

### Query by Point IDs (with Catalog)

Query specific points by ID or label:

```bash
# By point label suffix
pytronikon query --point_ids compressor-outlet,element-outlet --catalog catalog.json --host 192.168.100.100

# By full point ID
pytronikon query --point_ids "analog_inputs:compressor-outlet" --catalog catalog.json --host 192.168.100.100
```

Both formats match and return decoded data for those specific points.

### Override Target Host

All commands support `--host` and respect the `ELEKTRONIKON_HOST` environment variable:

```bash
pytronikon query --selector 300201 --host 192.168.100.100

# Or set environment variable
export ELEKTRONIKON_HOST=192.168.100.100
pytronikon query --selector 300201
```

### Legacy Discovery (via Library)

Discover the active catalog and use point queries without a catalog file:

```bash
pytronikon discover
```

Then query by point name:

```bash
pytronikon query --all
pytronikon query --point analog_inputs:compressor_outlet --family digital_outputs
```

**Note:** This requires that you've previously called `discover` to initialize the controller state. For reproducible, automatable workflows, saving the catalog to a file is recommended.

## Library Usage

### Basic Raw Queries

Query raw selectors directly (no discovery required):

```python
from pytronikon import ElektronikonClient

client = ElektronikonClient(host="192.168.100.100")

# Query by selector
result = client.query_raw(["300201", "300301"])
print(result["direct_results"])  # List of raw results
```

### Explicit Discovery

Discover all points on a controller:

```python
# Explicit discovery required for point/family queries
catalog = client.discover()

# Catalog contains all discovered points, families, and metadata
print(catalog.family_counts)  # {'analog_inputs': 4, 'counters': 6, ...}
print(catalog.points_by_id)   # Dict of point ID -> point metadata
```

### Query by Point ID or Family

After discovery, query by point name or family:

```python
# Query all discovered points
all_points = client.query(all_discovered=True)

# Query specific points
specific = client.query(points=["analog_inputs:compressor_outlet"])

# Query entire families
family = client.query(families=["digital_outputs"])

# Mix direct selectors and named points
mixed = client.query(
    selectors=["300201"],
    points=["analog_inputs:element_outlet"],
    families=["counters"],
)
```

### Working with Catalogs

Save and load catalogs for reproducible queries:

```python
import json

# Save catalog to file
catalog = client.discover()
with open("catalog.json", "w") as f:
    json.dump({
        "host": "192.168.100.100",
        "discovered_at": catalog.discovered_at,
        "family_counts": catalog.family_counts,
        "points": {
            fam: [p for p in catalog.families[fam]]
            for fam in catalog.families
        }
    }, f, indent=2)

# Later, load and use catalog data
with open("catalog.json", "r") as f:
    catalog_data = json.load(f)
    print(catalog_data["family_counts"])
```

## Tests

Run unit tests:

```bash
pytest
```

Run integration tests against the controller (optional):

```bash
ELEKTRONIKON_RUN_INTEGRATION=1 pytest tests/integration
```

Override the target host with `ELEKTRONIKON_HOST` environment variable:

```bash
ELEKTRONIKON_RUN_INTEGRATION=1 ELEKTRONIKON_HOST=192.168.100.100 pytest tests/integration
```

Run both unit and integration:

```bash
ELEKTRONIKON_RUN_INTEGRATION=1 ELEKTRONIKON_HOST=192.168.100.100 pytest
```

## Understanding Query Output

### Raw Query Results (Without Catalog)

Raw queries return hex-encoded values:

```json
{
  "direct_results": [
    {
      "selector": "300201",
      "index": 12290,
      "subindex": 1,
      "raw": "1AD90080"
    }
  ]
}
```

The `raw` field is an 8-character hex string. To interpret it, you need to know the point type and unit.

### Enriched Query Results (With Catalog)

Using a catalog automatically decodes the raw values:

```json
{
  "direct_results": [
    {
      "selector": "300201",
      "index": 12290,
      "subindex": 1,
      "raw": "1AD90080",
      "point_id": "analog_inputs:compressor-outlet",
      "point_label": "Compressor Outlet",
      "point_family": "analog_inputs",
      "point_unit": "bar",
      "decoded": {
        "value": 6.849,
        "unit": "bar",
        "raw_value": 6849,
        "status": 128
      }
    }
  ],
  "catalog_source": "2026-06-02T02:27:23.707288+00:00"
}
```

**Decoded field breakdown:**
- `value`: The interpreted measurement (6.849 bar, 63.3°C, etc.)
- `unit`: Unit of measurement (bar, °C, count, hours, kWh, %)
- `raw_value`: The raw integer value before normalization (6849 → 6.849 bar)
- `status`: Device status code from the first word of the response

### Catalog File Format

Catalog files from `discover` contain:
- **discovered_at**: ISO timestamp of when discovery ran
- **family_counts**: Number of points per family
- **points**: All discovered points organized by family, with:
  - `id`: Unique point identifier (family:label)
  - `label`: Human-readable name
  - `family`: Category (analog_inputs, counters, etc.)
  - `unit`: Measurement unit
  - `live_selectors`: HTTP request parameters to query current value
  - `index`: Memory address on the controller
  - Type-specific fields (input_type, counter_unit, etc.)

Reuse the same catalog file across multiple queries on the same controller to avoid re-discovering.

## Key Design Notes

- **Explicit Discovery**: The `discover()` method must be called explicitly before querying by point ID or family. There is no auto-discovery. This gives you full control over when and how the catalog is built.
- **No External Dependencies**: All HTTP transport uses `http.client.HTTPConnection` from the standard library. Connection reuse is attempted (useful for batched discovery requests), but the transport automatically reconnects and retries on connection loss, accounting for embedded controllers that may not fully support persistent connections.
- **Python 3.13+ only**: Uses modern Python idioms including `match` statements, PEP 604 unions, and other 3.13+ features.

## Protocol Notes

For protocol details, see [notes/elektronikon-mkv-protocol.md](notes/elektronikon-mkv-protocol.md).
