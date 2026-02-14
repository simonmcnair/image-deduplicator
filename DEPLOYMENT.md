# Deployment & Resume Guide

## Table of Contents
- [Resume Capability](#resume-capability)
- [Docker Deployment](#docker-deployment)
- [GitHub Actions Setup](#github-actions-setup)
- [Production Deployment](#production-deployment)

## Resume Capability

### How It Works

The tool automatically saves processing state every 100 images to a checkpoint file (`.dedup_checkpoint.json` by default). This enables:
- **Interruption Recovery**: Resume after Ctrl+C, crashes, or system failures
- **Large Dataset Processing**: Process massive collections across multiple sessions
- **Cost Optimization**: Pause cloud processing jobs and resume later

### Checkpoint Contents

```json
{
  "processed_files": ["path1.jpg", "path2.jpg", ...],
  "image_metadata": [{...}, {...}, ...],
  "timestamp": 1707912345.678,
  "config": {
    "threshold": 10,
    "hash_size": 8,
    "min_resolution": 100
  }
}
```

### Usage Examples

#### Basic Resume
```bash
# Start processing
python image_deduplicate.py /large/photo/library

# Interrupted? Resume where you left off
python image_deduplicate.py /large/photo/library --resume
```

#### Custom Checkpoint Location
```bash
# Use custom checkpoint file
python image_deduplicate.py /photos \
  --checkpoint-file /backup/.checkpoint.json

# Resume from custom location
python image_deduplicate.py /photos \
  --resume \
  --checkpoint-file /backup/.checkpoint.json
```

#### Docker Resume
```bash
# Create state directory for persistence
mkdir -p ./checkpoint_state

# First run (may be interrupted)
docker run --rm \
  -v $(pwd)/photos:/data \
  -v $(pwd)/checkpoint_state:/state \
  image-deduplicator \
  /data --checkpoint-file /state/.checkpoint.json

# Resume from checkpoint
docker run --rm \
  -v $(pwd)/photos:/data \
  -v $(pwd)/checkpoint_state:/state \
  image-deduplicator \
  /data --resume --checkpoint-file /state/.checkpoint.json
```

#### Docker Compose Resume
```bash
# First run
docker-compose up deduplicator

# Resume if interrupted
docker-compose up deduplicator-resume
```

### Configuration Validation

The checkpoint stores your configuration (threshold, hash_size, min_resolution). If you resume with different settings, the tool will:
1. Detect config mismatch
2. Warn you
3. Start fresh processing

**Example:**
```bash
# Original run
python image_deduplicate.py /photos --threshold 10

# This will start fresh (threshold changed)
python image_deduplicate.py /photos --resume --threshold 15
```

### Checkpoint Lifecycle

| State | Checkpoint Status |
|-------|------------------|
| Processing started | Created after first 100 images |
| Interrupted | Preserved on disk |
| Resumed | Loaded, processing continues |
| Completed successfully | Automatically deleted |
| No duplicates found | Automatically deleted |

### Performance Impact

- **Overhead**: ~2-5% (checkpoint saves every 100 images)
- **Storage**: ~100KB per 1000 images processed
- **I/O**: Minimal (async writes to avoid blocking)

### Best Practices

#### ✓ Do
- Use `--resume` for large datasets (>10K images)
- Store checkpoints on reliable storage (not tmpfs)
- Keep checkpoint files in version control (.gitignore them)
- Use Docker volumes for checkpoint persistence in containers

#### ✗ Don't
- Manually edit checkpoint files (corrupts state)
- Share checkpoints between different directories
- Resume with different configuration parameters
- Use network filesystems for checkpoints (latency issues)

### Troubleshooting

#### Checkpoint Not Loading
```bash
# Check file exists
ls -la .dedup_checkpoint.json

# Validate JSON structure
python -m json.tool .dedup_checkpoint.json

# Start fresh if corrupted
rm .dedup_checkpoint.json
python image_deduplicate.py /photos
```

#### Config Mismatch Warning
```
WARNING - Checkpoint config mismatch. Starting fresh.
```
**Solution**: Use same parameters or delete checkpoint to acknowledge fresh start.

#### Permission Denied
```bash
# Docker: Ensure volume permissions
chown -R 1000:1000 ./checkpoint_state

# Linux: Fix ownership
sudo chown $USER:$USER .dedup_checkpoint.json
```

---

## Docker Deployment

### Build Image

```bash
# Build locally
docker build -t image-deduplicator:latest .

# Multi-platform build
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t image-deduplicator:latest \
  --push .
```

### Run Containers

#### Basic Usage
```bash
docker run --rm \
  -v /path/to/images:/data:ro \
  image-deduplicator:latest
```

#### With Resume Capability
```bash
# Create persistent state directory
mkdir -p ~/.dedup_state

docker run --rm \
  -v /path/to/images:/data:ro \
  -v ~/.dedup_state:/state \
  -v $(pwd)/output:/output \
  image-deduplicator:latest \
  /data \
  --checkpoint-file /state/.checkpoint.json \
  --output /output/report.html
```

#### Advanced Configuration
```bash
docker run --rm \
  -v /path/to/images:/data:ro \
  -v ~/.dedup_state:/state \
  -v $(pwd)/output:/output \
  --memory 4g \
  --cpus 2 \
  image-deduplicator:latest \
  /data \
  --threshold 12 \
  --hash-size 16 \
  --use-ssim \
  --checkpoint-file /state/.checkpoint.json \
  --output /output/report.html \
  --json-output /output/report.json
```

### Docker Compose

```bash
# Start processing
docker-compose up deduplicator

# Resume interrupted job
docker-compose up deduplicator-resume

# With SSIM refinement
docker-compose up deduplicator-ssim

# Cleanup
docker-compose down
```

---

## GitHub Actions Setup

### Required Secrets

Navigate to: **Settings → Secrets and variables → Actions**

#### GitHub Container Registry (Recommended)
No additional secrets needed - uses `GITHUB_TOKEN` automatically.

#### Docker Hub (Optional)
Add these secrets:
- `DOCKER_USERNAME`: Your Docker Hub username
- `DOCKER_PASSWORD`: Docker Hub access token (not password!)

### Workflow Triggers

| Event | Trigger | Action |
|-------|---------|--------|
| Push to `main` | Automatic | Build + Push Docker image |
| Pull Request | Automatic | Run tests, build Docker (no push) |
| Tag `v*.*.*` | Manual | Release build with version tags |

### Testing Workflow

The CI pipeline (`ci.yml`) runs:
1. **Unit tests** on Python 3.9-3.12
2. **Resume capability test** (interruption simulation)
3. **Integration test** (full execution)
4. **Code quality** (ruff, mypy)
5. **Security scan** (bandit, safety)

### Docker Workflow

The Docker pipeline (`docker.yml`) performs:
1. **Multi-platform build** (amd64, arm64)
2. **Resume capability test** in Docker
3. **Vulnerability scan** (Trivy)
4. **Push to registry** (GHCR or Docker Hub)

### Manual Trigger

```bash
# Create and push tag
git tag v1.2.3
git push origin v1.2.3

# GitHub Actions will:
# - Run all tests
# - Build Docker images
# - Tag as: latest, 1.2.3, 1.2, 1
# - Create GitHub Release
```

---

## Production Deployment

### Cloud Deployment

#### AWS ECS
```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

docker build -t image-deduplicator .
docker tag image-deduplicator:latest $ECR_REGISTRY/image-deduplicator:latest
docker push $ECR_REGISTRY/image-deduplicator:latest

# Run ECS task with EFS for state persistence
aws ecs run-task \
  --cluster dedup-cluster \
  --task-definition image-deduplicator \
  --overrides '{
    "containerOverrides": [{
      "name": "deduplicator",
      "command": ["/data", "--resume", "--checkpoint-file", "/state/.checkpoint.json"]
    }]
  }'
```

#### Google Cloud Run
```bash
# Build and push to GCR
gcloud builds submit --tag gcr.io/$PROJECT_ID/image-deduplicator

# Deploy with Cloud Storage for state
gcloud run deploy image-deduplicator \
  --image gcr.io/$PROJECT_ID/image-deduplicator \
  --platform managed \
  --region us-central1 \
  --memory 4Gi \
  --cpu 2 \
  --mount type=cloud-storage,bucket=dedup-state,mount-path=/state
```

#### Azure Container Instances
```bash
# Push to ACR
az acr build --registry $ACR_NAME --image image-deduplicator .

# Run with Azure Files for state
az container create \
  --resource-group dedup-rg \
  --name image-deduplicator \
  --image $ACR_NAME.azurecr.io/image-deduplicator \
  --azure-file-volume-account-name $STORAGE_ACCOUNT \
  --azure-file-volume-share-name dedup-state \
  --azure-file-volume-mount-path /state
```

### Kubernetes Deployment

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: image-deduplicator
spec:
  template:
    spec:
      containers:
      - name: deduplicator
        image: ghcr.io/username/image-deduplicator:latest
        args:
          - /data
          - --resume
          - --checkpoint-file
          - /state/.checkpoint.json
          - --threshold
          - "10"
        volumeMounts:
        - name: images
          mountPath: /data
          readOnly: true
        - name: state
          mountPath: /state
        - name: output
          mountPath: /output
        resources:
          limits:
            memory: 4Gi
            cpu: 2
      restartPolicy: OnFailure
      volumes:
      - name: images
        persistentVolumeClaim:
          claimName: image-pvc
      - name: state
        persistentVolumeClaim:
          claimName: state-pvc
      - name: output
        persistentVolumeClaim:
          claimName: output-pvc
```

### Monitoring

#### Health Checks
```bash
# Container health
docker inspect --format='{{.State.Health.Status}}' image-deduplicator

# Application health
docker exec image-deduplicator python -c "import imagehash, PIL; print('OK')"
```

#### Logging
```bash
# Docker logs
docker logs -f image-deduplicator

# Kubernetes logs
kubectl logs -f job/image-deduplicator
```

#### Metrics
```bash
# Container stats
docker stats image-deduplicator

# Kubernetes metrics
kubectl top pod -l job-name=image-deduplicator
```

### Backup Strategies

#### Checkpoint Backups
```bash
# Automated backup script
#!/bin/bash
CHECKPOINT_DIR="/path/to/checkpoints"
BACKUP_DIR="/backups/dedup"

# Backup every hour
while true; do
  if [ -f "$CHECKPOINT_DIR/.dedup_checkpoint.json" ]; then
    cp "$CHECKPOINT_DIR/.dedup_checkpoint.json" \
       "$BACKUP_DIR/checkpoint_$(date +%Y%m%d_%H%M%S).json"
  fi
  sleep 3600
done
```

#### State Recovery
```bash
# Restore from backup
cp /backups/dedup/checkpoint_20260214_120000.json \
   /state/.dedup_checkpoint.json

# Resume processing
docker run --rm \
  -v /images:/data:ro \
  -v /state:/state \
  image-deduplicator \
  /data --resume --checkpoint-file /state/.dedup_checkpoint.json
```

### Performance Tuning

#### Memory Optimization
```bash
# Monitor memory usage
docker stats --no-stream image-deduplicator

# Adjust container memory
docker run --memory 8g ...
```

#### CPU Optimization
```bash
# Monitor CPU
top -b -n 1 | grep python

# Adjust CPU allocation
docker run --cpus 4 ...
```

#### Disk I/O
```bash
# Monitor disk usage
iostat -x 1

# Use SSD for checkpoints
mount -o noatime /dev/nvme0n1 /state
```

---

## Security Considerations

### Image Scanning
```bash
# Trivy scan
trivy image image-deduplicator:latest

# Grype scan
grype image-deduplicator:latest
```

### Non-root Execution
The Docker image runs as user `dedup` (UID 1000) for security.

### Network Isolation
```bash
# Run without network access
docker run --rm --network none \
  -v /images:/data:ro \
  image-deduplicator
```

### Secrets Management
Never hardcode credentials. Use environment variables or secret managers:

```bash
# AWS Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id dedup-config \
  --query SecretString \
  --output text | docker run --rm -i ...
```

---

## Maintenance

### Cleanup
```bash
# Remove old checkpoints
find /state -name ".dedup_checkpoint.json" -mtime +7 -delete

# Clean Docker
docker system prune -a
```

### Updates
```bash
# Pull latest image
docker pull ghcr.io/username/image-deduplicator:latest

# Rebuild from source
git pull origin main
docker build -t image-deduplicator:latest .
```

### Support
- Report issues: GitHub Issues
- Documentation: README.md
- CI/CD logs: GitHub Actions tab
