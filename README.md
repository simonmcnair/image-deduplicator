# Image Deduplication Tool

[![CI/CD Pipeline](https://github.com/USERNAME/image-deduplicator/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/USERNAME/image-deduplicator/actions)
[![Docker](https://img.shields.io/badge/docker-available-blue.svg)](https://hub.docker.com/r/USERNAME/image-deduplicator)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-ready tool for identifying duplicate and near-duplicate images using perceptual hashing with rotation awareness and resumability.

## Features

- **Perceptual Hashing**: Robust duplicate detection using pHash (DCT-based)
- **Rotation-Aware**: Automatically detects rotated duplicates (90°, 180°, 270°)
- **Resumable Processing**: Checkpoint system for large datasets - interrupt and resume anytime
- **Quality Scoring**: Intelligent keeper recommendation based on resolution, format, and metadata
- **Performance Optimized**: Aspect ratio bucketing reduces O(n²) comparisons
- **Multi-Stage Detection**: Pre-filtering → perceptual hashing → optional SSIM refinement
- **Rich Reports**: HTML with thumbnails + JSON for programmatic access
- **Containerized**: Docker support for consistent cross-platform execution

## Quick Start

### Python
```bash
pip install -r requirements.txt
python image_deduplicate.py /path/to/images
```

### Docker
```bash
docker pull ghcr.io/simonmcnair/image-deduplicator:latest
docker run --rm -v /path/to/images:/data ghcr.io/simonmcnair/image-deduplicator:latest
```

## Resumable Processing

```bash
# Start processing large dataset
python image_deduplicate.py /large/dataset

# Interrupted? Resume from checkpoint
python image_deduplicate.py /large/dataset --resume
```

Checkpoints saved every 100 images to `.dedup_checkpoint.json`

## Usage Examples

```bash
# Strict matching
python image_deduplicate.py /photos --threshold 6

# Higher precision
python image_deduplicate.py /photos --hash-size 16 --threshold 24

# SSIM refinement
python image_deduplicate.py /photos --use-ssim

# Docker with resume
docker run --rm \
  -v $(pwd)/photos:/data \
  -v $(pwd)/.checkpoint.json:/data/.dedup_checkpoint.json \
  image-deduplicator --resume
```

## Threshold Tuning

| hash_size=8 | Interpretation |
|-------------|----------------|
| 0-5 | Near-perfect duplicates |
| **6-10** | **Recommended** - handles compression |
| 11-15 | More tolerant |
| 16+ | May produce false positives |

For hash_size=16, scale thresholds by ~4x

## CI/CD Pipeline

GitHub Actions automatically:
- Runs tests on Ubuntu/Windows/macOS + Python 3.9-3.12
- Builds multi-platform Docker images (amd64, arm64)
- Publishes to Docker Hub + GitHub Container Registry
- Creates releases for version tags

### Setup Secrets
- `DOCKER_USERNAME`: Docker Hub username
- `DOCKER_PASSWORD`: Docker Hub access token

## Performance

| Dataset | Memory | Time | Checkpoint Overhead |
|---------|--------|------|---------------------|
| 1K | ~200 MB | 30-60s | ~5% |
| 10K | ~1.5 GB | 5-8m | ~3% |
| 100K | ~12 GB | 45-60m | ~2% |

## Architecture

```
Image Discovery → Metadata Extraction (checkpointed)
                        ↓
                Aspect Ratio Bucketing
                        ↓
                Duplicate Detection (Union-Find)
                        ↓
                Quality Scoring → Reports
```

**Key Algorithms:**
- **pHash**: DCT-based perceptual hashing
- **Union-Find**: Transitive duplicate clustering
- **Aspect Ratio Bucketing**: 60-80% comparison reduction

## CLI Arguments

```
positional:
  directory              Scan path

options:
  --threshold INT        Hamming distance (default: 10)
  --hash-size {8,16,32}  Hash precision (default: 8)
  --resume               Resume from checkpoint
  --checkpoint-file PATH Custom checkpoint location
  --use-ssim             Enable SSIM refinement
  --output PATH          HTML report path
  --json-output PATH     JSON report path
```

## Output Formats

**HTML**: Visual report with thumbnails, keeper highlighting
**JSON**: Machine-readable with full metadata

## Known Limitations

Cannot detect:
- Mirrored/flipped images
- Heavy cropping (>40%)
- Extreme aspect ratio changes
- Watermark variations

## License

MIT License

## Development

```bash
# Tests
python test_deduplication.py

# Code quality
black --line-length=100 image_deduplicate.py
flake8 image_deduplicate.py --max-line-length=100
mypy image_deduplicate.py --ignore-missing-imports
```
