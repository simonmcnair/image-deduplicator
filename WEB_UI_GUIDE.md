# Web UI User Guide

## Overview

The Image Deduplicator Web UI provides an interactive, browser-based interface for managing duplicate image detection and review. Built with Flask and SQLite, it offers real-time progress monitoring, persistent job history, and visual duplicate comparison.

## Quick Start

### Docker (Recommended)
```bash
# Start web UI
docker-compose up web-ui

# Access at http://localhost:5000
```

### Standalone Python
```bash
# Install dependencies
pip install -r requirements.txt

# Run web UI
python web_ui.py

# Access at http://localhost:5000
```

### Custom Port
```bash
# Using environment variable
PORT=8080 python web_ui.py

# Or modify web_ui.py
app.run(host='0.0.0.0', port=8080)
```

---

## Features

### 1. Dashboard (`/`)

**Create New Jobs:**
- Enter directory path to scan
- Set similarity threshold (0-32)
- Choose hash size (8/16/32)
- Click "Start Processing"

**Active Job Monitoring:**
- Real-time progress bar
- Current file being processed
- Files processed / total count
- Duplicates found so far

**Job History:**
- Last 10 jobs displayed
- Status badges (pending/running/completed/failed)
- Quick access to job details
- Processing statistics

### 2. Job Detail Page (`/jobs/<id>`)

**Job Information:**
- Directory scanned
- Configuration (threshold, hash size)
- Timestamps (created, started, completed)
- Processing progress
- Error messages (if failed)

**Duplicate Groups:**
- List of all duplicate groups found
- Image count per group
- Total size per group
- Quick navigation to group review

### 3. Group Review Page (`/groups/<id>`)

**Visual Comparison:**
- Image grid layout
- Thumbnails with metadata
- Resolution, file size, format
- Keeper recommendations highlighted

**Interactive Actions:**
- **Keep**: Mark image as keeper (green border)
- **Delete**: Mark for deletion (red border, faded)
- **Skip**: No action (default state)

**Image Metadata:**
- Dimensions (width × height)
- File size (KB/MB)
- Format (JPEG, PNG, etc.)
- Quality score (calculated)

---

## Database

### Location
Default: `/app/data/dedup.db` (Docker) or `./dedup.db` (standalone)

Override with environment variable:
```bash
DB_PATH=/custom/path/dedup.db python web_ui.py
```

### Schema

#### Jobs Table
```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    directory TEXT NOT NULL,
    status TEXT NOT NULL,
    threshold INTEGER,
    hash_size INTEGER,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_images INTEGER,
    processed_images INTEGER,
    duplicate_groups INTEGER,
    error_message TEXT
);
```

#### Images Table
```sql
CREATE TABLE images (
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
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
    is_keeper BOOLEAN,
    marked_for_deletion BOOLEAN,
    created_at TIMESTAMP
);
```

#### Duplicate Groups Table
```sql
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
    keeper_image_id INTEGER,
    image_count INTEGER,
    total_size INTEGER,
    potential_savings INTEGER,
    created_at TIMESTAMP
);
```

#### User Actions Table
```sql
CREATE TABLE user_actions (
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
    image_id INTEGER,
    action TEXT,  -- 'keep', 'delete', 'skip'
    timestamp TIMESTAMP
);
```

### Querying the Database

```bash
# Connect to database
sqlite3 /app/data/dedup.db

# List all jobs
SELECT id, directory, status, duplicate_groups FROM jobs;

# Get images marked for deletion
SELECT path, file_size FROM images WHERE marked_for_deletion = 1;

# Calculate potential space savings
SELECT SUM(file_size) FROM images 
WHERE marked_for_deletion = 1;

# User action history
SELECT i.path, ua.action, ua.timestamp 
FROM user_actions ua
JOIN images i ON i.id = ua.image_id
ORDER BY ua.timestamp DESC;
```

---

## API Reference

### Jobs

#### List All Jobs
```http
GET /api/jobs
```

Response:
```json
[
  {
    "id": 1,
    "directory": "/data/photos",
    "status": "completed",
    "threshold": 10,
    "hash_size": 8,
    "created_at": "2026-02-14 10:00:00",
    "total_images": 1000,
    "processed_images": 1000,
    "duplicate_groups": 25
  }
]
```

#### Create New Job
```http
POST /api/jobs
Content-Type: application/json

{
  "directory": "/data/photos",
  "threshold": 10,
  "hash_size": 8
}
```

Response:
```json
{
  "job_id": 1,
  "status": "started"
}
```

#### Get Job Details
```http
GET /api/jobs/<job_id>
```

Response:
```json
{
  "job": { /* job details */ },
  "groups": [ /* duplicate groups */ ]
}
```

#### Get Real-Time Progress
```http
GET /api/jobs/<job_id>/progress
```

Response:
```json
{
  "active": true,
  "progress": 75.5,
  "current_file": "IMG_1234.jpg",
  "total_files": 1000,
  "processed_files": 755,
  "duplicates_found": 18
}
```

#### Get Job Statistics
```http
GET /api/jobs/<job_id>/stats
```

Response:
```json
{
  "total_groups": 25,
  "total_duplicates": 100,
  "total_size": 524288000,
  "potential_savings": 314572800
}
```

### Groups

#### Get Duplicate Group
```http
GET /api/groups/<group_id>
```

Response:
```json
{
  "group": {
    "id": 1,
    "job_id": 1,
    "image_count": 5,
    "total_size": 10485760
  },
  "images": [
    {
      "id": 1,
      "path": "/data/photos/IMG_1.jpg",
      "width": 1920,
      "height": 1080,
      "file_size": 2097152,
      "is_keeper": true,
      "marked_for_deletion": false
    }
  ]
}
```

### Images

#### Mark Image Action
```http
POST /api/images/<image_id>/action
Content-Type: application/json

{
  "action": "delete"  // or "keep" or "skip"
}
```

Response:
```json
{
  "success": true
}
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `/app/data/dedup.db` | SQLite database location |
| `DEBUG` | `false` | Enable Flask debug mode |
| `SECRET_KEY` | auto-generated | Flask session secret |
| `PORT` | `5000` | Web server port |
| `HOST` | `0.0.0.0` | Web server host |

### Docker Volumes

| Mount | Purpose |
|-------|---------|
| `/data` | Image directory to scan |
| `/state` | Checkpoint files |
| `/app/data` | SQLite database |

Example:
```bash
docker run -p 5000:5000 \
  -v /photos:/data:ro \
  -v ./state:/state \
  -v ./database:/app/data \
  image-deduplicator \
  python web_ui.py
```

---

## Workflows

### Basic Workflow
1. **Start Web UI**: `docker-compose up web-ui`
2. **Open Browser**: Navigate to `http://localhost:5000`
3. **Create Job**: Enter directory path and settings
4. **Monitor**: Watch real-time progress
5. **Review**: Click job when completed
6. **Examine Groups**: Browse duplicate groups
7. **Mark Actions**: Keep/delete images in each group
8. **Export**: Query database for deletion list

### Automated Workflow (API)
```bash
# Start web UI in background
docker-compose up -d web-ui

# Create job
JOB_ID=$(curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"directory": "/data/photos", "threshold": 10}' \
  | jq -r '.job_id')

# Poll for completion
while true; do
  STATUS=$(curl -s http://localhost:5000/api/jobs/$JOB_ID/progress | jq -r '.status')
  if [ "$STATUS" = "completed" ]; then
    break
  fi
  sleep 10
done

# Get results
curl http://localhost:5000/api/jobs/$JOB_ID/stats

# Query database for marked images
sqlite3 /path/to/dedup.db \
  "SELECT path FROM images WHERE marked_for_deletion = 1;"
```

### Batch Review Workflow
```python
import requests
import sqlite3

# Connect to database
conn = sqlite3.connect('/path/to/dedup.db')

# Get job ID
job_id = 1

# Auto-mark all non-keepers for deletion
cursor = conn.execute("""
    UPDATE images 
    SET marked_for_deletion = 1 
    WHERE job_id = ? AND is_keeper = 0
""", (job_id,))

conn.commit()

# Generate deletion script
cursor = conn.execute("""
    SELECT path FROM images 
    WHERE marked_for_deletion = 1
""")

with open('delete_images.sh', 'w') as f:
    f.write('#!/bin/bash\n')
    for row in cursor:
        f.write(f'rm "{row[0]}"\n')

print("Deletion script created: delete_images.sh")
```

---

## Troubleshooting

### Web UI Won't Start

**Issue**: `Address already in use`
```
OSError: [Errno 48] Address already in use
```

**Solution**: Change port
```bash
docker run -p 8080:5000 ...
# Access at http://localhost:8080
```

### Database Locked

**Issue**: `database is locked`

**Solution**: Check for other processes
```bash
# Find processes using database
lsof /app/data/dedup.db

# Stop conflicting process
docker stop image-deduplicator-web

# Restart
docker-compose up web-ui
```

### Images Not Displaying

**Issue**: Thumbnails show "No Preview"

**Cause**: Browser security blocks `file://` URLs

**Solutions**:
1. Mount images as static files (production)
2. Use reverse proxy (nginx)
3. Accept limitation for local use

### Job Stuck in "Running"

**Issue**: Job never completes

**Solution**: Check logs and restart
```bash
# Check logs
docker logs image-deduplicator-web

# Restart job
sqlite3 /app/data/dedup.db \
  "UPDATE jobs SET status = 'failed' WHERE id = X;"

# Restart with resume
# Job will automatically resume if checkpoint exists
```

### Out of Memory

**Issue**: Process killed during large jobs

**Solution**: Increase Docker memory
```yaml
# docker-compose.yml
services:
  web-ui:
    deploy:
      resources:
        limits:
          memory: 8G
```

---

## Performance Optimization

### Database Indexes
Already optimized with indexes on:
- `images.job_id`
- `images.group_id`
- `duplicate_groups.job_id`
- `user_actions.job_id`

### Large Datasets

**Pagination** (future feature):
```python
# Current limitation: all groups loaded at once
# For 1000+ groups, consider splitting jobs
```

**Checkpoint Strategy**:
- Saves every 100 images
- Minimal overhead (~2-5%)
- Resume on failure automatic

**Background Processing**:
- Non-blocking threading
- Progress updates every 2 seconds
- No database locks during processing

---

## Security

### Production Deployment

**Never expose to internet without:**
1. Authentication layer (nginx + basic auth)
2. HTTPS/TLS encryption
3. Firewall rules
4. Read-only volume mounts

**Recommended Setup**:
```nginx
# nginx reverse proxy
server {
    listen 443 ssl;
    server_name dedup.example.com;
    
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
    }
}
```

### Secret Key

**Generate secure key**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Set in environment**:
```bash
export SECRET_KEY="your-generated-key-here"
docker-compose up web-ui
```

---

## Backup & Recovery

### Backup Database
```bash
# Hot backup (SQLite 3.27+)
sqlite3 /app/data/dedup.db ".backup /backup/dedup_$(date +%Y%m%d).db"

# Cold backup (stop service first)
docker-compose stop web-ui
cp /app/data/dedup.db /backup/
docker-compose start web-ui
```

### Restore Database
```bash
docker-compose stop web-ui
cp /backup/dedup_20260214.db /app/data/dedup.db
docker-compose start web-ui
```

### Export Data
```bash
# Export to JSON
sqlite3 /app/data/dedup.db << 'SQL'
.mode json
.output /backup/jobs.json
SELECT * FROM jobs;
.output /backup/images.json
SELECT * FROM images;
SQL
```

---

## Integration

### CI/CD Integration
```yaml
# .gitlab-ci.yml
dedup-scan:
  image: image-deduplicator:latest
  script:
    - python web_ui.py &
    - sleep 5
    - curl -X POST http://localhost:5000/api/jobs \
        -H "Content-Type: application/json" \
        -d '{"directory": "/data", "threshold": 10}'
  artifacts:
    paths:
      - dedup.db
```

### Notification Webhooks
```python
# Add to web_ui.py after job completion
import requests

def send_notification(job_id, status):
    webhook_url = os.environ.get('WEBHOOK_URL')
    if webhook_url:
        requests.post(webhook_url, json={
            'job_id': job_id,
            'status': status,
            'timestamp': datetime.now().isoformat()
        })
```

---

## FAQ

**Q: Can multiple jobs run simultaneously?**  
A: No, currently one job at a time. Queue system planned for v2.2.

**Q: How do I delete marked images?**  
A: Query database for `marked_for_deletion = 1`, generate shell script, review and execute.

**Q: Can I undo actions?**  
A: Yes, user actions are logged. Restore from `user_actions` table before executing deletions.

**Q: What's the database size limit?**  
A: SQLite supports up to 281 TB. Practical limit: ~1 million images per database.

**Q: Can I use PostgreSQL instead?**  
A: Not currently. SQLite chosen for simplicity. PostgreSQL support planned for enterprise version.

**Q: How do I migrate jobs between servers?**  
A: Copy entire `dedup.db` file. All data is self-contained.

---

## Support

- **Documentation**: This guide + README.md
- **Issues**: GitHub Issues
- **API Testing**: Use curl or Postman
- **Database**: Use `sqlite3` CLI or GUI tool (DB Browser for SQLite)

---

## Changelog

### v2.1.0 (2026-02-14)
- Initial web UI release
- SQLite persistence
- RESTful API
- Real-time progress monitoring
- Interactive duplicate review

### Future Roadmap
- v2.2: Job queue, batch operations
- v2.3: User authentication, multi-user
- v2.4: Thumbnail caching, pagination
- v3.0: Cloud storage, ML enhancements
