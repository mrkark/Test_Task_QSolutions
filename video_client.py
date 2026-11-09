import os
from typing import Optional, Union, Dict, Any
import requests


def UploadVideo(
    server_url: str,
    video_path: str,
    company_name: str,
    sidecar_path: Optional[str] = None,
    auto_process: bool = True,
) -> str:
    """Uploads a video file (and optional zoom sidecar) to the server and returns its URL."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    filename = os.path.basename(video_path)
    url = f"{server_url.rstrip('/')}/upload"

    # Auto-detect sidecar if not explicitly passed
    if sidecar_path is None:
        candidate = f"{video_path}.zoom.json"
        if os.path.exists(candidate):
            sidecar_path = candidate

    files: Dict[str, Any] = {}
    sidecar_file_handle = None

    try:
        with open(video_path, "rb") as video_file:
            files["file"] = (filename, video_file, "video/webm")

            if sidecar_path and os.path.exists(sidecar_path):
                sidecar_file_handle = open(sidecar_path, "rb")
                files["sidecar"] = (os.path.basename(sidecar_path), sidecar_file_handle, "application/json")

            data = {
                "company_name": company_name,
                "auto_process": "1" if auto_process else "0",
            }
            response = requests.post(url, files=files, data=data, timeout=120)
    finally:
        if sidecar_file_handle:
            sidecar_file_handle.close()

    response.raise_for_status()
    result = response.json()
    return result.get("processed_video_url") or result["video_url"]


def ProcessVideo(server_url: str, video_id_or_company: Union[int, str], sidecar_path: Optional[str] = None) -> str:
    """Triggers zoom post-processing on the server for a video ID or company name."""
    url = f"{server_url.rstrip('/')}/process"

    files = {}
    sidecar_file_handle = None
    try:
        if sidecar_path and os.path.exists(sidecar_path):
            sidecar_file_handle = open(sidecar_path, "rb")
            files["sidecar"] = (os.path.basename(sidecar_path), sidecar_file_handle, "application/json")

        if isinstance(video_id_or_company, int) or (isinstance(video_id_or_company, str) and video_id_or_company.isdigit()):
            job_url = f"{server_url.rstrip('/')}/jobs/{video_id_or_company}/process"
            response = requests.post(job_url, files=files if files else None, timeout=120)
        else:
            data = {"company_name": str(video_id_or_company)}
            response = requests.post(url, data=data, files=files if files else None, timeout=120)
    finally:
        if sidecar_file_handle:
            sidecar_file_handle.close()

    response.raise_for_status()
    result = response.json()
    return result.get("processed_video_url") or result.get("video_url")


def GetVideoURL(server_url: str, company_name: str, get_processed: bool = False) -> str:
    """Returns the video URL for the given company name (or processed_video_url if requested)."""
    url = f"{server_url.rstrip('/')}/get_video_url"
    response = requests.get(url, params={"company_name": company_name}, timeout=15)
    response.raise_for_status()
    result = response.json()
    if get_processed and result.get("processed_video_url"):
        return result["processed_video_url"]
    return result["video_url"]
