import os
import sys
import csv
import time
import argparse
from typing import List, Optional
import qscript
from apply_zoom import apply_zoom


def preview_video(video_url: str, view_seconds: float = 5.0):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            print(f"Previewing video in Chromium: {video_url}")
            page.goto(video_url)
            if view_seconds > 0:
                time.sleep(view_seconds)
            else:
                input(f"Previewing '{video_url}'. Press Enter to continue...")
            browser.close()
    except Exception as exc:
        print(f"Preview error for {video_url}: {exc}", file=sys.stderr)


def process_csv(
    csv_filepath: str = "input.csv",
    server_url: Optional[str] = None,
    view_seconds: float = 5.0,
    enable_zoom: bool = False,
    run_apply_zoom: bool = False,
) -> List[str]:
    if not os.path.exists(csv_filepath):
        print(f"Error: CSV file '{csv_filepath}' not found.", file=sys.stderr)
        sys.exit(1)

    saved_video_paths = []

    print(f"Reading tasks from '{csv_filepath}' (zoom={enable_zoom}, post-process={run_apply_zoom})...")
    with open(csv_filepath, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')

        for index, row in enumerate(reader, start=1):
            company = row.get("Company Name", f"Row_{index}")
            print(f"\n--- Processing row #{index}: {company} ---")

            video_path = qscript.CaptureVideo_Magento(
                url=row.get("URL", ""),
                company_name=row.get("Company Name", ""),
                language=row.get("Language", ""),
                country=row.get("Country", ""),
                postcode=row.get("Postcode", ""),
                city=row.get("City", ""),
                street=row.get("Street", ""),
                house_no=row.get("HouseNo", ""),
                enable_zoom=enable_zoom,
            )

            if video_path:
                print(f"Saved video path: {video_path}")
                final_path_to_upload = video_path

                sidecar_path = f"{video_path}.zoom.json"
                if run_apply_zoom and os.path.exists(sidecar_path):
                    print(f"Applying zoom post-processing locally for {company}...")
                    zoomed_path = f"{os.path.splitext(video_path)[0]}.zoomed.webm"
                    code, _ = apply_zoom(video_path=video_path, sidecar_path=sidecar_path, output_path=zoomed_path)
                    if code == 0 and os.path.exists(zoomed_path):
                        final_path_to_upload = zoomed_path

                saved_video_paths.append(final_path_to_upload)

                if server_url:
                    try:
                        from video_client import UploadVideo
                        print(f"Uploading video for {company} to {server_url}...")
                        video_url = UploadVideo(
                            server_url=server_url,
                            video_path=final_path_to_upload,
                            company_name=company,
                            sidecar_path=sidecar_path if os.path.exists(sidecar_path) else None,
                        )
                        print(f"Uploaded video URL: {video_url}")
                        preview_video(video_url, view_seconds)
                    except Exception as upload_err:
                        print(f"Upload/preview failed for {company}: {upload_err}", file=sys.stderr)
            else:
                print(f"Warning: Failed to capture video for {company}", file=sys.stderr)

    print(f"\nProcessing complete. Successfully generated {len(saved_video_paths)} video(s).")
    return saved_video_paths


def main():
    parser = argparse.ArgumentParser(description="CSV-driven browser automation and video recorder with zoom and server upload")
    parser.add_argument("csv_file", nargs="?", default="input.csv", help="Path to input CSV file (default: input.csv)")
    parser.add_argument("--server", type=str, default=None, help="Server URL for video upload and preview (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--view-seconds", type=float, default=5.0, help="Seconds to preview the video (>0: wait N seconds, 0: wait for Enter)")
    parser.add_argument("--zoom", action="store_true", help="Enable Camtasia-style zoom capture during recording")
    parser.add_argument("--apply-zoom", action="store_true", help="Locally run apply_zoom post-processing before uploading")
    parser.add_argument("--interactive", "--manual", action="store_true", help="Launch interactive recorder for human operator to test F5 zoom live")
    parser.add_argument("--url", type=str, default="https://duckduckgo.com", help="Initial URL for interactive recording")
    parser.add_argument("--name", type=str, default="Manual_Recording", help="Recording / Company name for interactive recording")

    args = parser.parse_args()

    if args.interactive:
        print("[*] Launching interactive manual recorder...")
        qscript.RecordInteractive(
            url=args.url,
            company_name=args.name,
            auto_apply_zoom=True,
            server_url=args.server,
        )
        return

    process_csv(
        csv_filepath=args.csv_file,
        server_url=args.server,
        view_seconds=args.view_seconds,
        enable_zoom=args.zoom,
        run_apply_zoom=args.apply_zoom,
    )


if __name__ == "__main__":
    main()
