import os
from typing import Optional, Union, Dict, Any
import requests


def UploadVideo(
    server_url: str,
    video_path: str,
    company_name: str,
    sidecar_path: Optional[str] = None,
    processed_video_path: Optional[str] = None,
    auto_process: bool = True,
) -> str:
    """Uploads a video file (optional zoom sidecar, and optional pre-rendered zoomed video) to the server and returns its URL."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    filename = os.path.basename(video_path)
    url = f"{server_url.rstrip('/')}/upload"

    # Auto-detect sidecar if not explicitly passed
    if sidecar_path is None:
        candidate = f"{video_path}.zoom.json"
        if os.path.exists(candidate):
            sidecar_path = candidate

    # Auto-detect pre-rendered zoomed video if not explicitly passed
    if processed_video_path is None:
        base, ext = os.path.splitext(video_path)
        candidate_proc = f"{base}.zoomed{ext or '.webm'}"
        if os.path.exists(candidate_proc):
            processed_video_path = candidate_proc

    files: Dict[str, Any] = {}
    sidecar_file_handle = None
    proc_file_handle = None

    try:
        with open(video_path, "rb") as video_file:
            files["file"] = (filename, video_file, "video/webm")

            if sidecar_path and os.path.exists(sidecar_path):
                sidecar_file_handle = open(sidecar_path, "rb")
                files["sidecar"] = (os.path.basename(sidecar_path), sidecar_file_handle, "application/json")

            if processed_video_path and os.path.exists(processed_video_path):
                proc_file_handle = open(processed_video_path, "rb")
                files["processed_file"] = (os.path.basename(processed_video_path), proc_file_handle, "video/webm")

            data = {
                "company_name": company_name,
                "auto_process": "1" if auto_process else "0",
            }
            response = requests.post(url, files=files, data=data, timeout=120)
    finally:
        if sidecar_file_handle:
            sidecar_file_handle.close()
        if proc_file_handle:
            proc_file_handle.close()

    response.raise_for_status()
    result = response.json()
    return result.get("processed_video_url") or result["video_url"]


def SyncVideos(server_url: str = "http://127.0.0.1:8000", video_dir: str = "video") -> list:
    """Scans local video_dir and uploads all recorded videos (and sidecars/zoomed videos) to Docker."""
    if not os.path.exists(video_dir):
        print(f"[SyncVideos] Directory not found: {video_dir}")
        return []

    uploaded = []
    for item in sorted(os.listdir(video_dir)):
        if not item.endswith(".webm") or item.endswith(".zoomed.webm"):
            continue

        raw_path = os.path.join(video_dir, item)
        company_name = os.path.splitext(item)[0]
        sidecar_path = f"{raw_path}.zoom.json"
        if not os.path.exists(sidecar_path):
            sidecar_path = None

        base, ext = os.path.splitext(raw_path)
        zoomed_path = f"{base}.zoomed{ext or '.webm'}"
        if not os.path.exists(zoomed_path):
            zoomed_path = None

        print(f"[SyncVideos] Uploading '{company_name}'...")
        try:
            url = UploadVideo(
                server_url=server_url,
                video_path=raw_path,
                company_name=company_name,
                sidecar_path=sidecar_path,
                processed_video_path=zoomed_path,
                auto_process=True,
            )
            print(f"[SyncVideos] -> OK: {url}")
            uploaded.append({"company_name": company_name, "url": url})
        except Exception as err:
            print(f"[SyncVideos] -> Error uploading {company_name}: {err}")

    return uploaded


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
