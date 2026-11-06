import os
import sys
import csv
import time
import argparse
import qscript


def start_background_server(port: int = 8000):
    import threading
    from werkzeug.serving import make_server
    import web_service

    server = make_server("127.0.0.1", port, web_service.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


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


def process_csv(csv_filepath: str = "input.csv", server_url: str = None, view_seconds: float = 5.0) -> list[str]:
    if not os.path.exists(csv_filepath):
        print(f"Error: CSV file '{csv_filepath}' not found.", file=sys.stderr)
        sys.exit(1)

    saved_video_paths = []

    print(f"Reading tasks from '{csv_filepath}'...")
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
            )

            if video_path:
                print(f"Saved video path: {video_path}")
                saved_video_paths.append(video_path)

                if server_url:
                    try:
                        from video_client import UploadVideo
                        print(f"Uploading video for {company} to {server_url}...")
                        video_url = UploadVideo(server_url, video_path, company)
                        print(f"Uploaded video URL: {video_url}")
                        preview_video(video_url, view_seconds)
                    except Exception as upload_err:
                        print(f"Upload/preview failed for {company}: {upload_err}", file=sys.stderr)
            else:
                print(f"Warning: Failed to capture video for {company}", file=sys.stderr)

    print(f"\nProcessing complete. Successfully generated {len(saved_video_paths)} video(s).")
    return saved_video_paths


def main():
    parser = argparse.ArgumentParser(description="CSV-driven browser automation and video recorder with server upload")
    parser.add_argument("csv_file", nargs="?", default="input.csv", help="Path to input CSV file (default: input.csv)")
    parser.add_argument("--server", type=str, default=None, help="Server URL for video upload and preview (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--auto-server", action="store_true", help="Start local web service in background, upload and preview recorded videos")
    parser.add_argument("--view-seconds", type=float, default=5.0, help="Seconds to preview the video (>0: wait N seconds, 0: wait for Enter)")

    args = parser.parse_args()

    server_url = args.server
    server_handle = None

    if args.auto_server:
        server_handle, server_url = start_background_server(8000)
        print(f"Background web service started at {server_url}")

    try:
        process_csv(csv_filepath=args.csv_file, server_url=server_url, view_seconds=args.view_seconds)
    finally:
        if server_handle:
            server_handle.shutdown()


if __name__ == "__main__":
    main()
