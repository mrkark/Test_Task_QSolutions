import os
import requests


def UploadVideo(server_url: str, video_path: str, company_name: str) -> str:
    """Uploads a video file to the server and returns its URL."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    filename = os.path.basename(video_path)
    url = f"{server_url.rstrip('/')}/upload"

    with open(video_path, "rb") as video_file:
        files = {"file": (filename, video_file, "video/webm")}
        data = {"company_name": company_name}
        response = requests.post(url, files=files, data=data, timeout=60)

    response.raise_for_status()
    result = response.json()
    return result["video_url"]


def GetVideoURL(server_url: str, company_name: str) -> str:
    """Returns the video URL for the given company name."""
    url = f"{server_url.rstrip('/')}/get_video_url"
    response = requests.get(url, params={"company_name": company_name}, timeout=15)
    response.raise_for_status()
    result = response.json()
    return result["video_url"]
