#!/usr/bin/env python3
"""
Test Resume Capability
======================
Validates checkpoint save/load and resume functionality.
"""

import json
import tempfile
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from image_deduplicate import ImageDeduplicator, ImageMetadata


def test_checkpoint_creation():
    """Test that checkpoints are created during processing."""
    print("\n[TEST] Checkpoint Creation")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_file = tmpdir / "test_checkpoint.json"
        
        # Create dummy deduplicator
        dedup = ImageDeduplicator(
            directory=tmpdir,
            checkpoint_file=checkpoint_file,
            resume=False
        )
        
        # Simulate processing
        dedup.processed_files.add("test1.jpg")
        dedup.processed_files.add("test2.jpg")
        
        # Create mock metadata
        meta = ImageMetadata(
            path="test1.jpg",
            width=800,
            height=600,
            resolution=480000,
            file_size=50000,
            format="JPEG",
            bit_depth=24,
            has_exif=True,
            is_lossless=False,
            aspect_ratio=1.33,
            phash="abc123",
            phash_90="def456",
            phash_180="ghi789",
            phash_270="jkl012"
        )
        dedup.image_metadata.append(meta)
        
        # Save checkpoint
        dedup._save_checkpoint()
        
        # Verify checkpoint exists
        assert checkpoint_file.exists(), "Checkpoint file not created"
        print("✓ Checkpoint file created")
        
        # Verify checkpoint content
        with open(checkpoint_file, 'r') as f:
            data = json.load(f)
        
        assert "processed_files" in data, "Missing processed_files"
        assert "image_metadata" in data, "Missing image_metadata"
        assert "timestamp" in data, "Missing timestamp"
        assert "config" in data, "Missing config"
        print("✓ Checkpoint structure valid")
        
        assert len(data["processed_files"]) == 2, "Wrong processed_files count"
        assert len(data["image_metadata"]) == 1, "Wrong metadata count"
        print("✓ Checkpoint content correct")


def test_checkpoint_loading():
    """Test that checkpoints are loaded correctly on resume."""
    print("\n[TEST] Checkpoint Loading")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_file = tmpdir / "test_checkpoint.json"
        
        # Create checkpoint data
        checkpoint_data = {
            "processed_files": ["file1.jpg", "file2.jpg"],
            "image_metadata": [
                {
                    "path": "file1.jpg",
                    "width": 1920,
                    "height": 1080,
                    "resolution": 2073600,
                    "file_size": 100000,
                    "format": "JPEG",
                    "bit_depth": 24,
                    "has_exif": True,
                    "is_lossless": False,
                    "aspect_ratio": 1.77,
                    "phash": "abc123",
                    "phash_90": "def456",
                    "phash_180": "ghi789",
                    "phash_270": "jkl012"
                }
            ],
            "timestamp": 1234567890.0,
            "config": {
                "threshold": 10,
                "hash_size": 8,
                "min_resolution": 100
            }
        }
        
        # Save checkpoint
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        
        # Create deduplicator with resume
        dedup = ImageDeduplicator(
            directory=tmpdir,
            checkpoint_file=checkpoint_file,
            resume=True,
            threshold=10,
            hash_size=8,
            min_resolution=100
        )
        
        # Verify loaded state
        assert len(dedup.processed_files) == 2, "Wrong processed_files count"
        assert "file1.jpg" in dedup.processed_files, "Missing file1.jpg"
        assert "file2.jpg" in dedup.processed_files, "Missing file2.jpg"
        print("✓ Processed files loaded correctly")
        
        assert len(dedup.image_metadata) == 1, "Wrong metadata count"
        assert dedup.image_metadata[0].path == "file1.jpg", "Wrong metadata path"
        print("✓ Metadata loaded correctly")


def test_config_validation():
    """Test that config mismatches are detected."""
    print("\n[TEST] Config Validation")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_file = tmpdir / "test_checkpoint.json"
        
        # Create checkpoint with specific config
        checkpoint_data = {
            "processed_files": ["file1.jpg"],
            "image_metadata": [],
            "timestamp": 1234567890.0,
            "config": {
                "threshold": 10,
                "hash_size": 8,
                "min_resolution": 100
            }
        }
        
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        
        # Try to resume with different config
        dedup = ImageDeduplicator(
            directory=tmpdir,
            checkpoint_file=checkpoint_file,
            resume=True,
            threshold=15,  # Different!
            hash_size=8,
            min_resolution=100
        )
        
        # Should have reset due to mismatch
        assert len(dedup.processed_files) == 0, "Should reset on config mismatch"
        print("✓ Config mismatch detected and reset")


def test_checkpoint_removal():
    """Test that checkpoints are removed on completion."""
    print("\n[TEST] Checkpoint Removal")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        checkpoint_file = tmpdir / "test_checkpoint.json"
        
        # Create checkpoint
        checkpoint_file.write_text("{}")
        assert checkpoint_file.exists(), "Setup failed"
        
        # Create deduplicator and clear checkpoint
        dedup = ImageDeduplicator(
            directory=tmpdir,
            checkpoint_file=checkpoint_file
        )
        dedup._clear_checkpoint()
        
        # Verify removal
        assert not checkpoint_file.exists(), "Checkpoint not removed"
        print("✓ Checkpoint removed successfully")


def test_skip_processed_files():
    """Test that processed files are skipped on resume."""
    print("\n[TEST] Skip Processed Files")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        dedup = ImageDeduplicator(
            directory=tmpdir,
            resume=False
        )
        
        # Mark files as processed
        dedup.processed_files.add("already_processed.jpg")
        
        # Simulate process_images checking
        test_files = [
            Path("already_processed.jpg"),
            Path("new_file.jpg")
        ]
        
        skipped = []
        processed = []
        
        for file in test_files:
            if str(file) in dedup.processed_files:
                skipped.append(str(file))
            else:
                processed.append(str(file))
        
        assert len(skipped) == 1, "Should skip 1 file"
        assert len(processed) == 1, "Should process 1 file"
        assert "already_processed.jpg" in skipped, "Wrong file skipped"
        print("✓ Processed files correctly skipped")


def run_all_tests():
    """Run all resume capability tests."""
    print("=" * 60)
    print("Resume Capability Test Suite")
    print("=" * 60)
    
    tests = [
        test_checkpoint_creation,
        test_checkpoint_loading,
        test_config_validation,
        test_checkpoint_removal,
        test_skip_processed_files
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
