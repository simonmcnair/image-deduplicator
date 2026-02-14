#!/usr/bin/env python3
"""
Web UI for Image Deduplication Tool
====================================
Interactive Flask-based interface with real-time progress, SQLite persistence,
and browser-based duplicate review.

Author: Senior Principal Engineer
"""

import os
import sqlite3
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from contextlib import contextmanager

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from werkzeug.utils import secure_filename

# Import deduplication logic
from image_deduplicate import ImageDeduplicator, ImageMetadata

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024  # 16GB max upload

# Database path
DB_PATH = Path(os.environ.get('DB_PATH', '/app/data/dedup.db'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Global processing state
processing_state = {
    'active': False,
    'progress': 0.0,
    'current_file': '',
    'total_files': 0,
    'processed_files': 0,
    'duplicates_found': 0,
    'job_id': None,
    'error': None
}


# Database Schema
def init_db():
    """Initialize SQLite database with schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                directory TEXT NOT NULL,
                status TEXT NOT NULL,  -- 'pending', 'running', 'completed', 'failed'
                threshold INTEGER NOT NULL,
                hash_size INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                total_images INTEGER DEFAULT 0,
                processed_images INTEGER DEFAULT 0,
                duplicate_groups INTEGER DEFAULT 0,
                error_message TEXT
            );
            
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                resolution INTEGER,
                file_size INTEGER,
                format TEXT,
                bit_depth INTEGER,
                has_exif BOOLEAN,
                is_lossless BOOLEAN,
                aspect_ratio REAL,
                phash TEXT,
                phash_90 TEXT,
                phash_180 TEXT,
                phash_270 TEXT,
                quality_score REAL,
                group_id INTEGER,
                is_keeper BOOLEAN DEFAULT 0,
                marked_for_deletion BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS duplicate_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                keeper_image_id INTEGER,
                image_count INTEGER NOT NULL,
                total_size INTEGER,
                potential_savings INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (keeper_image_id) REFERENCES images(id)
            );
            
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                action TEXT NOT NULL,  -- 'keep', 'delete', 'skip'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_images_job ON images(job_id);
            CREATE INDEX IF NOT EXISTS idx_images_group ON images(group_id);
            CREATE INDEX IF NOT EXISTS idx_groups_job ON duplicate_groups(job_id);
            CREATE INDEX IF NOT EXISTS idx_actions_job ON user_actions(job_id);
        """)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_job(directory: str, threshold: int, hash_size: int) -> int:
    """Create new job in database."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs (directory, status, threshold, hash_size) VALUES (?, ?, ?, ?)",
            (directory, 'pending', threshold, hash_size)
        )
        return cursor.lastrowid


def update_job_status(job_id: int, status: str, **kwargs):
    """Update job status and optional fields."""
    fields = ', '.join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values())
    
    with get_db() as conn:
        if fields:
            conn.execute(
                f"UPDATE jobs SET status = ?, {fields} WHERE id = ?",
                [status] + values + [job_id]
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id)
            )


def save_image_metadata(job_id: int, metadata: ImageMetadata, group_id: Optional[int] = None):
    """Save image metadata to database."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO images (
                job_id, path, width, height, resolution, file_size, format,
                bit_depth, has_exif, is_lossless, aspect_ratio,
                phash, phash_90, phash_180, phash_270, group_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, metadata.path, metadata.width, metadata.height,
            metadata.resolution, metadata.file_size, metadata.format,
            metadata.bit_depth, metadata.has_exif, metadata.is_lossless,
            metadata.aspect_ratio, metadata.phash, metadata.phash_90,
            metadata.phash_180, metadata.phash_270, group_id
        ))


def save_duplicate_group(job_id: int, images: List[ImageMetadata], keeper: ImageMetadata):
    """Save duplicate group to database."""
    with get_db() as conn:
        # Create group
        cursor = conn.execute(
            "INSERT INTO duplicate_groups (job_id, image_count, total_size) VALUES (?, ?, ?)",
            (job_id, len(images), sum(img.file_size for img in images))
        )
        group_id = cursor.lastrowid
        
        # Save images with group_id
        keeper_id = None
        for img in images:
            cursor = conn.execute("""
                INSERT INTO images (
                    job_id, path, width, height, resolution, file_size, format,
                    bit_depth, has_exif, is_lossless, aspect_ratio,
                    phash, phash_90, phash_180, phash_270, group_id, is_keeper
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, img.path, img.width, img.height, img.resolution,
                img.file_size, img.format, img.bit_depth, img.has_exif,
                img.is_lossless, img.aspect_ratio, img.phash, img.phash_90,
                img.phash_180, img.phash_270, group_id, img.path == keeper.path
            ))
            
            if img.path == keeper.path:
                keeper_id = cursor.lastrowid
        
        # Update group with keeper
        conn.execute(
            "UPDATE duplicate_groups SET keeper_image_id = ? WHERE id = ?",
            (keeper_id, group_id)
        )


def background_processing(job_id: int, directory: str, threshold: int, hash_size: int):
    """Background thread for image processing."""
    global processing_state
    
    try:
        processing_state['active'] = True
        processing_state['job_id'] = job_id
        processing_state['error'] = None
        
        update_job_status(job_id, 'running', started_at=datetime.now())
        
        # Create deduplicator
        dedup = ImageDeduplicator(
            directory=Path(directory),
            threshold=threshold,
            hash_size=hash_size,
            checkpoint_file=Path(f'/app/data/checkpoint_{job_id}.json'),
            resume=True
        )
        
        # Find images
        image_files = dedup.find_images()
        processing_state['total_files'] = len(image_files)
        
        update_job_status(job_id, 'running', total_images=len(image_files))
        
        # Process images with progress updates
        for idx, image_path in enumerate(image_files):
            if str(image_path) in dedup.processed_files:
                continue
            
            metadata = dedup.extract_metadata(image_path)
            if metadata:
                dedup.image_metadata.append(metadata)
                dedup.processed_files.add(str(image_path))
                
                # Update progress
                processing_state['processed_files'] = len(dedup.processed_files)
                processing_state['progress'] = (idx + 1) / len(image_files) * 100
                processing_state['current_file'] = image_path.name
                
                # Save checkpoint
                if len(dedup.processed_files) % 100 == 0:
                    dedup._save_checkpoint()
                    update_job_status(job_id, 'running', processed_images=len(dedup.processed_files))
        
        # Final checkpoint
        dedup._save_checkpoint()
        
        # Find duplicates
        dedup.find_duplicates()
        dedup.assign_quality_scores_and_keepers()
        
        # Save results to database
        for group in dedup.duplicate_groups:
            if group:
                keeper = max(group, key=lambda x: x.quality_score)
                save_duplicate_group(job_id, group, keeper)
        
        processing_state['duplicates_found'] = len(dedup.duplicate_groups)
        
        # Complete
        update_job_status(
            job_id, 'completed',
            completed_at=datetime.now(),
            processed_images=len(dedup.image_metadata),
            duplicate_groups=len(dedup.duplicate_groups)
        )
        
        # Cleanup checkpoint
        dedup._clear_checkpoint()
        
    except Exception as e:
        processing_state['error'] = str(e)
        update_job_status(job_id, 'failed', error_message=str(e))
    
    finally:
        processing_state['active'] = False


# Web Routes

@app.route('/')
def index():
    """Main dashboard."""
    with get_db() as conn:
        jobs = conn.execute("""
            SELECT * FROM jobs 
            ORDER BY created_at DESC 
            LIMIT 10
        """).fetchall()
    
    return render_template('index.html', jobs=jobs, processing_state=processing_state)


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """API: List all jobs."""
    with get_db() as conn:
        jobs = conn.execute("""
            SELECT * FROM jobs 
            ORDER BY created_at DESC
        """).fetchall()
    
    return jsonify([dict(job) for job in jobs])


@app.route('/api/jobs', methods=['POST'])
def create_job_api():
    """API: Create new deduplication job."""
    data = request.get_json()
    
    directory = data.get('directory')
    threshold = data.get('threshold', 10)
    hash_size = data.get('hash_size', 8)
    
    if not directory or not Path(directory).exists():
        return jsonify({'error': 'Invalid directory'}), 400
    
    job_id = create_job(directory, threshold, hash_size)
    
    # Start background processing
    thread = threading.Thread(
        target=background_processing,
        args=(job_id, directory, threshold, hash_size),
        daemon=True
    )
    thread.start()
    
    return jsonify({'job_id': job_id, 'status': 'started'}), 201


@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """API: Get job details."""
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        groups = conn.execute("""
            SELECT * FROM duplicate_groups WHERE job_id = ?
        """, (job_id,)).fetchall()
    
    return jsonify({
        'job': dict(job),
        'groups': [dict(g) for g in groups]
    })


@app.route('/api/jobs/<int:job_id>/progress', methods=['GET'])
def get_progress(job_id):
    """API: Get real-time processing progress."""
    if processing_state['job_id'] == job_id:
        return jsonify(processing_state)
    
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify({
            'active': False,
            'status': job['status'],
            'processed_files': job['processed_images'],
            'total_files': job['total_images'],
            'duplicates_found': job['duplicate_groups']
        })


@app.route('/api/groups/<int:group_id>', methods=['GET'])
def get_group(group_id):
    """API: Get duplicate group with images."""
    with get_db() as conn:
        group = conn.execute(
            "SELECT * FROM duplicate_groups WHERE id = ?",
            (group_id,)
        ).fetchone()
        
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        images = conn.execute(
            "SELECT * FROM images WHERE group_id = ?",
            (group_id,)
        ).fetchall()
    
    return jsonify({
        'group': dict(group),
        'images': [dict(img) for img in images]
    })


@app.route('/api/images/<int:image_id>/action', methods=['POST'])
def set_image_action(image_id):
    """API: Mark image action (keep/delete/skip)."""
    data = request.get_json()
    action = data.get('action')
    
    if action not in ['keep', 'delete', 'skip']:
        return jsonify({'error': 'Invalid action'}), 400
    
    with get_db() as conn:
        image = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        # Update image
        if action == 'delete':
            conn.execute(
                "UPDATE images SET marked_for_deletion = 1 WHERE id = ?",
                (image_id,)
            )
        elif action == 'keep':
            conn.execute(
                "UPDATE images SET is_keeper = 1 WHERE id = ?",
                (image_id,)
            )
        
        # Log action
        conn.execute(
            "INSERT INTO user_actions (job_id, image_id, action) VALUES (?, ?, ?)",
            (image['job_id'], image_id, action)
        )
    
    return jsonify({'success': True})


@app.route('/api/jobs/<int:job_id>/stats', methods=['GET'])
def get_job_stats(job_id):
    """API: Get job statistics."""
    with get_db() as conn:
        stats = conn.execute("""
            SELECT 
                COUNT(DISTINCT group_id) as total_groups,
                COUNT(*) as total_duplicates,
                SUM(file_size) as total_size,
                SUM(CASE WHEN marked_for_deletion = 1 THEN file_size ELSE 0 END) as potential_savings
            FROM images 
            WHERE job_id = ? AND group_id IS NOT NULL
        """, (job_id,)).fetchone()
    
    return jsonify(dict(stats))


@app.route('/jobs/<int:job_id>')
def view_job(job_id):
    """View job details page."""
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        
        if not job:
            return "Job not found", 404
        
        groups = conn.execute("""
            SELECT g.*, COUNT(i.id) as image_count
            FROM duplicate_groups g
            LEFT JOIN images i ON i.group_id = g.id
            WHERE g.job_id = ?
            GROUP BY g.id
        """, (job_id,)).fetchall()
    
    return render_template('job.html', job=job, groups=groups)


@app.route('/groups/<int:group_id>')
def view_group(group_id):
    """View duplicate group page."""
    with get_db() as conn:
        group = conn.execute(
            "SELECT * FROM duplicate_groups WHERE id = ?",
            (group_id,)
        ).fetchone()
        
        if not group:
            return "Group not found", 404
        
        images = conn.execute(
            "SELECT * FROM images WHERE group_id = ? ORDER BY quality_score DESC",
            (group_id,)
        ).fetchall()
    
    return render_template('group.html', group=group, images=images)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
