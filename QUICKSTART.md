# Quick Start Guide - Complete Setup

## Repository Setup

### 1. Initialize Git Repository
```bash
git init
git add .
git commit -m "Initial commit: Image deduplicator v2.0 with resume capability"
```

### 2. Create GitHub Repository
```bash
# Using GitHub CLI
gh repo create image-deduplicator --public --source=. --push

# Or manually on GitHub.com, then:
git remote add origin git@github.com:YOUR_USERNAME/image-deduplicator.git
git branch -M main
git push -u origin main
```

### 3. Configure GitHub Actions

#### Enable Actions
1. Go to **Settings** → **Actions** → **General**
2. Select **Allow all actions and reusable workflows**
3. Save

#### Set Permissions
1. **Settings** → **Actions** → **General** → **Workflow permissions**
2. Select **Read and write permissions**
3. Check **Allow GitHub Actions to create and approve pull requests**
4. Save

#### GitHub Container Registry (Automatic)
No secrets needed - uses `GITHUB_TOKEN` automatically.

Images pushed to: `ghcr.io/YOUR_USERNAME/image-deduplicator`

#### Optional: Docker Hub
If pushing to Docker Hub:
1. **Settings** → **Secrets and variables** → **Actions**
2. Add secrets:
   - `DOCKER_USERNAME`: Your Docker Hub username
   - `DOCKER_PASSWORD`: Docker Hub access token (NOT password!)

Then update `.github/workflows/docker.yml`:
```yaml
env:
  REGISTRY: docker.io
  IMAGE_NAME: YOUR_USERNAME/image-deduplicator
```

### 4. Test CI/CD Pipeline

```bash
# Create test branch
git checkout -b test-ci

# Make small change
echo "# Test" >> README.md
git add README.md
git commit -m "Test: CI/CD pipeline"
git push origin test-ci

# Create pull request (triggers CI)
gh pr create --title "Test CI/CD" --body "Testing pipeline"

# Check Actions tab on GitHub
# Should see:
# - CI - Test & Validate (running tests)
# - Docker Build & Push (building, not pushing)
```

### 5. Test Resume Capability Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
./run_tests.sh

# Expected output:
# ✓ Unit Tests PASSED
# ✓ Resume Capability Tests PASSED
# ✓ Integration Tests PASSED
# All tests passed!
```

---

## First Production Run

### Option 1: Python Direct
```bash
# Start processing
python image_deduplicate.py /path/to/photos

# If interrupted, resume
python image_deduplicate.py /path/to/photos --resume

# Check output
ls -lh duplicates_report.html duplicates_report.json
```

### Option 2: Docker
```bash
# Build image
docker build -t image-deduplicator:local .

# Run with state persistence
mkdir -p ./checkpoint_state

docker run --rm \
  -v /path/to/photos:/data:ro \
  -v $(pwd)/checkpoint_state:/state \
  -v $(pwd)/output:/output \
  image-deduplicator:local \
  /data \
  --checkpoint-file /state/.checkpoint.json \
  --output /output/report.html
```

### Option 3: Docker Compose
```bash
# Update docker-compose.yml with your paths
# volumes:
#   - /path/to/photos:/data:ro

# Run
docker-compose up deduplicator

# Resume if needed
docker-compose up deduplicator-resume
```

---

## Production Deployment

### GitHub Container Registry
```bash
# Pull latest
docker pull ghcr.io/YOUR_USERNAME/image-deduplicator:latest

# Run
docker run --rm \
  -v /photos:/data:ro \
  ghcr.io/YOUR_USERNAME/image-deduplicator:latest
```

### AWS ECS
See `DEPLOYMENT.md` section "AWS ECS" for complete setup.

### Google Cloud Run
See `DEPLOYMENT.md` section "Google Cloud Run" for complete setup.

### Kubernetes
```bash
# Apply deployment
kubectl apply -f k8s-job.yaml

# Monitor
kubectl logs -f job/image-deduplicator
```

---

## Verification Checklist

### Local Development
- [ ] Tests passing: `./run_tests.sh`
- [ ] Docker builds: `docker build -t test .`
- [ ] Docker runs: `docker run --rm test --help`
- [ ] Resume works: Test with `--resume` flag

### GitHub Setup
- [ ] Repository created and pushed
- [ ] Actions enabled
- [ ] CI workflow triggered on push
- [ ] Docker workflow triggered on push to main
- [ ] GHCR permissions configured

### First Run
- [ ] Pull/build image successfully
- [ ] Process test dataset
- [ ] HTML report generated
- [ ] JSON report valid
- [ ] Checkpoint created during processing
- [ ] Checkpoint removed on completion

### Production Ready
- [ ] Multi-platform images available
- [ ] Security scans passing
- [ ] Documentation reviewed
- [ ] Monitoring configured (optional)
- [ ] Backup strategy defined (optional)

---

## Common Issues & Solutions

### Issue: GitHub Actions failing
**Solution:**
1. Check Actions tab for error details
2. Verify test images exist: `ls test_images/`
3. Ensure permissions set correctly
4. Re-run failed jobs

### Issue: Docker build fails
**Solution:**
```bash
# Check Docker version
docker --version  # Need 20.10+

# Clean build
docker system prune -a
docker build --no-cache -t image-deduplicator .
```

### Issue: Permission denied in Docker
**Solution:**
```bash
# Linux: Fix volume permissions
sudo chown -R $USER:$USER ./checkpoint_state ./output

# Or run as root (not recommended)
docker run --user root ...
```

### Issue: Resume not working
**Solution:**
1. Verify checkpoint file exists: `ls -la .dedup_checkpoint.json`
2. Check config matches: Same `--threshold`, `--hash-size`
3. Check file permissions
4. Try with `--checkpoint-file` explicit path

### Issue: Out of memory
**Solution:**
```bash
# Docker: Increase memory
docker run --memory 8g ...

# Local: Process in batches or reduce hash-size
python image_deduplicate.py /photos --hash-size 8  # Lower memory
```

---

## Next Steps

1. **Customize for your use case**
   - Adjust thresholds in docker-compose.yml
   - Configure output paths
   - Set up monitoring/alerting

2. **Scale up**
   - Process larger datasets
   - Deploy to cloud
   - Add to scheduled jobs

3. **Contribute**
   - Report issues
   - Submit improvements
   - Share use cases

4. **Monitor & Maintain**
   - Watch CI/CD pipeline
   - Update dependencies
   - Review security scans
   - Keep documentation current

---

## Support Resources

- **Documentation**: README.md, DEPLOYMENT.md
- **Testing**: run_tests.sh, test_resume.py
- **Examples**: docker-compose.yml
- **Issues**: GitHub Issues tab
- **CI/CD Logs**: GitHub Actions tab

---

## Quick Reference

### Essential Commands
```bash
# Test
./run_tests.sh

# Run locally
python image_deduplicate.py /photos --resume

# Docker build
docker build -t image-deduplicator .

# Docker run with resume
docker run --rm \
  -v /photos:/data:ro \
  -v ./state:/state \
  image-deduplicator \
  /data --resume --checkpoint-file /state/.checkpoint.json

# Docker Compose
docker-compose up deduplicator
docker-compose up deduplicator-resume

# Pull from GHCR
docker pull ghcr.io/YOUR_USERNAME/image-deduplicator:latest

# Check logs
docker logs -f CONTAINER_ID
kubectl logs -f job/image-deduplicator
```

### Key Files
| File | Purpose |
|------|---------|
| `image_deduplicate.py` | Main script |
| `Dockerfile` | Container definition |
| `docker-compose.yml` | Local orchestration |
| `.github/workflows/ci.yml` | CI pipeline |
| `.github/workflows/docker.yml` | Docker build |
| `test_resume.py` | Resume tests |
| `run_tests.sh` | Test runner |
| `DEPLOYMENT.md` | Deployment guide |
| `README.md` | User documentation |

---

## Success Criteria

✓ **Setup Complete When:**
- Repository on GitHub
- Actions running and passing
- Docker images building
- Tests passing locally
- Can process images with resume
- Documentation reviewed

✓ **Production Ready When:**
- Multi-platform images available
- Security scans passing
- Monitoring configured
- Backup strategy defined
- Team trained on usage
