#!/usr/bin/env python3
"""
Model Download Script for Marker3 - Two-Phase Approach
=====================================================

Phase 1: Download models WITH network access enabled
Phase 2: Verify downloads and create offline markers

This script ensures all required models are downloaded before network restrictions
are applied in production containers.

Usage:
    python scripts/download_models.py [--verify-only]
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Add the parent directory to the path so we can import marker
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    from huggingface_hub import snapshot_download
    import marker
except ImportError as e:
    print(f"Error importing required packages: {e}")
    print("Please ensure marker and its dependencies are installed")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model configuration - Update these based on marker's actual requirements
MODELS_CONFIG = {
    "surya_models": {
        "detection": "vikp/surya_det3",
        "recognition": "vikp/surya_rec2", 
        "layout": "vikp/surya_layout3",
        "order": "vikp/surya_order",
        "table_rec": "vikp/surya_tablerec"
    },
    "other_models": {
        # Add other models that marker3 uses
        # Example: "some_model": "model_name_on_hf"
    }
}

MODELS_DIR = Path("/app/models")
OFFLINE_MARKER_FILE = MODELS_DIR / ".models_downloaded"

def ensure_models_dir():
    """Create models directory if it doesn't exist."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Models directory: {MODELS_DIR}")

def download_model(model_name: str, model_id: str) -> bool:
    """Download a single model and verify it."""
    try:
        logger.info(f"Downloading {model_name} ({model_id})...")
        
        # Download model to local directory
        local_path = MODELS_DIR / model_name
        
        # Use snapshot_download for complete model download
        snapshot_download(
            repo_id=model_id,
            local_dir=local_path,
            local_dir_use_symlinks=False,
            resume_download=True
        )
        
        logger.info(f"✓ Successfully downloaded {model_name}")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to download {model_name}: {e}")
        return False

def verify_model(model_name: str, model_path: Path) -> bool:
    """Verify that a model was downloaded correctly."""
    try:
        # Check if directory exists and has content
        if not model_path.exists():
            logger.error(f"Model directory doesn't exist: {model_path}")
            return False
            
        # Check for essential files
        essential_files = ["config.json"]
        pytorch_files = list(model_path.glob("*.bin")) + list(model_path.glob("*.safetensors"))
        
        if not any((model_path / f).exists() for f in essential_files):
            logger.error(f"Missing essential files in {model_name}")
            return False
            
        if not pytorch_files:
            logger.error(f"Missing model weights in {model_name}")
            return False
            
        logger.info(f"✓ Model {model_name} verification passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Model {model_name} verification failed: {e}")
        return False

def create_offline_marker(downloaded_models: List[str]):
    """Create marker file indicating successful downloads."""
    marker_data = {
        "downloaded_at": str(Path(__file__).stat().st_mtime),
        "models": downloaded_models,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
        "pytorch_version": torch.__version__
    }
    
    with open(OFFLINE_MARKER_FILE, 'w') as f:
        json.dump(marker_data, f, indent=2)
        
    logger.info(f"✓ Created offline marker: {OFFLINE_MARKER_FILE}")

def check_offline_marker() -> bool:
    """Check if models have been previously downloaded."""
    if not OFFLINE_MARKER_FILE.exists():
        return False
        
    try:
        with open(OFFLINE_MARKER_FILE, 'r') as f:
            marker_data = json.load(f)
            
        logger.info("Found existing offline marker:")
        logger.info(f"  Models: {', '.join(marker_data.get('models', []))}")
        logger.info(f"  CUDA available: {marker_data.get('cuda_available', False)}")
        logger.info(f"  PyTorch version: {marker_data.get('pytorch_version', 'unknown')}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error reading offline marker: {e}")
        return False

def download_all_models() -> bool:
    """Download all required models."""
    ensure_models_dir()
    
    all_models = {}
    all_models.update(MODELS_CONFIG["surya_models"])
    all_models.update(MODELS_CONFIG["other_models"])
    
    downloaded_models = []
    failed_models = []
    
    logger.info(f"Starting download of {len(all_models)} models...")
    
    for model_name, model_id in all_models.items():
        if download_model(model_name, model_id):
            # Verify the download
            model_path = MODELS_DIR / model_name
            if verify_model(model_name, model_path):
                downloaded_models.append(model_name)
            else:
                failed_models.append(model_name)
        else:
            failed_models.append(model_name)
    
    if failed_models:
        logger.error(f"Failed to download models: {', '.join(failed_models)}")
        return False
    
    # Create offline marker
    create_offline_marker(downloaded_models)
    
    logger.info(f"✓ Successfully downloaded all {len(downloaded_models)} models")
    return True

def verify_all_models() -> bool:
    """Verify all models are present and valid."""
    ensure_models_dir()
    
    if not check_offline_marker():
        logger.error("No offline marker found. Models may not have been downloaded.")
        return False
    
    all_models = {}
    all_models.update(MODELS_CONFIG["surya_models"])
    all_models.update(MODELS_CONFIG["other_models"])
    
    verification_results = []
    
    for model_name in all_models.keys():
        model_path = MODELS_DIR / model_name
        result = verify_model(model_name, model_path)
        verification_results.append(result)
    
    all_verified = all(verification_results)
    
    if all_verified:
        logger.info("✓ All models verified successfully")
    else:
        logger.error("✗ Some models failed verification")
    
    return all_verified

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download and verify marker3 models")
    parser.add_argument("--verify-only", action="store_true", 
                       help="Only verify existing models, don't download")
    
    args = parser.parse_args()
    
    if args.verify_only:
        success = verify_all_models()
    else:
        success = download_all_models()
    
    if not success:
        sys.exit(1)
    
    logger.info("Model download/verification completed successfully!")

if __name__ == "__main__":
    main()
