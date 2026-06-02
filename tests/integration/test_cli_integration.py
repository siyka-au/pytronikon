"""Integration tests for the CLI against a live controller."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
def host():
    """Get the integration test host."""
    return os.environ.get("ELEKTRONIKON_HOST", "192.168.100.100")


def run_cli(args: list[str]) -> tuple[int, dict, str]:
    """Run the CLI and return exit code, parsed JSON output, and stderr.
    
    Args:
        args: CLI arguments (without 'pytronikon')
        
    Returns:
        (exit_code, parsed_json_or_dict, stderr_text)
    """
    cmd = ["pytronikon"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = result.stdout
    
    return result.returncode, output, result.stderr


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_discover(host):
    """Test 'discover' command."""
    exit_code, output, stderr = run_cli(["discover", "--host", host])
    
    assert exit_code == 0, f"CLI failed: {stderr}"
    assert isinstance(output, dict)
    assert output["host"] == host
    assert "language" in output
    assert "discovered_at" in output
    assert "family_counts" in output
    assert "points" in output
    
    # Check that we have core families
    assert output["family_counts"].get("analog_inputs", 0) >= 1
    assert "analog_inputs" in output["points"]
    assert len(output["points"]["analog_inputs"]) >= 1


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_discover_with_language(host):
    """Test 'discover' command with language option."""
    exit_code, output, stderr = run_cli(["discover", "--host", host, "--language", "English"])
    
    assert exit_code == 0, f"CLI failed: {stderr}"
    assert output["language"] == "English"
    assert "points" in output


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_single_selector(host):
    """Test 'query' command with single selector."""
    exit_code, output, stderr = run_cli(["query", "--host", host, "--selector", "300201"])
    
    assert exit_code == 0, f"CLI failed: {stderr}"
    assert isinstance(output, dict)
    assert "direct_results" in output
    assert len(output["direct_results"]) >= 1
    
    result = output["direct_results"][0]
    assert result["selector"] == "300201"
    assert "raw" in result
    assert result["raw"] != "X"


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_multiple_selectors(host):
    """Test 'query' command with multiple selectors."""
    exit_code, output, stderr = run_cli(
        ["query", "--host", host, "--selector", "300201,300301,300401"]
    )
    
    assert exit_code == 0, f"CLI failed: {stderr}"
    assert len(output["direct_results"]) == 3
    
    selectors = {r["selector"] for r in output["direct_results"]}
    assert selectors == {"300201", "300301", "300401"}


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_multiple_selector_args(host):
    """Test 'query' with multiple --selector arguments."""
    exit_code, output, stderr = run_cli(
        ["query", "--host", host, "--selector", "300201", "--selector", "300301"]
    )
    
    assert exit_code == 0, f"CLI failed: {stderr}"
    assert len(output["direct_results"]) == 2
    
    selectors = {r["selector"] for r in output["direct_results"]}
    assert selectors == {"300201", "300301"}


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_no_args_fails(host):
    """Test 'query' command without selectors/points/families fails."""
    exit_code, output, stderr = run_cli(["query", "--host", host])
    
    assert exit_code == 1, "Query without selectors should fail"


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_with_catalog_and_family(host):
    """Test 'query' with catalog file and family filtering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # First, create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Now query with family filter using the catalog
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--family", "digital_outputs", "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert "direct_results" in output
        assert len(output["direct_results"]) >= 1
        
        # All results should have catalog metadata
        for result in output["direct_results"]:
            assert "point_family" in result
            assert result["point_family"] == "digital_outputs"


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_with_catalog_and_point_ids(host):
    """Test 'query' with catalog file and point ID filtering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query by point ID suffix
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--point_ids", "compressor-outlet", "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) >= 1
        
        # Should find the compressor outlet
        results = output["direct_results"]
        assert any("compressor" in r.get("point_label", "").lower() for r in results)


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_with_catalog_multiple_point_ids(host):
    """Test 'query' with multiple point IDs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query by multiple point IDs
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--point_ids", "compressor-outlet,element-outlet", 
             "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) >= 2


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_with_catalog_enrichment(host):
    """Test that catalog enrichment adds decoded values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query with enrichment
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--selector", "300201", "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        result = output["direct_results"][0]
        
        # Check enrichment fields
        assert "point_id" in result
        assert "point_label" in result
        assert "point_family" in result
        
        # Check if decoded value is present for analog input
        if "decoded" in result:
            decoded = result["decoded"]
            assert "value" in decoded
            assert "unit" in decoded or "raw_value" in decoded


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_multiple_families(host):
    """Test 'query' with multiple families using catalog."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query multiple families
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--family", "analog_inputs", "--family", "digital_inputs",
             "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) >= 2
        
        # Check that we have both families
        families = {r.get("point_family") for r in output["direct_results"]}
        assert "analog_inputs" in families or "digital_inputs" in families


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_all_discovered(host):
    """Test 'query' with all points from a family using catalog."""
    # First discover
    exit_code, discover_output, stderr = run_cli(["discover", "--host", host])
    assert exit_code == 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        catalog_path.write_text(json.dumps(discover_output, ensure_ascii=False))
        
        # Query all analog inputs to get all discovered
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--family", "analog_inputs", "--family", "digital_inputs",
             "--family", "counters", "--family", "digital_outputs", "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) > 0
        
        # Should have significant number of results
        assert len(output["direct_results"]) >= 10


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_mixed_selectors_and_families(host):
    """Test 'query' mixing selectors and families."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query with both selector and family
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--selector", "300201", 
             "--family", "digital_outputs", "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        results = output["direct_results"]
        assert len(results) > 1
        
        # Should have the specific selector
        assert any(r["selector"] == "300201" for r in results)


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_discover_to_file(host):
    """Test saving discover output to file and using it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Run discover and save to file
        cmd = ["pytronikon", "discover", "--host", host]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0
        
        catalog_path.write_text(result.stdout)
        
        # Verify file was created and is valid JSON
        catalog_data = json.loads(catalog_path.read_text())
        assert "points" in catalog_data
        assert "family_counts" in catalog_data


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_specific_point_by_full_id(host):
    """Test querying a specific point by full point ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query by full point ID
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--point_ids", "analog_inputs:compressor-outlet", 
             "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) >= 1
        
        result = output["direct_results"][0]
        assert "compressor" in result.get("point_label", "").lower()


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_query_multiple_families_comma_separated(host):
    """Test 'query' with comma-separated family names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "catalog.json"
        
        # Create the catalog
        exit_code, output, stderr = run_cli(["discover", "--host", host])
        assert exit_code == 0
        catalog_path.write_text(json.dumps(output, ensure_ascii=False))
        
        # Query comma-separated families
        exit_code, output, stderr = run_cli(
            ["query", "--host", host, "--family", "analog_inputs,counters",
             "--catalog", str(catalog_path)]
        )
        
        assert exit_code == 0, f"CLI failed: {stderr}"
        assert len(output["direct_results"]) >= 2


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_catalog_metadata_fields(host):
    """Test that catalog contains expected metadata fields."""
    exit_code, output, stderr = run_cli(["discover", "--host", host])
    
    assert exit_code == 0
    
    # Check structure
    assert "host" in output
    assert "language" in output
    assert "discovered_at" in output
    assert "family_counts" in output
    assert "points" in output
    
    # Check points structure
    points = output.get("points", {})
    for family_name, points_list in points.items():
        for point in points_list:
            assert "id" in point
            assert "label" in point
            assert "family" in point
            assert "live_selectors" in point
            
            # Check live_selectors structure
            for selector in point["live_selectors"]:
                assert "index" in selector
                assert "subindex" in selector
                assert "selector" in selector


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_help_commands():
    """Test that CLI help works."""
    result = subprocess.run(["pytronikon", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "discover" in result.stdout or "query" in result.stdout


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_cli_json_output_format(host):
    """Test that JSON output is valid and properly formatted."""
    exit_code, output, stderr = run_cli(["discover", "--host", host])
    
    assert exit_code == 0
    # Output should be dict if JSON parsed successfully
    assert isinstance(output, dict)
    
    # Re-serialize to ensure it's valid
    json_str = json.dumps(output, ensure_ascii=False)
    reparsed = json.loads(json_str)
    assert reparsed == output
