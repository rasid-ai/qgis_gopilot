# -*- coding: utf-8 -*-
"""
Virtual Environment Manager for GoPilot Plugin
Manages an isolated venv for plugin dependencies to avoid polluting QGIS Python.
"""

import os
import sys
import subprocess
import shutil
import importlib.util
import importlib.metadata
import re
from pathlib import Path
from typing import List, Tuple, Optional, Callable

from qgis.PyQt.QtCore import QThread, pyqtSignal


# Plugin configuration
MIN_PYTHON_VERSION = (3, 9)
# Store venv in plugin root directory (one level up from rasid_components)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "qgis_gopilot_venv")
PYTHON_VERSION = f"py{sys.version_info.major}.{sys.version_info.minor}"


def _load_requirements_from_file() -> List[Tuple[str, str]]:
    """Load requirements from requirements.txt file.

    Returns:
        List of tuples: (import_name, pip_install_spec)
        Example: [("keyring", "keyring>=23.0.0"), ...]
    """
    # Go up 3 levels: venv_manager.py -> dependencies -> rasid_components -> plugin root
    requirements_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'requirements.txt'
    )
    packages = []

    try:
        with open(requirements_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Extract import name from pip spec
                # "keyring>=23.0.0" → "keyring"
                import_name = line.split('>=')[0].split('==')[0].split('<')[0].split('[')[0].strip()

                if import_name:
                    packages.append((import_name, line))

        # If we successfully read the file, return it
        if packages:
            return packages

    except Exception as e:
        # Log the error for debugging
        print(f"[venv_manager] Error reading requirements.txt: {e}")

    # Fallback if file is missing or unreadable or empty
    return [
        ("keyring", "keyring>=23.0.0"),
        ("requests", "requests>=2.25.0"),
        ("markdown", "markdown>=3.3.0"),
    ]


# Dependency specs: (import_name, pip_install_name)
# Note: Call get_required_packages() instead of using this directly
# to ensure fresh reload of requirements.txt
REQUIRED_PACKAGES = _load_requirements_from_file()


def get_required_packages(force_reload: bool = True) -> List[Tuple[str, str]]:
    """Get the current list of required packages from requirements.txt.

    This reloads the file each time to pick up changes without needing
    to restart QGIS.

    Args:
        force_reload: If True, always reload from file. If False, use cached.

    Returns:
        List of tuples: (import_name, pip_install_spec)
    """
    if force_reload:
        return _load_requirements_from_file()
    return REQUIRED_PACKAGES


def get_venv_dir() -> str:
    """Get the path to the plugin's virtual environment directory.

    Returns:
        Path to the venv directory (plugin_root/qgis_gopilot_venv/venv_pyX.Y).
    """
    return os.path.join(CACHE_DIR, f"venv_{PYTHON_VERSION}")


def get_venv_python_path(venv_dir: Optional[str] = None) -> str:
    """Get the path to the Python executable inside the venv.

    Args:
        venv_dir: Path to the venv directory. Defaults to get_venv_dir().

    Returns:
        Path to the venv's Python executable.
    """
    if venv_dir is None:
        venv_dir = get_venv_dir()

    if sys.platform == "win32":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python3")


def get_venv_site_packages(venv_dir: Optional[str] = None) -> str:
    """Get the path to the venv's site-packages directory.

    Args:
        venv_dir: Path to the venv directory. Defaults to get_venv_dir().

    Returns:
        Path to the venv's site-packages directory.
    """
    if venv_dir is None:
        venv_dir = get_venv_dir()

    if sys.platform == "win32":
        return os.path.join(venv_dir, "Lib", "site-packages")

    # On Unix, detect the actual Python version directory
    lib_dir = os.path.join(venv_dir, "lib")
    if os.path.isdir(lib_dir):
        for entry in sorted(os.listdir(lib_dir)):
            if entry.startswith("python"):
                candidate = os.path.join(lib_dir, entry, "site-packages")
                if os.path.isdir(candidate):
                    return candidate

    # Fallback using current Python version
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return os.path.join(venv_dir, "lib", py_ver, "site-packages")


def venv_exists(venv_dir: Optional[str] = None) -> bool:
    """Check if the plugin's virtual environment exists and has a Python executable.

    Args:
        venv_dir: Path to the venv directory. Defaults to get_venv_dir().

    Returns:
        True if the venv directory and Python executable exist.
    """
    if venv_dir is None:
        venv_dir = get_venv_dir()
    python_path = get_venv_python_path(venv_dir)
    return os.path.isdir(venv_dir) and os.path.isfile(python_path)


def venv_python_usable(venv_dir: Optional[str] = None) -> Tuple[bool, str]:
    """Return whether the venv Python starts with the expected stdlib.

    Args:
        venv_dir: Path to the venv directory. Defaults to get_venv_dir().

    Returns:
        Tuple of (usable, error_message). error_message is empty when usable is True.
    """
    if venv_dir is None:
        venv_dir = get_venv_dir()
    python_path = get_venv_python_path(venv_dir)
    if not os.path.isdir(venv_dir):
        return False, f"Virtual environment does not exist: {venv_dir}"
    if not os.path.isfile(python_path):
        return False, f"Virtual environment Python is missing: {python_path}"
    return _python_executable_usable(python_path)


def _add_venv_to_path() -> bool:
    """Internal function: Add venv site-packages to sys.path if it exists.

    Does NOT create venv or install packages. Used by check_dependencies()
    to avoid circular recursion.

    Returns:
        True if site-packages was added or already present, False if venv
        does not exist.
    """
    if not venv_exists():
        return False

    site_packages = get_venv_site_packages()
    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)
    return True


def ensure_venv_packages_available() -> bool:
    """Add the venv's site-packages to sys.path if the venv exists.

    This does NOT create the venv or install packages automatically.
    Use DependencyManager.prompt_install() to show the installation dialog.

    This is safe to call multiple times (idempotent).

    Returns:
        True if site-packages was added or already present, False if venv
        does not exist or packages are missing.
    """
    # Simply delegate to the internal function
    return _add_venv_to_path()


def _dependency_discoverable(import_name: str) -> Tuple[bool, Optional[str]]:
    """Return whether a dependency is discoverable on sys.path.

    Args:
        import_name: Dotted module name to probe.

    Returns:
        Tuple of (discoverable, error_message). error_message is None when
        discoverable is True.
    """
    try:
        if importlib.util.find_spec(import_name) is None:
            return False, f"No module named {import_name!r}"
    except (ImportError, ModuleNotFoundError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def _distribution_name(pip_name: str) -> str:
    """Return a best-effort distribution name from a pip requirement string."""
    return (
        pip_name.split("[", 1)[0]
        .split(">", 1)[0]
        .split("<", 1)[0]
        .split("=", 1)[0]
        .strip()
    )


def _dependency_version(pip_name: str) -> Optional[str]:
    """Return an installed distribution version without importing the package."""
    try:
        return importlib.metadata.version(_distribution_name(pip_name))
    except importlib.metadata.PackageNotFoundError:
        return None


def _package_in_venv(import_name: str, pip_name: str) -> bool:
    """Check if a package is installed specifically in the venv's site-packages.

    This checks the actual venv directory, not just if the package is importable
    from anywhere in sys.path. This ensures we detect missing packages even if
    they exist in QGIS's Python environment.

    Args:
        import_name: Python import name (e.g., "keyring")
        pip_name: Pip package spec (e.g., "keyring>=23.0.0")

    Returns:
        True if the package is installed in the venv, False otherwise.
    """
    if not venv_exists():
        return False

    site_packages = get_venv_site_packages()
    if not os.path.isdir(site_packages):
        return False

    # Check using importlib.metadata with the venv's site-packages
    # This checks if the distribution is installed in the venv specifically
    dist_name = _distribution_name(pip_name)

    # Check if the package's dist-info directory exists in venv's site-packages
    # This is more reliable than checking if it's importable
    for entry in os.listdir(site_packages):
        entry_lower = entry.lower()
        dist_name_lower = dist_name.lower().replace('-', '_')

        # Check for dist-info or egg-info directories
        if (entry_lower.startswith(dist_name_lower) and
            (entry_lower.endswith('.dist-info') or entry_lower.endswith('.egg-info'))):
            return True

    return False


def python_runtime_supported() -> bool:
    """Return True when the current Python can install/run the plugin."""
    return sys.version_info >= MIN_PYTHON_VERSION


def python_runtime_error() -> str:
    """Return a clear unsupported-runtime message for QGIS users."""
    required = ".".join(str(part) for part in MIN_PYTHON_VERSION)
    current = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return (
        f"QGIS GoPilot requires Python {required} or newer. "
        f"This QGIS session is using Python {current}. "
        f"Install a newer QGIS build, or use a QGIS Python environment based on "
        f"Python {required}+."
    )


def check_dependencies() -> List[dict]:
    """Check if required Python packages are installed in the venv.

    Returns:
        List of dicts with keys: name, pip_name, installed, version, error.
        error is populated when the package is not installed in venv.
    """
    # Get fresh list of required packages from requirements.txt
    required_packages = get_required_packages()

    # If venv doesn't exist, ALL packages are missing
    if not venv_exists():
        return [
            {
                "name": import_name,
                "pip_name": pip_name,
                "installed": False,
                "version": None,
                "error": "Virtual environment does not exist"
            }
            for import_name, pip_name in required_packages
        ]

    # Venv exists - add it to path and check if packages are in venv
    _add_venv_to_path()
    results = []
    for import_name, pip_name in required_packages:
        info = {
            "name": import_name,
            "pip_name": pip_name,
            "installed": False,
            "version": None,
            "error": None,
        }

        # Check if package is installed specifically in the venv
        if _package_in_venv(import_name, pip_name):
            info["installed"] = True
            info["version"] = _dependency_version(pip_name) or "installed"
        else:
            info["error"] = f"Not installed in venv"

        results.append(info)
    return results


def all_dependencies_met() -> bool:
    """Return True if venv exists and all required packages are installed in it.

    Returns:
        True if venv exists and all dependencies are installed in the venv.
    """
    # If venv doesn't exist, dependencies are NOT met
    if not venv_exists():
        return False

    _add_venv_to_path()
    # Get fresh list of required packages
    required_packages = get_required_packages()
    return all(
        _package_in_venv(import_name, pip_name)
        for import_name, pip_name in required_packages
    )


def get_missing_packages() -> List[str]:
    """Return pip install names of missing packages.

    Returns:
        List of pip package names that are not currently importable.
    """
    return [
        dep["pip_name"]
        for dep in check_dependencies()
        if not dep["installed"]
    ]


def _get_clean_env() -> dict:
    """Get a clean copy of the environment for subprocess calls.

    Removes variables that could interfere with venv creation and pip installs.

    Returns:
        A copy of os.environ with problematic variables removed.
    """
    env = os.environ.copy()
    for var in ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"]:
        env.pop(var, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _get_subprocess_kwargs() -> dict:
    """Get platform-specific subprocess keyword arguments.

    On Windows, suppresses the console window that would otherwise pop up.

    Returns:
        Dict of kwargs to pass to subprocess.run().
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _python_executable_names() -> List[str]:
    """Return expected Python executable names for the current runtime."""
    versioned = f"python{sys.version_info.major}.{sys.version_info.minor}"
    names = [versioned, f"python{sys.version_info.major}", "python3", "python"]
    if sys.platform == "win32":
        return [f"{name}.exe" for name in names]
    return names


def _python_version_spec() -> str:
    """Return the Python major.minor version required by this QGIS session."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _looks_like_python_executable(path: Optional[str]) -> bool:
    """Return True when path names a Python interpreter binary."""
    if not path:
        return False
    name = os.path.basename(path).lower()
    if sys.platform == "win32" and name.endswith(".exe"):
        name = name[:-4]
    return bool(re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", name))


def _add_existing_python_candidate(
    candidates: List[str], seen: set, path: Optional[str]
) -> None:
    """Append path when it exists and looks like a Python interpreter."""
    if not path or not _looks_like_python_executable(path):
        return
    normalized = os.path.abspath(path)
    if normalized in seen or not os.path.isfile(normalized):
        return
    candidates.append(normalized)
    seen.add(normalized)


def _python_executable_usable(path: str) -> Tuple[bool, str]:
    """Return whether path can run as the current QGIS Python version.

    Args:
        path: Path to Python executable to test.

    Returns:
        Tuple of (usable, error_message). error_message is empty when usable is True.
    """
    code = (
        "import encodings, sys; "
        f"raise SystemExit(0 if sys.version_info[:2] == "
        f"({sys.version_info.major}, {sys.version_info.minor}) else 3)"
    )
    try:
        result = subprocess.run(
            [path, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
            env=_get_clean_env(),
            **_get_subprocess_kwargs(),
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if result.returncode == 0:
        return True, ""
    if result.returncode == 3:
        return False, f"wrong Python version; need {_python_version_spec()}"

    error = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
    if len(error) > 500:
        error = "..." + error[-500:]
    return False, error


def _first_usable_python_candidate(
    candidates: List[str], rejected: List[str]
) -> Optional[str]:
    """Return the first candidate that starts successfully."""
    for candidate in candidates:
        usable, reason = _python_executable_usable(candidate)
        if usable:
            return candidate
        rejected.append(f"{candidate}: {reason}")
    return None


def _find_python_executable() -> str:
    """Find a working Python executable for subprocess calls.

    In QGIS, sys.executable can point to the QGIS application binary
    instead of a Python interpreter. This function uses a simplified
    approach that works for modern QGIS installations.

    Returns:
        Path to a Python executable.

    Raises:
        RuntimeError: If no Python interpreter can be found.
    """
    candidates: List[str] = []
    seen = set()

    # Try sys._base_executable first (most reliable in modern Python)
    _add_existing_python_candidate(
        candidates, seen, getattr(sys, "_base_executable", None)
    )

    # Try sys.executable
    _add_existing_python_candidate(candidates, seen, sys.executable)

    # Try python from PATH
    for name in _python_executable_names():
        _add_existing_python_candidate(candidates, seen, shutil.which(name))

    # Windows: Try base_prefix
    if sys.platform == "win32":
        base_prefix = getattr(sys, "_base_prefix", None) or sys.prefix
        python_in_prefix = os.path.join(base_prefix, "python.exe")
        _add_existing_python_candidate(candidates, seen, python_in_prefix)

        # Try next to sys.executable
        exe_dir = os.path.dirname(sys.executable)
        for name in ("python.exe", "python3.exe"):
            _add_existing_python_candidate(
                candidates, seen, os.path.join(exe_dir, name)
            )

    # Test candidates
    rejected: List[str] = []
    python_exe = _first_usable_python_candidate(candidates, rejected)
    if python_exe:
        return python_exe

    # All failed - show clear error
    raise RuntimeError(
        "Could not find a Python interpreter for dependency installation.\n\n"
        f"sys.executable: {sys.executable}\n"
        "QGIS GoPilot requires a working Python interpreter.\n\n"
        "You can install dependencies manually:\n"
        "  pip install keyring requests markdown\n\n"
        f"Tried: {', '.join(candidates[:5])}"
    )




def _cleanup_partial_venv(venv_dir: str) -> None:
    """Remove a partially created venv directory (best-effort)."""
    if os.path.isdir(venv_dir):
        try:
            shutil.rmtree(venv_dir)
        except OSError:
            pass


def _verify_pip_and_return(python_path: str) -> str:
    """Ensure pip is available in the venv and return the python path.

    Args:
        python_path: Path to the venv's Python executable.

    Returns:
        The python_path if pip is verified.

    Raises:
        RuntimeError: If pip cannot be made available.
    """
    usable, reason = _python_executable_usable(python_path)
    if not usable:
        raise RuntimeError(
            "Virtual environment Python is not usable.\n"
            f"Python path: {python_path}\n"
            f"Error: {reason}"
        )

    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    # Try ensurepip
    subprocess.run(
        [python_path, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        **kwargs,
    )

    # Verify pip works
    result = subprocess.run(
        [python_path, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        **kwargs,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "pip is not available in the virtual environment.\n"
            f"Python path: {python_path}\n"
            f"Error: {result.stderr or result.stdout}"
        )

    return python_path




def _ensure_usable_venv(
    venv_dir: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Return a usable venv Python, recreating stale broken venvs when needed."""
    if venv_exists(venv_dir):
        usable, reason = venv_python_usable(venv_dir)
        if usable:
            return get_venv_python_path(venv_dir)
        if progress_callback:
            progress_callback("Existing virtual environment is unusable; recreating it...")
        _cleanup_partial_venv(venv_dir)

    if progress_callback:
        progress_callback("Creating virtual environment...")
    return create_venv(venv_dir, progress_callback)


def create_venv(venv_dir: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
    """Create a virtual environment at the specified path.

    Args:
        venv_dir: Path where the venv should be created.
        progress_callback: Optional callback for progress updates.

    Returns:
        Path to the Python executable inside the newly created venv.

    Raises:
        RuntimeError: If venv creation fails.
    """
    if not python_runtime_supported():
        raise RuntimeError(python_runtime_error())

    os.makedirs(os.path.dirname(venv_dir), exist_ok=True)

    python_path = get_venv_python_path(venv_dir)
    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    # Find Python executable
    try:
        python_exe = _find_python_executable()
    except RuntimeError as exc:
        raise RuntimeError(
            "Could not create virtual environment: no working Python interpreter found.\n\n"
            + str(exc)
        )

    # Create venv using subprocess
    cmd = [python_exe, "-m", "venv", venv_dir]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        **kwargs,
    )

    if result.returncode == 0 and os.path.isfile(python_path):
        if progress_callback:
            progress_callback("Virtual environment created successfully!")
        return _verify_pip_and_return(python_path)

    # Failed - clean up and raise error
    _cleanup_partial_venv(venv_dir)

    error_output = result.stderr or result.stdout or "Unknown error"
    if len(error_output) > 500:
        error_output = error_output[:500] + "\n..."

    raise RuntimeError(
        "Failed to create virtual environment.\n\n"
        "You can install dependencies manually:\n"
        "  pip install keyring requests markdown\n\n"
        f"Error: {error_output}\n"
        f"Python: {python_exe}\n"
        f"Target: {venv_dir}"
    )


def install_packages(
    venv_dir: str,
    packages: List[str],
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """Install packages into the virtual environment.

    Args:
        venv_dir: Path to the venv directory.
        packages: List of pip package names to install.
        progress_callback: Optional callback for progress updates.

    Returns:
        Tuple of (success, message).
    """
    python_path = get_venv_python_path(venv_dir)
    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    usable, reason = venv_python_usable(venv_dir)
    if not usable:
        return (
            False,
            "Virtual environment Python is not usable. Re-run dependency "
            f"installation to recreate it.\nPython path: {python_path}\n"
            f"Error: {reason}",
        )

    pip_cmd = [
        python_path,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--disable-pip-version-check",
        "--prefer-binary",
    ] + packages

    if progress_callback:
        progress_callback(f"Installing: {', '.join(packages)}...")

    result = subprocess.run(
        pip_cmd,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        **kwargs,
    )

    if result.returncode == 0:
        if progress_callback:
            progress_callback("Packages installed successfully!")
        return True, "Packages installed successfully."

    error_output = result.stderr or result.stdout or "Unknown error"
    if len(error_output) > 1000:
        error_output = error_output[:500] + "\n...\n" + error_output[-500:]
    return False, f"pip install failed:\n{error_output}"


class DepsInstallWorker(QThread):
    """Worker thread for creating a venv and installing dependencies."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        """Execute venv creation and dependency installation."""
        try:
            if not python_runtime_supported():
                self.finished.emit(False, python_runtime_error())
                return

            venv_dir = get_venv_dir()

            # Step 1: Create venv if needed, or recreate stale broken venvs
            try:
                _ensure_usable_venv(
                    venv_dir,
                    progress_callback=lambda m: self.progress.emit(m),
                )
            except RuntimeError as e:
                self.finished.emit(False, str(e))
                return
            self.progress.emit("Virtual environment ready.")

            # Step 2: Verify pip
            self.progress.emit("Verifying pip...")
            python_path = get_venv_python_path(venv_dir)
            env = _get_clean_env()
            kwargs = _get_subprocess_kwargs()

            result = subprocess.run(
                [python_path, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                **kwargs,
            )
            if result.returncode != 0:
                self.finished.emit(
                    False,
                    "pip is not available in the virtual environment.\n"
                    "Please install dependencies manually:\n"
                    "pip install keyring requests markdown",
                )
                return
            self.progress.emit("pip ready.")

            # Step 3: Install missing packages
            missing = get_missing_packages()
            if not missing:
                self.finished.emit(
                    True,
                    "All dependencies are already installed.",
                )
                return

            self.progress.emit(f"Installing: {', '.join(missing)}...")
            success, message = install_packages(
                venv_dir,
                missing,
                progress_callback=lambda m: self.progress.emit(m),
            )
            if not success:
                self.finished.emit(False, message)
                return
            self.progress.emit("Packages installed.")

            # Step 4: Add venv to sys.path
            self.progress.emit("Configuring package paths...")
            ensure_venv_packages_available()

            # Step 5: Verify imports
            self.progress.emit("Verifying installations...")
            still_missing = get_missing_packages()

            if still_missing:
                self.finished.emit(
                    False,
                    f"The following packages could not be verified: "
                    f"{', '.join(still_missing)}.\n"
                    "You may need to restart QGIS for changes to take effect.",
                )
            else:
                self.progress.emit("All dependencies installed!")
                self.finished.emit(
                    True,
                    "All dependencies installed successfully!",
                )

        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Installation timed out after 10 minutes.")
        except Exception as e:
            self.finished.emit(False, f"Unexpected error: {str(e)}")


def setup_venv_and_install(
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """Create venv (if needed) and install missing packages.

    Args:
        progress_callback: Optional callback for progress updates.

    Returns:
        Tuple of (success, message).
    """
    try:
        if not python_runtime_supported():
            return False, python_runtime_error()

        venv_dir = get_venv_dir()

        # Create venv if it doesn't exist or recreate if broken
        try:
            _ensure_usable_venv(venv_dir, progress_callback)
        except RuntimeError as e:
            return False, str(e)

        if progress_callback:
            progress_callback("Virtual environment ready.")

        # Add to sys.path
        ensure_venv_packages_available()

        # Check what's missing
        missing = get_missing_packages()
        if not missing:
            return True, "All packages already installed!"

        # Install missing packages
        success, message = install_packages(venv_dir, missing, progress_callback)

        if success:
            # Verify installation
            ensure_venv_packages_available()
            still_missing = get_missing_packages()

            if still_missing:
                return False, (
                    f"Installation completed but packages not found: "
                    f"{', '.join(still_missing)}.\n"
                    "You may need to restart QGIS."
                )

            return True, "All packages installed successfully!"

        return False, message

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
