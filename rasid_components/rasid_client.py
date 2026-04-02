# API session / token management
import os
import tempfile
import requests

TIMEOUT = 15

class RasidClient:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://api.rasid.ai/api/"
        # Set Referer so Django CSRF doesn't reject POST requests
        self.session.headers["Referer"] = self.base_url

    def fetch_csrf_token(self):
        """Fetch a fresh CSRF token from the dedicated endpoint."""
        try:
            response = self.session.get(
                self.base_url + "auth/csrf/",
                timeout=TIMEOUT
            )
            response.raise_for_status()
            # Extract token from cookie and set header
            csrf = self.session.cookies.get("csrftoken_v2")
            if csrf:
                self.session.headers["X-CSRFToken"] = csrf
            return True
        except Exception:
            return False

    def _ensure_csrf(self, fetch_if_missing=True):
        """
        Ensure CSRF token is set in request headers.

        Args:
            fetch_if_missing: If True, fetch a fresh token from API if not in cookies.
                             If False, only use existing cookie.
        """
        csrf = self.session.cookies.get("csrftoken_v2")
        if csrf:
            # Token exists, set it in headers
            self.session.headers["X-CSRFToken"] = csrf
        elif fetch_if_missing:
            # Token missing, fetch a fresh one from API
            self.fetch_csrf_token()

    def login(self, username_or_email, password):
        # Ensure we have a fresh CSRF token before login
        self._ensure_csrf(fetch_if_missing=True)

        url = self.base_url + "auth/login/"
        response = self.session.post(
            url,
            json={"email_or_username": username_or_email, "password": password},
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            self._ensure_csrf(fetch_if_missing=True)
            return True
        else:
            detail = response.json().get("detail", "Login failed")
            raise Exception(detail)

    def save_cookies(self):
        """Save session cookies to QSettings."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        sessionid = self.session.cookies.get("sessionid_v2", "")
        csrftoken = self.session.cookies.get("csrftoken_v2", "")
        if sessionid:
            settings.setValue("rasid_plugin/sessionid", sessionid)
        if csrftoken:
            settings.setValue("rasid_plugin/csrftoken", csrftoken)

    def load_cookies(self):
        """Load session cookies from QSettings."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        sessionid = settings.value("rasid_plugin/sessionid", "")
        csrftoken = settings.value("rasid_plugin/csrftoken", "")
        if sessionid:
            self.session.cookies.set("sessionid_v2", sessionid)
        if csrftoken:
            self.session.cookies.set("csrftoken_v2", csrftoken)
            self.session.headers["X-CSRFToken"] = csrftoken
        return bool(sessionid and csrftoken)

    def clear_cookies(self):
        """Clear cookies from session and QSettings."""
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        settings.remove("rasid_plugin/sessionid")
        settings.remove("rasid_plugin/csrftoken")
        self.session.cookies.clear()

    def is_authenticated(self):
        """Test if current session is valid."""
        try:
            self.get_profile()
            return True
        except:
            return False

    def logout(self):
        """Logout and invalidate session on server."""
        self._ensure_csrf(fetch_if_missing=True)
        try:
            response = self.session.post(
                self.base_url + "auth/logout/",
                timeout=TIMEOUT
            )
            response.raise_for_status()
        except Exception:
            # Best effort - still clear session locally even if API call fails
            pass
        finally:
            self.clear_cookies()

    def get_profile(self):
        response = self.session.get(
            self.base_url + "accounts/profile/",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def get_user_projects(self, hidden=False):
        params = {"hidden": str(hidden).lower()}
        response = self.session.get(
            self.base_url + "projects/", params=params, timeout=TIMEOUT
        )
        if response.status_code == 200:
            return response.json()
        else:
            detail = response.json().get("detail", "Failed to fetch projects")
            raise Exception(detail)

    def get_solutions(self):
        response = self.session.get(
            self.base_url + "solutions/", timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def get_processes(self, project_slug):
        response = self.session.get(
            self.base_url + "processes/",
            params={"project": project_slug},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
        
    def create_project(self, solution_slug, title, tags=None):
        """
        Create a new project.
        
        Args:
            solution_slug: Slug of the solution to use
            title: Title for the new project
            tags: Optional list of tag IDs
        """
        self._ensure_csrf(fetch_if_missing=True)
        payload = {"solution_slug": solution_slug, "title": title}
        if tags:
            payload["tags"] = tags
        response = self.session.post(
            self.base_url + "projects-create/",
            json=payload,
            timeout=TIMEOUT,
        )
        if response.status_code == 201:
            return response.json()
        else:
            detail = response.json() if response.content else {"detail": "Failed to create project"}
            if isinstance(detail, dict):
                detail = detail.get("detail", str(detail))
            raise Exception(str(detail))

    def get_process_config(self, project_slug):
        response = self.session.get(
            self.base_url + f"projects/{project_slug}/process-config/",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def search_catalogue(self, payload):
        """
        Search Sentinel catalogue.

        Args:
            payload: Dict with keys:
                - bbox: string "[min_lon, min_lat, max_lon, max_lat]" or list
                - sentinel_start_date: string "YYYY-MM-DD"
                - sentinel_end_date: string "YYYY-MM-DD"
                - sentinel_data_collection: string (sentinel-2-l2a, sentinel-2-l1c, sentinel-1-grd)
                - sentinel_sort_by: string (optional: "---", "leastcc")
        """
        import json

        self._ensure_csrf(fetch_if_missing=True)

        # Convert bbox list to JSON string if needed
        if isinstance(payload.get("bbox"), list):
            payload = payload.copy()
            payload["bbox"] = json.dumps(payload["bbox"])

        # Build workspace URL from base URL (remove /api/ suffix)
        base = self.base_url.replace("/api/", "/")
        url = base + "workspace/sentinel2_catalogue/"

        response = self.session.post(
            url,
            data=payload,  # Use form data, not JSON
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_process(self, project_slug, payload, files=None):
        """
        Create a new process under a project.
        
        Args:
            project_slug: Project slug
            payload: Dict with process creation data (see CreateProcessInputSerializer)
            files: Optional dict of files (e.g., {'upload_raster': file_handle})
        """
        self._ensure_csrf(fetch_if_missing=True)
        
        # When sending files, we must use multipart/form-data (data=, not json=)
        # Temporarily remove Content-Type header to let requests set it automatically
        headers = {}
        if files:
            # Let requests set Content-Type with proper boundary
            if "Content-Type" in self.session.headers:
                headers["Content-Type"] = None
        
        response = self.session.post(
            self.base_url + f"projects/{project_slug}/processes/",
            data=payload,
            files=files,
            headers=headers or None,
            timeout=120 if files else TIMEOUT,
        )
        if response.status_code == 201:
            return response.json()
        else:
            detail = response.json() if response.content else {"detail": "Failed"}
            if isinstance(detail, dict):
                detail = detail.get("detail", str(detail))
            raise Exception(str(detail))

    def hide_process(self, project_slug, process_id):
        """Hide a process (soft delete)."""
        self._ensure_csrf(fetch_if_missing=True)
        response = self.session.post(
            self.base_url + f"projects/{project_slug}/processes/{process_id}/hide/",
            json={},  # Send empty JSON body
            timeout=TIMEOUT,
        )
        # FIXED: Handle both 200 and 204 responses without trying to parse empty body
        if response.status_code in (200, 204):
            return True
        else:
            detail = "Failed to hide process"
            if response.content:
                try:
                    detail = response.json().get("detail", str(response.json()))
                except Exception:
                    detail = response.text
            raise Exception(detail)

    def hide_project(self, project_slug):
        """Hide a project (soft delete)."""
        self._ensure_csrf(fetch_if_missing=True)
        response = self.session.post(
            self.base_url + f"projects/{project_slug}/hide/",
            json={},  # Send empty JSON body
            timeout=TIMEOUT,
        )
        # FIXED: Handle both 200 and 204 responses without trying to parse empty body
        if response.status_code in (200, 204):
            return True
        else:
            detail = "Failed to hide project"
            if response.content:
                try:
                    detail = response.json().get("detail", str(response.json()))
                except Exception:
                    detail = response.text
            raise Exception(detail)

    def get_process_detail(self, process_id):
        """Get detailed information about a process."""
        response = self.session.get(
            self.base_url + "process/detail/",
            params={"id": process_id},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    
    def submit_feedback(self, feedback_data):
        """
        Submit user feedback to the API.

        Args:
            feedback_data: Dict with keys:
                - message: string (required) - The feedback message
                - rating: integer (optional) - Rating 0-5, default 0
                - process: integer (optional) - Process ID to link feedback to
                - feedback_infos: dict (optional) - Additional metadata

        Returns:
            dict: Created feedback object with id, system_registration_date, etc.
        """
        self._ensure_csrf(fetch_if_missing=True)

        response = self.session.post(
            self.base_url + "accounts/feedback/",
            json=feedback_data,
            timeout=TIMEOUT,
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            # Try to parse error response
            detail = "Failed to submit feedback"
            if response.content:
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        detail = error_data.get("detail", str(error_data))
                    else:
                        detail = str(error_data)
                except Exception:
                    # If JSON parsing fails, use raw text
                    detail = f"Server error ({response.status_code}): {response.text[:200]}"
            raise Exception(str(detail))
        
    def download_file(self, url, dest_dir=None):
        """
        Download a file from the API and save it locally with path traversal protection.

        This function implements security measures to prevent path traversal attacks:
        - Extracts only the basename from URL to strip directory components
        - Blocks dangerous filenames (., .., or containing path separators)
        - Validates that the final resolved path stays within the destination directory
        - Uses os.path.realpath() to resolve any remaining path traversal attempts

        These protections prevent malicious URLs from writing files outside the intended
        directory, which could lead to:
        - System file corruption
        - Arbitrary code execution via startup folders
        - Overwriting configuration files
        - Privilege escalation attacks

        Args:
            url: URL to download from (absolute or relative to BASE_URL)
            dest_dir: Destination directory (defaults to temp/rasid_downloads)

        Returns:
            str: Local file path where the file was saved

        Raises:
            Exception: If URL is invalid, download fails, or path traversal detected
        """
        if not url:
            raise Exception("No file URL provided")
        if url.startswith("/"):
            url = self.base_url.rstrip("/api/") + url  # Handle base URL correctly

        response = self.session.get(url, timeout=60, stream=True)
        response.raise_for_status()

        # SECURITY: Extract filename from URL
        filename = url.rsplit("/", 1)[-1].split("?")[0] or "download"

        # SECURITY: Use basename to strip any directory components (../, ./, etc.)
        filename = os.path.basename(filename)

        # SECURITY: Block dangerous filenames that could still cause issues
        if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
            filename = "download"

        # SECURITY: Additional check - block filenames starting with dots (hidden files)
        # that might overwrite config files
        if filename.startswith("."):
            filename = "download" + filename

        if dest_dir is None:
            dest_dir = os.path.join(tempfile.gettempdir(), "rasid_downloads")
        os.makedirs(dest_dir, exist_ok=True)

        filepath = os.path.join(dest_dir, filename)

        # SECURITY: Final validation - ensure resolved path is within destination
        # This catches any edge cases or OS-specific path traversal methods
        real_dest = os.path.realpath(dest_dir)
        real_path = os.path.realpath(filepath)

        if not real_path.startswith(real_dest + os.sep) and real_path != real_dest:
            raise Exception(
                f"Security: Path traversal attempt detected. "
                f"File would be written outside download directory."
            )

        # Safe to write file
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return filepath