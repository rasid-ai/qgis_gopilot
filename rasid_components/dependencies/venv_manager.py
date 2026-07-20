# -*- coding: utf-8 -*-
"""
Virtual Environment Manager for GoPilot Plugin
Manages an isolated venv for plugin dependencies to avoid polluting QGIS Python.
"""

import os
import sys
# subprocess is used only to invoke a Python interpreter resolved from the
# system (sys.executable / sys._base_executable / PATH) with fixed, hard-coded
# argument lists ("-m", "pip", "venv", "ensurepip", ...). No argument is ever a
# shell string and shell=True is never used, so there is no command-injection
# surface. The Bandit B404/B603 findings on this module are therefore false
# positives and are suppressed inline with justification at each call site.
import subprocess  # nosec B404
import shutil
import importlib.util
import importlib.metadata
import re
from pathlib import Path
from typing import List, Tuple, Optional, Callable

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..logger import debug_print


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
    """Check if the plugin's package directory is present.

    Packages are installed with the BASE interpreter via ``pip --target`` (the
    venv's own pip is unreliable on QGIS Windows builds), so a populated
    site-packages directory is sufficient — even if the venv interpreter is
    missing or non-functional.

    Args:
        venv_dir: Path to the venv directory. Defaults to get_venv_dir().

    Returns:
        True if the directory exists and has either a Python executable or a
        site-packages directory.
    """
    if venv_dir is None:
        venv_dir = get_venv_dir()
    if not os.path.isdir(venv_dir):
        return False
    python_path = get_venv_python_path(venv_dir)
    return os.path.isfile(python_path) or os.path.isdir(get_venv_site_packages(venv_dir))


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
    site_packages = get_venv_site_packages()
    if not os.path.isdir(site_packages):
        return False
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
    """Check whether each required package is importable.

    A package counts as satisfied if it is importable from anywhere on
    sys.path — the plugin's own target folder (added here) OR QGIS's own Python
    (e.g. ``requests`` usually ships with QGIS). This avoids reinstalling what
    QGIS already provides, and avoids the ``pip --target`` "already satisfied"
    skip from ever causing a re-prompt loop.

    Returns:
        List of dicts with keys: name, pip_name, installed, version, error.
    """
    required_packages = get_required_packages()

    # Make the plugin's target folder importable before probing.
    _add_venv_to_path()

    results = []
    for import_name, pip_name in required_packages:
        discoverable, err = _dependency_discoverable(import_name)
        results.append({
            "name": import_name,
            "pip_name": pip_name,
            "installed": discoverable,
            "version": _dependency_version(pip_name) if discoverable else None,
            "error": None if discoverable else (err or "not importable"),
        })
    return results


def all_dependencies_met() -> bool:
    """Return True if every required package is importable.

    Returns:
        True if all dependencies can be imported (from the target folder or
        from QGIS's own Python).
    """
    _add_venv_to_path()
    required_packages = get_required_packages()
    return all(
        _dependency_discoverable(import_name)[0]
        for import_name, _pip_name in required_packages
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
    # IMPORTANT: preserve PYTHONHOME / PYTHONPATH. On Windows (OSGeo4W) the
    # bundled QGIS interpreter relies on them to locate its own standard library
    # and site-packages (where pip lives). Stripping them makes `python -m pip`
    # fail with "No module named pip" / "Could not find platform independent
    # libraries" — which is exactly why running pip from the OSGeo4W Shell works
    # but a stripped subprocess does not. Only drop VIRTUAL_ENV so pip does not
    # think it is inside some other virtual environment.
    env.pop("VIRTUAL_ENV", None)
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


def _ensure_base_pip(
    python_exe: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Ensure the BASE interpreter can run pip, bootstrapping it if necessary.

    QGIS almost always ships pip with its Python, so the first check usually
    passes. If not, we try ``ensurepip`` on the base interpreter (which — unlike
    a freshly created venv — can locate its own standard library).

    Returns:
        Tuple of (ok, error_message). error_message is empty when ok is True.
    """
    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    def _pip_ok() -> bool:
        try:
            r = subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
                [python_exe, "-m", "pip", "--version"],
                capture_output=True, text=True, timeout=60, env=env, **kwargs,
            )
            return r.returncode == 0
        except Exception:
            return False

    if _pip_ok():
        return True, ""

    if progress_callback:
        progress_callback("Bootstrapping pip (ensurepip)...")
    try:
        subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
            [python_exe, "-m", "ensurepip", "--upgrade"],
            capture_output=True, text=True, timeout=180, env=env, **kwargs,
        )
    except Exception as exc:
        # Best-effort bootstrap; the _pip_ok() re-check below decides success.
        debug_print(f"[venv_manager] ensurepip bootstrap failed: {exc}")

    if _pip_ok():
        return True, ""

    return False, (
        "pip is not available in the QGIS Python interpreter and could not be "
        "bootstrapped automatically.\n\n"
        f"Interpreter: {python_exe}\n\n"
        "Install pip manually, then retry:\n"
        "  - Windows: open the OSGeo4W Shell and run\n"
        f'      python -m ensurepip --upgrade\n'
        "  - Linux: run\n"
        f'      "{python_exe}" -m ensurepip --upgrade'
    )


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
        result = subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
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
    subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
        [python_path, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        **kwargs,
    )

    # Verify pip works
    result = subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
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
    site_packages = get_venv_site_packages(venv_dir)
    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    # Best effort: create a venv WITHOUT pip. Creating it *with* pip runs
    # ensurepip inside the fresh venv, which fails on some QGIS Windows builds
    # ("Could not find platform independent libraries <prefix>"). We never use
    # the venv's own pip anyway — packages are installed with the base
    # interpreter via `pip --target` — so `--without-pip` is all we need.
    try:
        python_exe = _find_python_executable()
        if progress_callback:
            progress_callback("Creating package environment...")
        result = subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
            [python_exe, "-m", "venv", "--without-pip", venv_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            **kwargs,
        )
        if result.returncode == 0:
            if progress_callback:
                progress_callback("Package environment ready.")
        elif progress_callback:
            progress_callback(
                "venv unavailable; falling back to a plain package folder."
            )
    except Exception as exc:
        # No interpreter, or venv module unavailable — fall back to a plain dir.
        if progress_callback:
            progress_callback(
                f"venv unavailable ({exc}); using a plain package folder."
            )

    # Guarantee the target folder exists even if `venv` did not run or failed.
    # A plain directory on sys.path is enough for `pip --target` + imports.
    os.makedirs(site_packages, exist_ok=True)
    return get_venv_python_path(venv_dir)


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
    site_packages = get_venv_site_packages(venv_dir)
    os.makedirs(site_packages, exist_ok=True)
    env = _get_clean_env()
    kwargs = _get_subprocess_kwargs()

    # Install with the BASE interpreter's pip into the target folder. This
    # sidesteps the venv's own pip, which does not exist (created with
    # --without-pip) and is unreliable on QGIS Windows anyway.
    try:
        python_exe = _find_python_executable()
    except RuntimeError as exc:
        return False, str(exc)

    ok, reason = _ensure_base_pip(python_exe, progress_callback)
    if not ok:
        return False, reason

    pip_cmd = [
        python_exe,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-cache-dir",
        "--disable-pip-version-check",
        "--prefer-binary",
        "--target",
        site_packages,
    ] + packages

    if progress_callback:
        progress_callback(f"Installing: {', '.join(packages)}...")

    result = subprocess.run(  # nosec B603 - fixed args, no shell, trusted interpreter
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
        """Create the package directory and install dependencies into it."""
        try:
            if not python_runtime_supported():
                self.finished.emit(False, python_runtime_error())
                return

            venv_dir = get_venv_dir()

            # Step 1: prepare the package directory (venv --without-pip, or a
            # plain folder if venv is not possible on this platform/build).
            self.progress.emit("Preparing package environment...")
            try:
                create_venv(
                    venv_dir,
                    progress_callback=lambda m: self.progress.emit(m),
                )
            except RuntimeError as e:
                self.finished.emit(False, str(e))
                return

            # Step 2: install only the packages that are not already importable
            # (QGIS ships some, e.g. requests). Install them into the target
            # folder with the base interpreter's pip (--target).
            ensure_venv_packages_available()
            missing = get_missing_packages()
            if not missing:
                self.progress.emit("All dependencies already available.")
                self.finished.emit(True, "All dependencies are already available.")
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

            # Step 3: put the folder on sys.path and verify imports resolve.
            self.progress.emit("Configuring package paths...")
            ensure_venv_packages_available()

            self.progress.emit("Verifying installation...")
            still_missing = get_missing_packages()
            if still_missing:
                self.finished.emit(
                    False,
                    "These packages could not be verified after install: "
                    f"{', '.join(still_missing)}.\n"
                    "Please restart QGIS and try again.",
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

        # Prepare the package directory (venv --without-pip, or a plain folder).
        try:
            create_venv(venv_dir, progress_callback)
        except RuntimeError as e:
            return False, str(e)

        # Install only the packages that are not already importable, into the
        # target folder via the base interpreter's pip.
        ensure_venv_packages_available()
        missing = get_missing_packages()
        if not missing:
            return True, "All packages already installed!"
        success, message = install_packages(venv_dir, missing, progress_callback)
        if not success:
            return False, message

        # Verify installation.
        ensure_venv_packages_available()
        still_missing = get_missing_packages()
        if still_missing:
            return False, (
                f"Installation completed but packages not found: "
                f"{', '.join(still_missing)}.\n"
                "You may need to restart QGIS."
            )
        return True, "All packages installed successfully!"

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
