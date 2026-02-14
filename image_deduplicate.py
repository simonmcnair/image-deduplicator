#!/usr/bin/env python3
"""
Advanced Image Deduplication Tool
==================================
A production-ready script for identifying duplicate and near-duplicate images
using perceptual hashing with rotation awareness.

Author: Senior Python Engineer
License: MIT
"""

import argparse
import base64
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional

import imagehash
import numpy as np
from PIL import Image, ExifTags
from tqdm import tqdm

# Optional: SSIM for refinement
try:
    from skimage.metrics import structural_similarity as ssim
    SSIM_AVAILABLE = True
except ImportError:
    SSIM_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ImageMetadata:
    """Stores comprehensive metadata for an image file."""
    path: str
    width: int
    height: int
    resolution: int  # width * height
    file_size: int
    format: str
    bit_depth: Optional[int]
    has_exif: bool
    is_lossless: bool
    aspect_ratio: float
    phash: str  # Hex representation
    phash_90: str
    phash_180: str
    phash_270: str
    quality_score: float = 0.0
    group_id: Optional[int] = None
    is_recommended_keeper: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ImageDeduplicator:
    """
    Main class for image deduplication using perceptual hashing.
    
    Perceptual Hashing Strategy:
    ---------------------------
    - Uses pHash (perceptual hash) which creates a hash based on image frequency domain
    - pHash is robust to resizing, compression, and minor color changes
    - hash_size determines precision: larger = more precise but less tolerant
    - Default hash_size=8 creates 64-bit hash (8x8 DCT matrix)
    
    Rotation Handling:
    -----------------
    - Computes 4 hashes: original, 90°, 180°, 270° rotations
    - When comparing images, uses MINIMUM Hamming distance across all orientations
    - This makes the system rotation-invariant
    
    Threshold Tuning:
    ----------------
    - Hamming distance = number of differing bits
    - For hash_size=8 (64 bits):
        * 0-5: Extremely similar (likely duplicates)
        * 6-10: Very similar (probable duplicates with minor changes)
        * 11-15: Similar (check manually)
        * 16+: Likely different images
    - For hash_size=16 (256 bits), scale thresholds proportionally (~4x)
    - Lower threshold = stricter matching (fewer false positives)
    - Higher threshold = looser matching (more potential duplicates found)
    """
    
    # Quality scoring weights
    WEIGHT_RESOLUTION = 0.50  # Highest weight - resolution is key quality indicator
    WEIGHT_FILE_SIZE = 0.20   # File size can indicate compression quality
    WEIGHT_METADATA = 0.15    # EXIF metadata presence
    WEIGHT_FORMAT = 0.15      # Lossless format bonus
    
    LOSSLESS_FORMATS = {'PNG', 'TIFF', 'BMP', 'WEBP'}
    
    def __init__(
        self,
        directory: Path,
        threshold: int = 10,
        hash_size: int = 8,
        min_resolution: int = 100,
        use_ssim: bool = False,
        ssim_threshold: float = 0.95,
        checkpoint_file: Optional[Path] = None,
        resume: bool = False
    ):
        """
        Initialize the deduplicator.
        
        Args:
            directory: Root directory to scan
            threshold: Maximum Hamming distance for duplicates
            hash_size: Size of perceptual hash (8, 16, or 32)
            min_resolution: Minimum image dimension to process
            use_ssim: Enable SSIM refinement for close matches
            ssim_threshold: SSIM similarity threshold (0-1)
            checkpoint_file: Path to checkpoint file for resumability
            resume: Whether to resume from checkpoint
        """
        self.directory = directory
        self.threshold = threshold
        self.hash_size = hash_size
        self.min_resolution = min_resolution
        self.use_ssim = use_ssim and SSIM_AVAILABLE
        self.ssim_threshold = ssim_threshold
        self.checkpoint_file = checkpoint_file or (directory / '.dedup_checkpoint.json')
        self.resume = resume
        
        self.image_metadata: List[ImageMetadata] = []
        self.duplicate_groups: List[List[ImageMetadata]] = []
        self.processed_files: Set[str] = set()
        
        if use_ssim and not SSIM_AVAILABLE:
            logger.warning("SSIM requested but scikit-image not available. Skipping SSIM refinement.")
        
        # Load checkpoint if resuming
        if self.resume and self.checkpoint_file.exists():
            self._load_checkpoint()
    
    def _save_checkpoint(self):
        """Save current processing state to checkpoint file."""
        checkpoint_data = {
            'processed_files': list(self.processed_files),
            'image_metadata': [asdict(meta) for meta in self.image_metadata],
            'timestamp': time.time(),
            'config': {
                'threshold': self.threshold,
                'hash_size': self.hash_size,
                'min_resolution': self.min_resolution
            }
        }
        
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            logger.debug(f"Checkpoint saved: {len(self.processed_files)} files processed")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")
    
    def _load_checkpoint(self):
        """Load processing state from checkpoint file."""
        try:
            with open(self.checkpoint_file, 'r') as f:
                checkpoint_data = json.load(f)
            
            # Verify config matches
            config = checkpoint_data.get('config', {})
            if (config.get('threshold') != self.threshold or 
                config.get('hash_size') != self.hash_size):
                logger.warning("Checkpoint config mismatch. Starting fresh.")
                return
            
            self.processed_files = set(checkpoint_data.get('processed_files', []))
            
            # Reconstruct ImageMetadata objects
            for meta_dict in checkpoint_data.get('image_metadata', []):
                meta = ImageMetadata(**meta_dict)
                self.image_metadata.append(meta)
            
            logger.info(f"Resumed from checkpoint: {len(self.processed_files)} files already processed")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}. Starting fresh.")
            self.processed_files = set()
            self.image_metadata = []
    
    def _clear_checkpoint(self):
        """Remove checkpoint file after successful completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.debug("Checkpoint file removed")
        except Exception as e:
            logger.warning(f"Failed to remove checkpoint: {e}")

    
    def find_images(self) -> List[Path]:
        """Find all supported image files in directory and subdirectories."""
        supported_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        image_files = []
        
        logger.info(f"Scanning directory: {self.directory}")
        for ext in supported_extensions:
            image_files.extend(self.directory.rglob(f'*{ext}'))
            image_files.extend(self.directory.rglob(f'*{ext.upper()}'))
        
        logger.info(f"Found {len(image_files)} image files")
        return image_files
    
    def compute_phash_with_rotations(self, img: Image.Image) -> Tuple[str, str, str, str]:
        """
        Compute perceptual hash for image and its rotations.
        
        Returns:
            Tuple of (hash_0, hash_90, hash_180, hash_270) as hex strings
        """
        hash_0 = str(imagehash.phash(img, hash_size=self.hash_size))
        hash_90 = str(imagehash.phash(img.rotate(90, expand=True), hash_size=self.hash_size))
        hash_180 = str(imagehash.phash(img.rotate(180), hash_size=self.hash_size))
        hash_270 = str(imagehash.phash(img.rotate(270, expand=True), hash_size=self.hash_size))
        
        return hash_0, hash_90, hash_180, hash_270
    
    def extract_metadata(self, image_path: Path) -> Optional[ImageMetadata]:
        """
        Extract comprehensive metadata from an image file.
        
        Returns:
            ImageMetadata object or None if image is corrupted/unsupported
        """
        try:
            with Image.open(image_path) as img:
                # Check minimum resolution
                if min(img.width, img.height) < self.min_resolution:
                    return None
                
                # Basic metadata
                width, height = img.size
                resolution = width * height
                file_size = image_path.stat().st_size
                format_name = img.format or 'UNKNOWN'
                
                # Bit depth
                bit_depth = None
                if hasattr(img, 'bits'):
                    bit_depth = img.bits
                elif img.mode == 'RGB':
                    bit_depth = 24
                elif img.mode == 'RGBA':
                    bit_depth = 32
                elif img.mode == 'L':
                    bit_depth = 8
                
                # EXIF metadata
                has_exif = hasattr(img, '_getexif') and img._getexif() is not None
                
                # Lossless format check
                is_lossless = format_name.upper() in self.LOSSLESS_FORMATS
                
                # Aspect ratio
                aspect_ratio = width / height if height > 0 else 0
                
                # Compute perceptual hashes
                # Convert to RGB for consistent hashing
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                phash_0, phash_90, phash_180, phash_270 = self.compute_phash_with_rotations(img)
                
                return ImageMetadata(
                    path=str(image_path),
                    width=width,
                    height=height,
                    resolution=resolution,
                    file_size=file_size,
                    format=format_name,
                    bit_depth=bit_depth,
                    has_exif=has_exif,
                    is_lossless=is_lossless,
                    aspect_ratio=aspect_ratio,
                    phash=phash_0,
                    phash_90=phash_90,
                    phash_180=phash_180,
                    phash_270=phash_270
                )
        
        except Exception as e:
            logger.warning(f"Failed to process {image_path}: {e}")
            return None
    
    def process_images(self, image_files: List[Path]) -> None:
        """Extract metadata from all images with progress tracking and checkpointing."""
        logger.info("Processing images and computing perceptual hashes...")
        
        checkpoint_interval = 100  # Save checkpoint every N images
        processed_count = 0
        
        for image_path in tqdm(image_files, desc="Processing images"):
            # Skip if already processed (resumability)
            if str(image_path) in self.processed_files:
                continue
            
            metadata = self.extract_metadata(image_path)
            if metadata:
                self.image_metadata.append(metadata)
                self.processed_files.add(str(image_path))
                processed_count += 1
                
                # Periodic checkpoint save
                if processed_count % checkpoint_interval == 0:
                    self._save_checkpoint()
        
        # Final checkpoint save
        self._save_checkpoint()
        logger.info(f"Successfully processed {len(self.image_metadata)} images")
    
    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two hex hash strings.
        
        Hamming distance = number of bit positions where hashes differ
        """
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')
    
    def min_rotation_distance(self, meta1: ImageMetadata, meta2: ImageMetadata) -> int:
        """
        Calculate minimum Hamming distance considering all rotations.
        
        Compares all 4 rotations of image1 against all 4 rotations of image2
        and returns the minimum distance found.
        """
        hashes1 = [meta1.phash, meta1.phash_90, meta1.phash_180, meta1.phash_270]
        hashes2 = [meta2.phash, meta2.phash_90, meta2.phash_180, meta2.phash_270]
        
        min_dist = float('inf')
        for h1 in hashes1:
            for h2 in hashes2:
                dist = self.hamming_distance(h1, h2)
                min_dist = min(min_dist, dist)
        
        return min_dist
    
    def compute_ssim(self, path1: str, path2: str) -> float:
        """
        Compute structural similarity index (SSIM) between two images.
        
        SSIM ranges from -1 to 1, where 1 means identical images.
        Used as optional refinement for close hash matches.
        """
        try:
            with Image.open(path1) as img1, Image.open(path2) as img2:
                # Resize to common size for comparison
                size = (256, 256)
                img1 = img1.convert('L').resize(size)
                img2 = img2.convert('L').resize(size)
                
                arr1 = np.array(img1)
                arr2 = np.array(img2)
                
                return ssim(arr1, arr2)
        except Exception as e:
            logger.warning(f"SSIM computation failed: {e}")
            return 0.0
    
    def find_duplicates(self) -> None:
        """
        Find duplicate groups using graph-based clustering.
        
        Algorithm:
        1. Build similarity graph: edge exists if Hamming distance <= threshold
        2. Use Union-Find to cluster connected components
        3. Each cluster becomes a duplicate group
        """
        logger.info("Finding duplicate groups...")
        
        n = len(self.image_metadata)
        parent = list(range(n))  # Union-Find parent array
        
        def find(x):
            """Find root with path compression."""
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            """Union by linking roots."""
            root_x, root_y = find(x), find(y)
            if root_x != root_y:
                parent[root_x] = root_y
        
        # Stage 1: Fast pre-filter by aspect ratio
        # Group images by similar aspect ratios to reduce comparisons
        aspect_buckets = defaultdict(list)
        aspect_tolerance = 0.05  # 5% tolerance
        
        for idx, meta in enumerate(self.image_metadata):
            bucket_key = round(meta.aspect_ratio / aspect_tolerance) * aspect_tolerance
            aspect_buckets[bucket_key].append(idx)
        
        # Stage 2: Compare images within same aspect ratio bucket
        comparisons = 0
        matches = 0
        
        for bucket_indices in tqdm(aspect_buckets.values(), desc="Comparing images"):
            for i in range(len(bucket_indices)):
                for j in range(i + 1, len(bucket_indices)):
                    idx1, idx2 = bucket_indices[i], bucket_indices[j]
                    meta1 = self.image_metadata[idx1]
                    meta2 = self.image_metadata[idx2]
                    
                    comparisons += 1
                    
                    # Calculate minimum distance across rotations
                    dist = self.min_rotation_distance(meta1, meta2)
                    
                    if dist <= self.threshold:
                        # Stage 3: Optional SSIM refinement
                        if self.use_ssim and dist > self.threshold // 2:
                            ssim_score = self.compute_ssim(meta1.path, meta2.path)
                            if ssim_score < self.ssim_threshold:
                                continue
                        
                        union(idx1, idx2)
                        matches += 1
        
        logger.info(f"Performed {comparisons} comparisons, found {matches} similar pairs")
        
        # Group images by their root parent
        groups = defaultdict(list)
        for idx, meta in enumerate(self.image_metadata):
            root = find(idx)
            groups[root].append(meta)
        
        # Only keep groups with 2+ images (actual duplicates)
        self.duplicate_groups = [group for group in groups.values() if len(group) >= 2]
        
        logger.info(f"Found {len(self.duplicate_groups)} duplicate groups")
    
    def calculate_quality_score(self, meta: ImageMetadata, max_resolution: int, max_file_size: int) -> float:
        """
        Calculate quality score for an image.
        
        Scoring Formula:
        ---------------
        score = (resolution_score * 0.50) +
                (file_size_score * 0.20) +
                (metadata_bonus * 0.15) +
                (format_bonus * 0.15)
        
        Where:
        - resolution_score: normalized pixel count (0-100)
        - file_size_score: normalized file size (0-100)
        - metadata_bonus: 100 if EXIF present, 0 otherwise
        - format_bonus: 100 if lossless format, 50 if lossy
        
        Higher score = better quality to keep
        """
        # Normalize resolution (0-100)
        resolution_score = (meta.resolution / max_resolution * 100) if max_resolution > 0 else 0
        
        # Normalize file size (0-100)
        file_size_score = (meta.file_size / max_file_size * 100) if max_file_size > 0 else 0
        
        # Metadata bonus
        metadata_bonus = 100 if meta.has_exif else 0
        
        # Format bonus
        format_bonus = 100 if meta.is_lossless else 50
        
        # Weighted sum
        score = (
            resolution_score * self.WEIGHT_RESOLUTION +
            file_size_score * self.WEIGHT_FILE_SIZE +
            metadata_bonus * self.WEIGHT_METADATA +
            format_bonus * self.WEIGHT_FORMAT
        )
        
        return round(score, 2)
    
    def assign_quality_scores_and_keepers(self) -> None:
        """
        Calculate quality scores and mark recommended keeper for each group.
        """
        logger.info("Calculating quality scores and identifying keepers...")
        
        for group_id, group in enumerate(self.duplicate_groups):
            # Calculate max values for normalization
            max_resolution = max(img.resolution for img in group)
            max_file_size = max(img.file_size for img in group)
            
            # Calculate scores
            for meta in group:
                meta.quality_score = self.calculate_quality_score(meta, max_resolution, max_file_size)
                meta.group_id = group_id
            
            # Mark highest-scoring image as keeper
            keeper = max(group, key=lambda x: x.quality_score)
            keeper.is_recommended_keeper = True
    
    def generate_thumbnail_base64(self, image_path: str, max_width: int = 150) -> str:
        """
        Generate low-resolution, highly compressed Base64 thumbnail.
        
        This prevents HTML reports from becoming too large.
        """
        try:
            with Image.open(image_path) as img:
                # Calculate thumbnail size maintaining aspect ratio
                aspect = img.height / img.width
                new_width = min(max_width, img.width)
                new_height = int(new_width * aspect)
                
                # Resize
                img.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to RGB if needed
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save to bytes with high compression
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=60, optimize=True)
                
                # Encode to base64
                img_str = base64.b64encode(buffer.getvalue()).decode()
                return f"data:image/jpeg;base64,{img_str}"
        
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail for {image_path}: {e}")
            return ""
    
    def generate_html_report(self, output_path: Path) -> None:
        """
        Generate standalone HTML report with embedded CSS and thumbnails.
        """
        logger.info(f"Generating HTML report: {output_path}")
        
        # Limit groups for performance
        max_groups_per_page = 500
        total_groups = len(self.duplicate_groups)
        
        if total_groups > max_groups_per_page:
            logger.warning(f"Report contains {total_groups} groups. Limiting to first {max_groups_per_page} to prevent browser issues.")
            groups_to_show = self.duplicate_groups[:max_groups_per_page]
        else:
            groups_to_show = self.duplicate_groups
        
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Deduplication Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }
        
        .header {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        
        .header h1 {
            color: #333;
            margin-bottom: 10px;
        }
        
        .header .stats {
            color: #666;
            font-size: 14px;
        }
        
        .group {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        
        .group-header {
            font-size: 18px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }
        
        .images-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .image-card {
            border: 3px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            background: #fafafa;
            transition: transform 0.2s;
        }
        
        .image-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        .image-card.keeper {
            border-color: #4CAF50;
            background: #f1f8f4;
        }
        
        .keeper-badge {
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        .thumbnail {
            width: 100%;
            height: auto;
            border-radius: 4px;
            margin-bottom: 10px;
            display: block;
        }
        
        .metadata {
            font-size: 13px;
            color: #555;
        }
        
        .metadata-row {
            margin: 4px 0;
            display: flex;
            justify-content: space-between;
        }
        
        .metadata-label {
            font-weight: 600;
            color: #333;
        }
        
        .file-path {
            font-size: 11px;
            color: #888;
            word-break: break-all;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #e0e0e0;
        }
        
        .quality-score {
            font-size: 16px;
            font-weight: bold;
            color: #2196F3;
            margin: 8px 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Image Deduplication Report</h1>
        <div class="stats">
            <p><strong>Total Images Scanned:</strong> """ + str(len(self.image_metadata)) + """</p>
            <p><strong>Duplicate Groups Found:</strong> """ + str(total_groups) + """</p>
            <p><strong>Groups Displayed:</strong> """ + str(len(groups_to_show)) + """</p>
            <p><strong>Detection Threshold:</strong> """ + str(self.threshold) + """ (Hamming distance)</p>
            <p><strong>Hash Size:</strong> """ + str(self.hash_size) + """</p>
        </div>
    </div>
"""
        
        for group_id, group in enumerate(tqdm(groups_to_show, desc="Generating HTML")):
            html_content += f"""
    <div class="group">
        <div class="group-header">Group {group_id + 1} — {len(group)} similar images</div>
        <div class="images-container">
"""
            
            for meta in group:
                keeper_class = "keeper" if meta.is_recommended_keeper else ""
                keeper_badge = '<span class="keeper-badge">✓ RECOMMENDED KEEPER</span>' if meta.is_recommended_keeper else ""
                
                thumbnail = self.generate_thumbnail_base64(meta.path)
                
                html_content += f"""
            <div class="image-card {keeper_class}">
                {keeper_badge}
                <img src="{thumbnail}" alt="Thumbnail" class="thumbnail" onerror="this.style.display='none'">
                <div class="quality-score">Quality Score: {meta.quality_score}</div>
                <div class="metadata">
                    <div class="metadata-row">
                        <span class="metadata-label">Resolution:</span>
                        <span>{meta.width} × {meta.height}</span>
                    </div>
                    <div class="metadata-row">
                        <span class="metadata-label">File Size:</span>
                        <span>{self.format_file_size(meta.file_size)}</span>
                    </div>
                    <div class="metadata-row">
                        <span class="metadata-label">Format:</span>
                        <span>{meta.format}</span>
                    </div>
                    <div class="metadata-row">
                        <span class="metadata-label">Lossless:</span>
                        <span>{'Yes' if meta.is_lossless else 'No'}</span>
                    </div>
                    <div class="metadata-row">
                        <span class="metadata-label">EXIF Data:</span>
                        <span>{'Yes' if meta.has_exif else 'No'}</span>
                    </div>
                    <div class="file-path">{meta.path}</div>
                </div>
            </div>
"""
            
            html_content += """
        </div>
    </div>
"""
        
        html_content += """
</body>
</html>
"""
        
        output_path.write_text(html_content, encoding='utf-8')
        logger.info(f"HTML report saved to: {output_path}")
    
    def generate_json_report(self, output_path: Path) -> None:
        """Generate machine-readable JSON report."""
        logger.info(f"Generating JSON report: {output_path}")
        
        report_data = {
            'summary': {
                'total_images': len(self.image_metadata),
                'duplicate_groups': len(self.duplicate_groups),
                'threshold': self.threshold,
                'hash_size': self.hash_size
            },
            'groups': []
        }
        
        for group_id, group in enumerate(self.duplicate_groups):
            group_data = {
                'group_id': group_id,
                'images': [meta.to_dict() for meta in group]
            }
            report_data['groups'].append(group_data)
        
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"JSON report saved to: {output_path}")
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _save_checkpoint(self) -> None:
        """Save current processing state to checkpoint file."""
        try:
            checkpoint_data = {
                'timestamp': time.time(),
                'processed_files': list(self.processed_files),
                'image_metadata': [meta.to_dict() for meta in self.image_metadata],
                'config': {
                    'threshold': self.threshold,
                    'hash_size': self.hash_size,
                    'min_resolution': self.min_resolution,
                    'use_ssim': self.use_ssim,
                    'ssim_threshold': self.ssim_threshold
                }
            }
            
            with self.checkpoint_file.open('w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
            logger.debug(f"Checkpoint saved: {len(self.processed_files)} files processed")
        
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")
    
    def _load_checkpoint(self) -> None:
        """Load processing state from checkpoint file."""
        try:
            with self.checkpoint_file.open('r') as f:
                checkpoint_data = json.load(f)
            
            self.processed_files = set(checkpoint_data['processed_files'])
            
            # Reconstruct ImageMetadata objects
            for meta_dict in checkpoint_data['image_metadata']:
                meta = ImageMetadata(**meta_dict)
                self.image_metadata.append(meta)
            
            checkpoint_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                          time.localtime(checkpoint_data['timestamp']))
            
            logger.info(f"Resumed from checkpoint: {len(self.processed_files)} files "
                       f"already processed (saved {checkpoint_time})")
        
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            self.processed_files = set()
    
    def _clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.debug("Checkpoint file removed")
        except Exception as e:
            logger.warning(f"Failed to remove checkpoint: {e}")
    
    def run(self, html_output: Path, json_output: Path) -> None:
        """Execute the complete deduplication pipeline."""
        # Step 1: Find images
        image_files = self.find_images()
        if not image_files:
            logger.error("No images found!")
            return
        
        # Step 2: Process images (with resumability)
        self.process_images(image_files)
        if not self.image_metadata:
            logger.error("No valid images to process!")
            return
        
        # Step 3: Find duplicates
        self.find_duplicates()
        if not self.duplicate_groups:
            logger.info("No duplicate groups found!")
            # Clear checkpoint even if no duplicates
            self._clear_checkpoint()
            return
        
        # Step 4: Calculate quality scores
        self.assign_quality_scores_and_keepers()
        
        # Step 5: Generate reports
        self.generate_html_report(html_output)
        self.generate_json_report(json_output)
        
        # Step 6: Clear checkpoint on successful completion
        self._clear_checkpoint()
        
        logger.info("✓ Deduplication complete!")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Advanced Image Deduplication Tool with Perceptual Hashing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with defaults
  %(prog)s /path/to/images
  
  # Strict matching (lower threshold)
  %(prog)s /path/to/images --threshold 6
  
  # Loose matching for heavily compressed images
  %(prog)s /path/to/images --threshold 15
  
  # Higher precision hashing
  %(prog)s /path/to/images --hash-size 16 --threshold 20
  
  # With SSIM refinement
  %(prog)s /path/to/images --use-ssim
  
  # Custom output location
  %(prog)s /path/to/images --output /tmp/report.html

Threshold Guidance:
  For hash_size=8 (default):
    - 0-5:   Extremely similar (near-perfect duplicates)
    - 6-10:  Very similar (recommended default)
    - 11-15: Similar with more variation
    - 16+:   Likely different images
  
  For hash_size=16:
    - Scale thresholds by ~4x (e.g., use threshold=24 instead of 6)
        """
    )
    
    parser.add_argument(
        'directory',
        type=str,
        help='Root directory to scan for images'
    )
    
    parser.add_argument(
        '--threshold',
        type=int,
        default=10,
        help='Maximum Hamming distance for duplicates (default: 10)'
    )
    
    parser.add_argument(
        '--hash-size',
        type=int,
        default=8,
        choices=[8, 16, 32],
        help='Perceptual hash size - larger = more precise (default: 8)'
    )
    
    parser.add_argument(
        '--min-resolution',
        type=int,
        default=100,
        help='Minimum image dimension to process (default: 100)'
    )
    
    parser.add_argument(
        '--use-ssim',
        action='store_true',
        help='Enable SSIM refinement for close matches (requires scikit-image)'
    )
    
    parser.add_argument(
        '--ssim-threshold',
        type=float,
        default=0.95,
        help='SSIM similarity threshold 0-1 (default: 0.95)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='duplicates_report.html',
        help='Output HTML report path (default: duplicates_report.html)'
    )
    
    parser.add_argument(
        '--json-output',
        type=str,
        default='duplicates_report.json',
        help='Output JSON report path (default: duplicates_report.json)'
    )
    
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from checkpoint file if it exists'
    )
    
    parser.add_argument(
        '--checkpoint-file',
        type=str,
        default=None,
        help='Custom checkpoint file path (default: .dedup_checkpoint.json in scan directory)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Dry run mode - never deletes files (always enabled)'
    )
    
    args = parser.parse_args()
    
    # Validate directory
    directory = Path(args.directory)
    if not directory.exists():
        logger.error(f"Directory does not exist: {directory}")
        sys.exit(1)
    
    if not directory.is_dir():
        logger.error(f"Path is not a directory: {directory}")
        sys.exit(1)
    
    # Initialize and run deduplicator
    checkpoint_path = Path(args.checkpoint_file) if args.checkpoint_file else None
    
    deduplicator = ImageDeduplicator(
        directory=directory,
        threshold=args.threshold,
        hash_size=args.hash_size,
        min_resolution=args.min_resolution,
        use_ssim=args.use_ssim,
        ssim_threshold=args.ssim_threshold,
        checkpoint_file=checkpoint_path,
        resume=args.resume
    )
    
    html_output = Path(args.output)
    json_output = Path(args.json_output)
    
    logger.info("=" * 60)
    logger.info("Image Deduplication Tool")
    logger.info("=" * 60)
    logger.info(f"Directory: {directory}")
    logger.info(f"Threshold: {args.threshold}")
    logger.info(f"Hash Size: {args.hash_size}")
    logger.info(f"Min Resolution: {args.min_resolution}")
    logger.info(f"SSIM Refinement: {args.use_ssim}")
    logger.info(f"Dry Run: ALWAYS ENABLED (no files will be deleted)")
    logger.info("=" * 60)
    
    try:
        deduplicator.run(html_output, json_output)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
