# Release Notes - v2.1.0

## 🎉 Major New Feature: Interactive Web UI

### What's New

**Flask-based Web Interface** - Complete browser-based UI for managing deduplication jobs:
- Real-time progress monitoring with live updates
- Interactive duplicate review and management
- SQLite database for persistent state and history
- RESTful API for programmatic access
- Responsive modern design

### Features

#### Web Dashboard
- **Job Management**: Create, monitor, and review deduplication jobs
- **Real-Time Progress**: Live updates during processing with progress bars
- **Job History**: View all past jobs with status and statistics
- **Interactive Review**: Browse duplicate groups visually
- **Image Actions**: Mark images for keep/delete/skip
- **Database Persistence**: All data stored in SQLite for query and analysis

#### Technical Implementation
- **Backend**: Flask 3.0+ with SQLite
- **Frontend**: Responsive HTML/CSS with vanilla JavaScript
- **API**: RESTful endpoints for all operations
- **Database Schema**: Jobs, Images, Duplicate Groups, User Actions
- **Threading**: Background processing with real-time status updates
- **Persistence**: Full checkpoint resume capability maintained

### Usage

#### Docker Web UI
```bash
# Start web UI
docker-compose up web-ui

# Access at http://localhost:5000
```

#### Standalone Python
```bash
pip install -r requirements.txt
python web_ui.py

# Access at http://localhost:5000
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/api/jobs` | GET | List all jobs |
| `/api/jobs` | POST | Create new job |
| `/api/jobs/<id>` | GET | Get job details |
| `/api/jobs/<id>/progress` | GET | Real-time progress |
| `/api/jobs/<id>/stats` | GET | Job statistics |
| `/api/groups/<id>` | GET | Get duplicate group |
| `/api/images/<id>/action` | POST | Mark image action |
| `/jobs/<id>` | GET | Job detail page |
| `/groups/<id>` | GET | Group review page |

### Database Schema

**Tables:**
- `jobs` - Deduplication job records
- `images` - Image metadata and hashes
- `duplicate_groups` - Grouped duplicates
- `user_actions` - User decisions (keep/delete/skip)

**Key Features:**
- Foreign key constraints for referential integrity
- Indexes for fast queries
- Timestamps for audit trails
- Status tracking (pending/running/completed/failed)

### Screenshots

```
Dashboard:
┌─────────────────────────────────────┐
│  🚀 Start New Job                   │
│  [Directory] [Threshold] [Submit]   │
│                                     │
│  ⚡ Active Processing                │
│  ████████░░ 80% (800/1000)          │
│                                     │
│  📊 Recent Jobs                      │
│  #1 Completed  500 duplicates       │
│  #2 Running    50% complete         │
└─────────────────────────────────────┘

Job View:
┌─────────────────────────────────────┐
│  Job #1 - /photos                   │
│  Status: COMPLETED ✓                 │
│  1000 images, 25 duplicate groups   │
│                                     │
│  📦 Duplicate Groups                 │
│  Group #1  5 images  12 MB          │
│  Group #2  3 images  8 MB           │
│  [Review each group...]             │
└─────────────────────────────────────┘

Group Review:
┌─────────────────────────────────────┐
│  Duplicate Group #1                 │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐     │
│  │img│ │img│ │img│ │img│ │img│     │
│  │ ✓ │ │   │ │   │ │   │ │   │     │
│  └───┘ └───┘ └───┘ └───┘ └───┘     │
│  [Keep] [Delete] buttons per image  │
└─────────────────────────────────────┘
```

### Architecture

```
User Browser
    ↓ HTTP
Flask App (web_ui.py)
    ↓
┌─────────────┬──────────────┐
│   SQLite    │  Image       │
│   Database  │  Deduplicator│
│             │  (background)│
└─────────────┴──────────────┘
         ↓
    /data (images)
    /state (checkpoints)
```

### Configuration

**Environment Variables:**
- `DB_PATH` - Database location (default: `/app/data/dedup.db`)
- `DEBUG` - Enable Flask debug mode (default: `false`)
- `SECRET_KEY` - Flask secret key (default: auto-generated)

**Ports:**
- `5000` - Web UI HTTP port

**Volumes:**
- `/data` - Image directory (mount your photos here)
- `/state` - Checkpoint files
- `/app/data` - SQLite database persistence

---

## ⚡ Improvements from v2.0

### Performance
- Background threading for non-blocking job processing
- Periodic checkpoint saves (every 100 images)
- Database indexes for fast queries
- Real-time progress polling (2-second intervals)

### User Experience
- Visual progress indicators
- Responsive grid layout for image review
- Color-coded status badges
- One-click actions (keep/delete)
- Keeper recommendations highlighted

### Maintainability
- Separated CLI and web UI codebases
- RESTful API design
- Context managers for database connections
- Transaction safety with rollback support
- Comprehensive error handling

---

## 🔄 Compatibility

**Backward Compatible:**
- All v2.0 CLI features preserved
- Same command-line interface
- Existing checkpoints work
- Docker CLI mode unchanged

**New Requirements:**
- Flask>=3.0.0
- Werkzeug>=3.0.0
- SQLite3 (included with Python)

---

## 📦 What's Included

### Core Files
1. `image_deduplicate.py` - CLI tool (unchanged interface)
2. `web_ui.py` - New Flask web application
3. `templates/base.html` - HTML template base
4. `templates/index.html` - Dashboard page
5. `templates/job.html` - Job detail page
6. `templates/group.html` - Group review page

### Configuration
7. `requirements.txt` - Updated with Flask dependencies
8. `Dockerfile` - Multi-mode (CLI/web)
9. `docker-compose.yml` - Web UI service added
10. `VERSION` - Version tracking

### Documentation
11. `CHANGELOG.md` - Updated with v2.1 changes
12. `README.md` - Web UI usage examples
13. `DEPLOYMENT.md` - Web UI deployment guide
14. `WEB_UI_GUIDE.md` - Detailed web UI documentation

---

## 🚀 Migration from v2.0

**No breaking changes!** Web UI is additive:

```bash
# Option 1: Continue using CLI
python image_deduplicate.py /photos

# Option 2: Use new web UI
python web_ui.py
# Visit http://localhost:5000

# Option 3: Docker CLI (unchanged)
docker run -v /photos:/data image-deduplicator

# Option 4: Docker Web UI (new)
docker-compose up web-ui
```

---

## 🐛 Known Issues

1. **Image Preview Limitations**: Direct file:// URLs may not work in all browsers due to security restrictions. Consider setting up a static file server for production.

2. **Concurrent Jobs**: Only one job can run at a time. Queueing system coming in v2.2.

3. **Large Datasets**: Web UI may be slow with 10,000+ images per group. Pagination coming in future release.

---

## 🔮 Roadmap (v2.2+)

- [ ] Job queue for concurrent processing
- [ ] Batch actions (delete all marked images)
- [ ] Export reports from web UI
- [ ] User authentication and multi-user support
- [ ] Thumbnail caching for performance
- [ ] Advanced filtering and search
- [ ] Cloud storage integration (S3, GCS)
- [ ] Mobile-responsive improvements

---

## 📊 Testing

All existing tests pass:
- ✓ Unit tests (Python 3.9-3.12)
- ✓ Resume capability tests
- ✓ Integration tests
- ✓ Docker build tests

New tests added:
- ✓ Web UI route tests
- ✓ Database schema tests
- ✓ API endpoint tests

---

## 💡 Examples

### Automated Workflow
```bash
# Start web UI
docker-compose up -d web-ui

# Create job via API
curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"directory": "/data/photos", "threshold": 10, "hash_size": 8}'

# Monitor progress
curl http://localhost:5000/api/jobs/1/progress

# Get results
curl http://localhost:5000/api/jobs/1
```

### Manual Review Workflow
1. Start web UI: `docker-compose up web-ui`
2. Open browser: `http://localhost:5000`
3. Create job: Enter directory, set threshold
4. Monitor: Watch real-time progress bar
5. Review: Click job to see duplicate groups
6. Decide: Mark each image keep/delete
7. Execute: Use generated report for cleanup

---

## 🙏 Credits

- **Core Algorithm**: perceptual hashing (pHash) + Union-Find clustering
- **Web Framework**: Flask (Pallets Project)
- **Database**: SQLite (public domain)
- **Design**: Modern CSS gradients and responsive layout

---

## 📄 License

MIT License - Same as v2.0

---

## Version History

- **v2.1.0** (2026-02-14): Added web UI, SQLite persistence, RESTful API
- **v2.0.0** (2026-02-14): Added resume capability, GitHub Actions CI/CD
- **v1.0.0** (2026-02-06): Initial release with CLI tool
