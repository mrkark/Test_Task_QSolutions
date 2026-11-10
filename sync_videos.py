#!/usr/bin/env python3
"""
Sync Local Recorded Videos into Docker PostgreSQL Database and Web Dashboard.

Scans the local ./video folder, uploads all recorded .webm videos, their F5 zoom
sidecars, and pre-rendered .zoomed.webm files to the Docker service (http://127.0.0.1:8000),
making them immediately playable on the web dashboard at http://localhost:8000/.
"""
import os
import sys
import argparse
from typing import List, Dict, Any
from apply_zoom import apply_zoom
from video_client import UploadVideo, GetVideoURL


def sync_all(server_url: str = "http://127.0.0.1:8000", video_dir: str = "video", auto_render_zoom: bool = True) -> List[Dict[str, Any]]:
    server_url = server_url.rstrip("/")
    abs_video_dir = os.path.abspath(video_dir)

    if not os.path.isdir(abs_video_dir):
        print(f"[!] Directory not found: {abs_video_dir}", file=sys.stderr)
        return []

    print("=" * 72)
    print("  QSolutions: Синхронизация записанных видео с базой данных Docker")
    print("=" * 72)
    print(f"  Каталог видео:  {abs_video_dir}")
    print(f"  Сервер Docker:  {server_url}")
    print(f"  Веб-дашборд:    {server_url}/")
    print("=" * 72)

    all_files = sorted(os.listdir(abs_video_dir))
    raw_videos = [
        f for f in all_files
        if f.endswith(".webm") and not f.endswith(".zoomed.webm") and not f.startswith("page@")
    ]

    if not raw_videos:
        print("[!] В папке ./video не найдено записей (.webm).")
        return []

    print(f"[*] Найдено записей для синхронизации: {len(raw_videos)}\n")

    results = []

    for idx, fname in enumerate(raw_videos, start=1):
        raw_path = os.path.join(abs_video_dir, fname)
        company_name = os.path.splitext(fname)[0]

        sidecar_path = f"{raw_path}.zoom.json"
        has_sidecar = os.path.exists(sidecar_path)

        zoomed_name = f"{company_name}.zoomed.webm"
        zoomed_path = os.path.join(abs_video_dir, zoomed_name)
        has_zoomed = os.path.exists(zoomed_path)

        print(f"[{idx}/{len(raw_videos)}] Синхронизация: {company_name}")
        print(f"    - Исходный файл: {fname} ({os.path.getsize(raw_path):,} байт)")
        print(f"    - Sidecar (F5 zoom): {'ЕСТЬ' if has_sidecar else 'нет'}")

        # If sidecar exists but zoomed video hasn't been rendered yet, render it
        if has_sidecar and not has_zoomed and auto_render_zoom:
            print("    - Рендеринг приближения (FFmpeg apply_zoom)...")
            code, msg = apply_zoom(
                video_path=raw_path,
                sidecar_path=sidecar_path,
                output_path=zoomed_path,
            )
            if code == 0 and os.path.exists(zoomed_path):
                has_zoomed = True
                print(f"    - Создано видео с зумом: {zoomed_name}")
            else:
                print(f"    - Ошибка рендеринга зума: {msg}")

        print(f"    - Видео с зумом: {'ЕСТЬ' if has_zoomed else 'нет'}")

        try:
            url = UploadVideo(
                server_url=server_url,
                video_path=raw_path,
                company_name=company_name,
                sidecar_path=sidecar_path if has_sidecar else None,
                processed_video_path=zoomed_path if has_zoomed else None,
                auto_process=True,
            )
            print(f"    -> [УСПЕХ] Загружено в БД! URL: {url}\n")
            results.append({
                "company_name": company_name,
                "status": "synced",
                "has_zoom": has_zoomed,
                "url": url,
            })
        except Exception as exc:
            print(f"    -> [ОШИБКА] Не удалось загрузить в Docker: {exc}\n", file=sys.stderr)
            results.append({
                "company_name": company_name,
                "status": "error",
                "error": str(exc),
            })

    print("=" * 72)
    print("  ИТОГИ СИНХРОНИЗАЦИИ:")
    print("=" * 72)
    for r in results:
        status_sym = "✅" if r.get("status") == "synced" else "❌"
        zoom_tag = "[Zoom Ready]" if r.get("has_zoom") else "[Standard]"
        print(f"  {status_sym} {r['company_name']:<30} {zoom_tag:<14} {r.get('url', r.get('error', ''))}")
    print("=" * 72)
    print(f"\n  Все видео доступны в веб-интерфейсе: {server_url}/")
    print("=" * 72 + "\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="Sync recorded videos into Docker PostgreSQL DB")
    parser.add_argument(
        "--server",
        type=str,
        default=os.environ.get("SERVER_URL", "http://127.0.0.1:8000"),
        help="Docker web service URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--video-dir",
        type=str,
        default="video",
        help="Local directory with videos (default: video)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Do not auto-render .zoomed.webm before uploading",
    )
    args = parser.parse_args()

    sync_all(
        server_url=args.server,
        video_dir=args.video_dir,
        auto_render_zoom=not args.no_render,
    )


if __name__ == "__main__":
    main()
