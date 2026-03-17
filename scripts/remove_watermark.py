import os
import cv2
import numpy as np
import requests
import logging
from pathlib import Path

# Configure logging for standalone usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

class WatermarkRemover:
    def __init__(self, assets_dir=None):
        logger.info("💧 WatermarkRemover v2.1 (Unicode Fix) Initialized")
        if assets_dir is None:
            # Default to 'assets' folder in the same directory as this script
            self.assets_dir = Path(__file__).parent / "assets"
        else:
            self.assets_dir = Path(assets_dir)
            
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.bg_48_path = self.assets_dir / "bg_48.png"
        self.bg_96_path = self.assets_dir / "bg_96.png"
        
        self.alpha_maps = {}
        self.templates = {}
        
        self._ensure_assets()
        self._init_resources()

    def _ensure_assets(self):
        base_url = "https://raw.githubusercontent.com/journey-ad/gemini-watermark-remover/main/src/assets"
        files = {
            "bg_48.png": self.bg_48_path,
            "bg_96.png": self.bg_96_path
        }
        
        for name, path in files.items():
            if not path.exists():
                logger.info(f"Downloading {name}...")
                try:
                    r = requests.get(f"{base_url}/{name}")
                    r.raise_for_status()
                    with open(path, 'wb') as f:
                        f.write(r.content)
                except Exception as e:
                    logger.error(f"Failed to download {name}: {e}")

    def _calculate_alpha_map(self, bg_image_path):
        if not bg_image_path.exists():
            return None
        
        # Read image
        try:
            # Use imdecode to handle unicode paths
            img = cv2.imdecode(np.fromfile(str(bg_image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            
            # JS Logic: max(r, g, b) / 255.0
            max_channel = np.max(img, axis=2)
            alpha_map = max_channel.astype(np.float32) / 255.0
            return alpha_map
        except Exception as e:
            logger.error(f"Error calculating alpha map for {bg_image_path}: {e}")
            return None

    def _init_resources(self):
        # Load Alpha Maps
        self.alpha_maps[48] = self._calculate_alpha_map(self.bg_48_path)
        self.alpha_maps[96] = self._calculate_alpha_map(self.bg_96_path)
        
        # Load Templates for Detection
        for size, path in [(48, self.bg_48_path), (96, self.bg_96_path)]:
            if path.exists():
                try:
                    tmpl = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
                    if tmpl is not None:
                        self.templates[size] = tmpl
                        logger.info(f"Loaded template for size {size}")
                    else:
                        logger.warning(f"Failed to decode template: {path}")
                except Exception as e:
                    logger.error(f"Error loading template {path}: {e}")

    def _detect_watermark(self, roi, size):
        """
        Detects if the watermark (template) is present in the ROI.
        Returns True if detected, False otherwise.
        """
        template = self.templates.get(size)
        if template is None:
            # logger.warning(f"Template for size {size} not found. Skipping removal.")
            return False

        if roi.shape != template.shape:
            return False

        # Convert to grayscale for correlation check
        roi_gray = cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_BGR2GRAY)
        tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # Normalized Correlation
        res = cv2.matchTemplate(roi_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
        score = res[0][0]
        
        # Threshold: conservative
        threshold = 0.22 
        
        is_detected = score > threshold
        if score > 0.1:
            logger.debug(f"   [Debug] Detection score: {score:.3f} (Size: {size}) -> {'MATCH' if is_detected else 'NO'}")
        
        return is_detected

    def process_image(self, image_path, output_path=None):
        """
        Removes watermark from the image at image_path.
        If output_path is provided, saves there. Otherwise overwrites.
        Returns the path to the processed image.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return str(image_path)
            
        # Use imdecode to handle unicode paths on Windows
        try:
            img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        except Exception as e:
            logger.error(f"Error reading image {image_path}: {e}")
            return str(image_path)

        if img is None:
             logger.error(f"Failed to load image (None): {image_path}")
             return str(image_path)

        # Handle 3 or 4 channels
        if len(img.shape) == 3 and img.shape[2] == 4:
            bgr = img[:, :, :3]
            alpha_channel = img[:, :, 3]
        elif len(img.shape) == 3:
            bgr = img
            alpha_channel = None
        else:
            # Grayscale or other
            bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            alpha_channel = None

        h, w = bgr.shape[:2]
        
        # Strategy: Try ALL corners and ALL sizes.
        # Prioritize Bottom-Right (Standard)
        
        # Sizes to try
        sizes = [96, 48]
        
        detected_config = None
        
        for size in sizes:
            alpha_map = self.alpha_maps.get(size)
            if alpha_map is None: continue
            
            # Margins logic: usually 64 for 96px, 32 for 48px
            margin = 64 if size == 96 else 32
            
            # Define Corners: (x, y, name) - Only checking Bottom-Right as requested
            corners = [
                (w - margin - size, h - margin - size, "Bottom-Right"), # Standard
            ]
            
            for x, y, name in corners:
                if x < 0 or y < 0: continue
                
                # Extract ROI
                roi = bgr[y:y+size, x:x+size].astype(np.float32)
                
                # Detect
                # logger.debug(f"Checking {name} ({size}px)...")
                if self._detect_watermark(roi, size):
                    detected_config = (size, margin, x, y, name)
                    logger.info(f"💧 Watermark DETECTED: {name} ({size}px) in {image_path.name}")
                    break
            
            if detected_config: break
        
        if not detected_config:
            logger.warning(f"⚠️ No watermark detected in any corner for {image_path.name}. Skipping.")
            return str(image_path)
            
        size, margin, x, y, name = detected_config
        roi = bgr[y:y+size, x:x+size].astype(np.float32)
        alpha_map = self.alpha_maps.get(size)
        
        # Constants
        ALPHA_THRESHOLD = 0.002
        MAX_ALPHA = 0.99
        LOGO_VALUE = 255.0
        
        # Removal Logic
        alpha = alpha_map[:, :, np.newaxis]
        mask = alpha >= ALPHA_THRESHOLD
        alpha_clamped = np.minimum(alpha, MAX_ALPHA)
        one_minus_alpha = 1.0 - alpha_clamped
        
        # Formula
        restored_roi = (roi - alpha_clamped * LOGO_VALUE) / one_minus_alpha
        restored_roi = np.clip(restored_roi, 0, 255)
        
        # Update ROI in original image
        output_roi = roi.copy()
        np.putmask(output_roi, np.repeat(mask, 3, axis=2), restored_roi)
        
        # Assign back
        bgr[y:y+size, x:x+size] = output_roi.astype(np.uint8)
        
        # Reconstruct
        if alpha_channel is not None:
            result = np.dstack((bgr, alpha_channel))
        else:
            result = bgr
            
        # Save
        save_path = output_path if output_path else image_path
        try:
            # Use imencode for unicode paths
            is_success, buffer = cv2.imencode(Path(save_path).suffix, result)
            if is_success:
                with open(save_path, "wb") as f:
                    buffer.tofile(f)
                logger.info(f"✨ Watermark removed from {save_path}")
            else:
                logger.error(f"Failed to encode image for saving: {save_path}")
        except Exception as e:
            logger.error(f"Failed to save processed image {save_path}: {e}")
            
        return str(save_path)

if __name__ == "__main__":
    import sys
    remover = WatermarkRemover()
    if len(sys.argv) > 1:
        remover.process_image(sys.argv[1])
    else:
        print("Usage: python remove_watermark.py <image_path>")