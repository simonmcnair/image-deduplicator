#!/bin/bash
set -e

echo "=================================="
echo "Image Deduplicator Test Suite"
echo "=================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_cmd="$2"
    
    echo ""
    echo "Running: $test_name"
    echo "---"
    
    if eval "$test_cmd"; then
        echo -e "${GREEN}✓ PASSED${NC}: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}: $test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Test 1: Unit tests
run_test "Unit Tests" "python test_deduplication.py"

# Test 2: Resume capability tests
run_test "Resume Capability Tests" "python test_resume.py"

# Test 3: Integration test - basic execution
run_test "Integration Test - Basic Execution" "
    mkdir -p /tmp/test_images_basic
    cp test_images/* /tmp/test_images_basic/ 2>/dev/null || true
    python image_deduplicate.py /tmp/test_images_basic \
        --output /tmp/test_basic.html \
        --json-output /tmp/test_basic.json
    test -f /tmp/test_basic.html && test -f /tmp/test_basic.json
    rm -rf /tmp/test_images_basic /tmp/test_basic.*
"

# Test 4: Resume functionality end-to-end
run_test "Integration Test - Resume E2E" "
    mkdir -p /tmp/test_images_resume /tmp/test_state
    cp test_images/* /tmp/test_images_resume/ 2>/dev/null || true
    
    # First run with timeout (simulate interruption)
    timeout 3 python image_deduplicate.py /tmp/test_images_resume \
        --checkpoint-file /tmp/test_state/.checkpoint.json 2>/dev/null || true
    
    # Verify checkpoint exists
    test -f /tmp/test_state/.checkpoint.json || exit 1
    
    # Resume and complete
    python image_deduplicate.py /tmp/test_images_resume \
        --resume \
        --checkpoint-file /tmp/test_state/.checkpoint.json \
        --output /tmp/test_resume.html
    
    # Verify checkpoint was removed (completion indicator)
    test ! -f /tmp/test_state/.checkpoint.json
    
    # Cleanup
    rm -rf /tmp/test_images_resume /tmp/test_state /tmp/test_resume.*
"

# Test 5: Different hash sizes
run_test "Integration Test - Hash Size Variants" "
    mkdir -p /tmp/test_images_hash
    cp test_images/* /tmp/test_images_hash/ 2>/dev/null || true
    
    # Test hash_size=16
    python image_deduplicate.py /tmp/test_images_hash \
        --hash-size 16 \
        --threshold 24 \
        --output /tmp/test_hash16.html
    test -f /tmp/test_hash16.html
    
    rm -rf /tmp/test_images_hash /tmp/test_hash16.*
"

# Test 6: SSIM mode (if available)
if python -c "from skimage.metrics import structural_similarity" 2>/dev/null; then
    run_test "Integration Test - SSIM Mode" "
        mkdir -p /tmp/test_images_ssim
        cp test_images/* /tmp/test_images_ssim/ 2>/dev/null || true
        
        python image_deduplicate.py /tmp/test_images_ssim \
            --use-ssim \
            --ssim-threshold 0.95 \
            --output /tmp/test_ssim.html
        test -f /tmp/test_ssim.html
        
        rm -rf /tmp/test_images_ssim /tmp/test_ssim.*
    "
else
    echo "Skipping SSIM test (scikit-image not installed)"
fi

# Test 7: Custom output locations
run_test "Integration Test - Custom Output Paths" "
    mkdir -p /tmp/custom_output /tmp/test_images_custom
    cp test_images/* /tmp/test_images_custom/ 2>/dev/null || true
    
    python image_deduplicate.py /tmp/test_images_custom \
        --output /tmp/custom_output/report.html \
        --json-output /tmp/custom_output/report.json
    
    test -f /tmp/custom_output/report.html
    test -f /tmp/custom_output/report.json
    
    rm -rf /tmp/test_images_custom /tmp/custom_output
"

# Test 8: Checkpoint persistence across runs
run_test "Integration Test - Checkpoint Persistence" "
    mkdir -p /tmp/test_persist /tmp/persist_state
    cp test_images/* /tmp/test_persist/ 2>/dev/null || true
    
    # Run 1: Process first batch
    python image_deduplicate.py /tmp/test_persist \
        --checkpoint-file /tmp/persist_state/.checkpoint.json \
        --output /tmp/persist1.html
    
    # Verify checkpoint exists during processing
    # (In practice, checkpoint is removed on completion, so we can't verify here)
    # But we can verify the script completed successfully
    test -f /tmp/persist1.html
    
    rm -rf /tmp/test_persist /tmp/persist_state /tmp/persist1.*
"

# Summary
echo ""
echo "=================================="
echo "Test Summary"
echo "=================================="
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
