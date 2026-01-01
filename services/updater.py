"""
Auto-updater service for BarberKiosk Agent
Checks GitHub Releases and updates the agent silently in the background
"""
import logging
import os
import sys
import platform
import shutil
import zipfile
import tarfile
import requests
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple
from packaging import version

from version import __version__

logger = logging.getLogger(__name__)

# GitHub repository (update this to your actual repo)
# GitHub repository - update this to your actual repository
# Format: "owner/repo" (e.g., "ezhoosh/BarberKioskAgent")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ezhoosh/BarberKioskAgent")
GITHUB_API_BASE = "https://api.github.com"

# Update directories
RELEASES_DIR = Path.home() / '.barber_agent' / 'releases'
CURRENT_SYMLINK = Path.home() / '.barber_agent' / 'current'
UPDATE_CHECK_INTERVAL = 3600  # Check every hour


class Updater:
    """Handles automatic updates from GitHub Releases"""
    
    def __init__(self):
        self.current_version = __version__
        self.is_updating = False
        self.check_thread: Optional[threading.Thread] = None
        self.stop_checking = False
    
    def start_background_check(self):
        """Start background thread to check for updates periodically"""
        if self.check_thread and self.check_thread.is_alive():
            return
        
        self.stop_checking = False
        self.check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Update checker started")
    
    def stop_background_check(self):
        """Stop background update checking"""
        self.stop_checking = True
        if self.check_thread:
            self.check_thread.join(timeout=2)
        logger.info("Update checker stopped")
    
    def _check_loop(self):
        """Background loop to check for updates"""
        while not self.stop_checking:
            try:
                self.check_and_update()
            except Exception as e:
                logger.exception(f"Error in update check loop: {e}")
            
            # Wait before next check
            for _ in range(UPDATE_CHECK_INTERVAL):
                if self.stop_checking:
                    break
                time.sleep(1)
    
    def check_and_update(self) -> bool:
        """
        Check for updates and install if available.
        Returns True if update was installed, False otherwise.
        """
        if self.is_updating:
            logger.debug("Update already in progress, skipping check")
            return False
        
        try:
            latest_version, download_url = self._get_latest_release()
            if not latest_version or not download_url:
                return False
            
            if version.parse(latest_version) > version.parse(self.current_version):
                logger.info(f"New version available: {latest_version} (current: {self.current_version})")
                return self._install_update(download_url, latest_version)
            else:
                logger.debug(f"Already on latest version: {self.current_version}")
                return False
        except Exception as e:
            logger.exception(f"Error checking for updates: {e}")
            return False
    
    def _get_latest_release(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get latest release version and download URL from GitHub.
        Returns (version, download_url) or (None, None) if not found.
        """
        try:
            url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            release_version = data.get('tag_name', '').lstrip('v')  # Remove 'v' prefix if present
            
            # Find asset for current platform
            assets = data.get('assets', [])
            platform_asset = self._find_platform_asset(assets)
            
            if not platform_asset:
                logger.warning(f"No asset found for platform {platform.system()}")
                return None, None
            
            download_url = platform_asset.get('browser_download_url')
            return release_version, download_url
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch latest release: {e}")
            return None, None
        except Exception as e:
            logger.exception(f"Error getting latest release: {e}")
            return None, None
    
    def _find_platform_asset(self, assets: list) -> Optional[dict]:
        """Find the appropriate asset for the current platform"""
        system = platform.system().lower()
        
        # Determine expected asset name pattern
        if system == 'windows':
            pattern = 'windows'
        elif system == 'darwin':
            pattern = 'macos'
        elif system == 'linux':
            pattern = 'linux'
        else:
            return None
        
        # Look for matching asset with preference order
        # - Windows: prefer zip (contains onedir build) to keep update logic consistent; exe is for manual download.
        # - macOS: prefer zip (for auto-updater); dmg is for manual install.
        preferred_exts = [".zip"]
        if system == "windows":
            preferred_exts = [".zip", ".exe"]
        elif system == "darwin":
            preferred_exts = [".zip", ".dmg"]

        matching = []
        for asset in assets:
            name = (asset.get("name", "") or "").lower()
            if pattern in name:
                matching.append(asset)

        # Sort by preferred extension order
        def _score(a: dict) -> int:
            n = (a.get("name", "") or "").lower()
            for i, ext in enumerate(preferred_exts):
                if n.endswith(ext):
                    return i
            return len(preferred_exts) + 1

        matching.sort(key=_score)
        if matching:
            return matching[0]
        
        return None

    def _resolve_executable_path(self, path: Path) -> Path:
        """
        Resolve an executable path for restart/compare.
        - If given a macOS .app bundle, return its Contents/MacOS/<executable>
        - Otherwise, return the path itself.
        """
        try:
            if platform.system() == "Darwin" and path.suffix == ".app" and path.is_dir():
                macos_dir = path / "Contents" / "MacOS"
                # Prefer BarberAgent binary name, otherwise pick first executable file
                preferred = macos_dir / "BarberAgent"
                if preferred.exists() and os.access(preferred, os.X_OK):
                    return preferred
                if macos_dir.exists():
                    for candidate in macos_dir.iterdir():
                        if candidate.is_file() and os.access(candidate, os.X_OK):
                            return candidate
        except Exception:
            pass
        return path
    
    def _install_update(self, download_url: str, version: str) -> bool:
        """
        Download and install update.
        Returns True if successful, False otherwise.
        """
        if self.is_updating:
            logger.warning("Update already in progress")
            return False
        
        self.is_updating = True
        
        try:
            logger.info(f"Downloading update {version} from {download_url}")
            
            # Create releases directory
            RELEASES_DIR.mkdir(parents=True, exist_ok=True)
            version_dir = RELEASES_DIR / version
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # Download file (keep original extension if possible)
            parsed = urlparse(download_url)
            original_name = Path(parsed.path).name or f"update-{version}.zip"
            download_path = version_dir / original_name
            response = requests.get(download_url, stream=True, timeout=300)
            response.raise_for_status()
            
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded update to {download_path}")
            
            # Extract archive
            extract_dir = version_dir / 'extracted'
            extract_dir.mkdir(exist_ok=True)
            
            if download_path.suffix == '.zip':
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif download_path.suffix in ['.tar', '.gz'] or ''.join(download_path.suffixes).endswith('.tar.gz'):
                with tarfile.open(download_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                logger.error(f"Unsupported archive format: {download_path.suffix}")
                return False
            
            logger.info(f"Extracted update to {extract_dir}")
            
            # Find the executable/app in extracted directory
            app_path = self._find_app_in_directory(extract_dir)
            if not app_path:
                logger.error("Could not find application in extracted archive")
                return False
            
            # Switch to new version (update symlink or copy)
            self._switch_to_version(version, app_path)
            
            logger.info(f"Update {version} installed successfully. Restart required.")
            
            # Schedule restart (will be handled by main application)
            return True
            
        except Exception as e:
            logger.exception(f"Error installing update: {e}")
            return False
        finally:
            self.is_updating = False
    
    def _find_app_in_directory(self, directory: Path) -> Optional[Path]:
        """Find the application executable/app bundle in directory"""
        system = platform.system()
        
        if system == 'Windows':
            # Look for .exe file
            for exe in directory.rglob('*.exe'):
                if 'BarberAgent' in exe.name or 'barber' in exe.name.lower():
                    return exe
        elif system == 'Darwin':
            # Look for .app bundle
            for app in directory.rglob('*.app'):
                return app
            # Or look for executable
            for exe in directory.rglob('BarberAgent'):
                if os.access(exe, os.X_OK):
                    return exe
        else:  # Linux
            # Look for executable
            for exe in directory.rglob('BarberAgent'):
                if os.access(exe, os.X_OK):
                    return exe
        
        return None
    
    def _switch_to_version(self, version: str, app_path: Path):
        """Switch current symlink/copy to point to new version"""
        try:
            # Remove old symlink if exists
            if CURRENT_SYMLINK.exists() or CURRENT_SYMLINK.is_symlink():
                if CURRENT_SYMLINK.is_symlink():
                    CURRENT_SYMLINK.unlink()
                else:
                    shutil.rmtree(CURRENT_SYMLINK)
            
            # Create symlink to new version
            if platform.system() == 'Windows':
                # Windows doesn't support symlinks easily, so we'll copy
                shutil.copytree(app_path.parent, CURRENT_SYMLINK, dirs_exist_ok=True)
            else:
                # Unix: create symlink
                CURRENT_SYMLINK.symlink_to(app_path)
            
            logger.info(f"Switched to version {version}")
            
        except Exception as e:
            logger.exception(f"Error switching to new version: {e}")
            raise
    
    def should_restart(self) -> bool:
        """Check if application should restart to use new version"""
        if not CURRENT_SYMLINK.exists():
            return False
        
        try:
            # Check if current executable is different from symlink target
            current_exe = Path(sys.executable)
            if CURRENT_SYMLINK.is_symlink():
                target = CURRENT_SYMLINK.resolve()
                target_exe = self._resolve_executable_path(target)
                return current_exe != target_exe
        except Exception:
            pass
        
        return False
    
    def restart_application(self):
        """Restart the application using the new version"""
        try:
            if platform.system() == 'Windows':
                # Windows: use subprocess to start new instance
                import subprocess
                new_exe = CURRENT_SYMLINK / 'BarberAgent.exe'
                if new_exe.exists():
                    subprocess.Popen([str(new_exe)])
                    sys.exit(0)
            else:
                # Unix/macOS: exec into new binary (handle .app bundles on macOS)
                import subprocess
                new_target = CURRENT_SYMLINK.resolve() if CURRENT_SYMLINK.is_symlink() else CURRENT_SYMLINK
                new_exe = self._resolve_executable_path(new_target)

                # macOS fallback: if target is an .app and we can't exec its binary, use `open`
                if platform.system() == "Darwin" and new_target.suffix == ".app" and new_target.exists():
                    if not (new_exe.exists() and os.access(new_exe, os.X_OK)):
                        subprocess.Popen(["open", "-n", str(new_target)])
                        sys.exit(0)

                if new_exe.exists() and os.access(new_exe, os.X_OK):
                    os.execv(str(new_exe), [str(new_exe)] + sys.argv[1:])
        except Exception as e:
            logger.exception(f"Error restarting application: {e}")


# Singleton instance
_updater_instance: Optional[Updater] = None


def get_updater() -> Updater:
    """Get the singleton updater instance"""
    global _updater_instance
    if _updater_instance is None:
        _updater_instance = Updater()
    return _updater_instance
