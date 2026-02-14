Image Deduplicator v${VERSION}
==============================

Thank you for downloading Image Deduplicator!

QUICK START
-----------

Option 1: Web UI (Recommended)
  docker-compose up web-ui
  Open http://localhost:5000

Option 2: CLI
  pip install -r requirements.txt
  python image_deduplicate.py /path/to/photos

Option 3: Docker CLI
  docker build -t image-deduplicator .
  docker run -v /photos:/data image-deduplicator

DOCUMENTATION
-------------
- README.md          - Main documentation
- QUICKSTART.md      - Setup guide
- DEPLOYMENT.md      - Production deployment
- RELEASE_NOTES*.md  - What's new in this version
- CHANGELOG.md       - Complete version history

SUPPORT
-------
- GitHub Issues: Report bugs and request features
- Documentation: See README.md for detailed usage
- Tests: Run ./run_tests.sh to verify installation

LICENSE
-------
MIT License - Free for personal and commercial use

Enjoy!
