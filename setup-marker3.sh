#!/bin/bash

# ==================================================================================
# MARKER3 SETUP SCRIPT - TWO-PHASE DOCKER DEPLOYMENT
# ==================================================================================
# This script implements the two-phase approach for secure model deployment:
# Phase 1: Download models with network access
# Phase 2: Run production containers with network restrictions
# ==================================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed or not working"
        exit 1
    fi
    
    # Check NVIDIA Docker runtime
    if ! docker info | grep -q nvidia; then
        log_warning "NVIDIA Docker runtime may not be properly configured"
        log_info "Make sure you have nvidia-container-toolkit installed"
    fi
    
    # Check GPU
    if command -v nvidia-smi &> /dev/null; then
        log_info "GPU Status:"
        nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
    else
        log_warning "nvidia-smi not found. GPU may not be available."
    fi
    
    log_success "Prerequisites check completed"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    
    mkdir -p models data output
    
    # Set proper permissions
    chmod 755 models data output
    
    log_success "Directories created"
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    
    docker build -t marker3:latest .
    
    if [ $? -eq 0 ]; then
        log_success "Docker image built successfully"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
}

# Phase 1: Download models
download_models() {
    log_info "Phase 1: Downloading models with network access..."
    
    # Run download service
    docker compose --profile download up marker-download
    
    # Check if download was successful
    if [ -f "./models/.models_downloaded" ]; then
        log_success "Models downloaded successfully"
        log_info "Downloaded models marker found: ./models/.models_downloaded"
    else
        log_error "Model download failed or incomplete"
        exit 1
    fi
}

# Verify models
verify_models() {
    log_info "Verifying downloaded models..."
    
    docker run --rm \
        --gpus all \
        -v "$(pwd)/models:/app/models:ro" \
        marker3:latest \
        python scripts/download_models.py --verify-only
    
    if [ $? -eq 0 ]; then
        log_success "Model verification completed successfully"
    else
        log_error "Model verification failed"
        exit 1
    fi
}

# Phase 2: Start production services
start_production() {
    log_info "Phase 2: Starting production services with network restrictions..."
    
    # Stop any existing services
    docker compose --profile production down 2>/dev/null || true
    
    # Start production services
    docker compose --profile production up -d marker-app
    
    if [ $? -eq 0 ]; then
        log_success "Production services started"
        log_info "Marker3 API available at: http://localhost:8000"
        
        # Wait for health check
        log_info "Waiting for service to be ready..."
        sleep 10
        
        # Check health
        for i in {1..12}; do
            if docker compose --profile production exec marker-app python -c "import marker; print('Marker is ready')" 2>/dev/null; then
                log_success "Marker3 is ready and healthy!"
                break
            else
                log_info "Waiting for service to be ready... ($i/12)"
                sleep 5
            fi
            
            if [ $i -eq 12 ]; then
                log_warning "Service may not be fully ready yet. Check logs with: docker compose --profile production logs marker-app"
            fi
        done
    else
        log_error "Failed to start production services"
        exit 1
    fi
}

# Start web interface (optional)
start_web_interface() {
    log_info "Starting web interface..."
    
    docker compose --profile web up -d marker-web
    
    if [ $? -eq 0 ]; then
        log_success "Web interface started"
        log_info "Streamlit interface available at: http://localhost:8501"
    else
        log_warning "Failed to start web interface (this is optional)"
    fi
}

# Show status
show_status() {
    log_info "Current status:"
    docker compose ps
    
    echo ""
    log_info "Available endpoints:"
    echo "  - API Server: http://localhost:8000"
    echo "  - Web Interface: http://localhost:8501 (if started)"
    
    echo ""
    log_info "Useful commands:"
    echo "  - View logs: docker compose --profile production logs -f marker-app"
    echo "  - Stop services: docker compose --profile production down"
    echo "  - Restart services: docker compose --profile production restart"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker compose --profile download down 2>/dev/null || true
    docker compose --profile production down 2>/dev/null || true
    docker compose --profile web down 2>/dev/null || true
}

# Main execution
main() {
    log_info "Starting Marker3 setup with two-phase deployment..."
    
    # Parse command line arguments
    SKIP_DOWNLOAD=false
    START_WEB=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-download)
                SKIP_DOWNLOAD=true
                shift
                ;;
            --with-web)
                START_WEB=true
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --skip-download    Skip model download phase (use existing models)"
                echo "  --with-web         Start web interface in addition to API"
                echo "  --help             Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Execute setup phases
    check_prerequisites
    create_directories
    build_image
    
    if [ "$SKIP_DOWNLOAD" = false ]; then
        download_models
        verify_models
    else
        log_info "Skipping model download phase"
        if [ ! -f "./models/.models_downloaded" ]; then
            log_error "No models found and --skip-download specified. Run without --skip-download first."
            exit 1
        fi
    fi
    
    start_production
    
    if [ "$START_WEB" = true ]; then
        start_web_interface
    fi
    
    show_status
    
    log_success "Marker3 setup completed successfully!"
    log_info "Your marker3 deployment is now running securely with network restrictions."
}

# Trap cleanup on script exit
trap cleanup EXIT

# Run main function
main "$@"
