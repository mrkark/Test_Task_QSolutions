#!/usr/bin/env python3
"""
Interactive Screen Recorder for Human Operators (Camtasia-style F5 Zoom)
Allows a person to browse any webpage in a visible browser, move the mouse,
and press F5 (or click the floating [Zoom (F5)] button) to record zoom-in / zoom-out events.

When the browser is closed (or Enter is pressed in terminal):
- Saves video to video/<name>.webm
- Saves sidecar to video/<name>.webm.zoom.json
- Automatically renders smooth zoom with FFmpeg to video/<name>.zoomed.webm
- Uploads to the Docker web service (http://127.0.0.1:8000) if active
"""
import sys
import argparse
import qscript


def main():
    parser = argparse.ArgumentParser(
        description="Interactive browser screen recorder with live F5 zoom capture and post-processing"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://duckduckgo.com",
        help="Initial website URL to open (default: https://duckduckgo.com)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Operator_Zoom_Test",
        help="Company / recording name for output files (default: Operator_Zoom_Test)",
    )
    parser.add_argument(
        "--server",
        type=str,
        default="http://127.0.0.1:8000",
        help="Docker web service URL (default: http://127.0.0.1:8000, use '' to skip upload)",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Do not upload video to Docker server",
    )
    parser.add_argument(
        "--no-zoom",
        action="store_true",
        help="Skip automatic FFmpeg apply_zoom post-processing",
    )

    args = parser.parse_args()

    server = None if args.no_server or not args.server else args.server

    print("=" * 70)
    print("  QSolutions: Запуск интерактивной записи с поддержкой клавиши F5")
    print("=" * 70)
    print(f"  URL:              {args.url}")
    print(f"  Имя записи:       {args.name}")
    print(f"  Авто-зум (FFmpeg):{'Включен' if not args.no_zoom else 'Отключен'}")
    print(f"  Сервер загрузки:  {server or 'Локальное сохранение (без сервера)'}")
    print("=" * 70)

    result = qscript.RecordInteractive(
        url=args.url,
        company_name=args.name,
        auto_apply_zoom=not args.no_zoom,
        server_url=server,
    )

    if not result:
        print("\n[!] Запись была прервана или завершилась с ошибкой.", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  РЕЗУЛЬТАТЫ ЗАПИСИ:")
    print("=" * 70)
    print(f"  1. Исходное видео:       {result.get('video_path')}")
    if result.get("sidecar_path"):
        print(f"  2. Файл событий (sidecar): {result.get('sidecar_path')}")
        print(f"     Количество событий F5:  {result.get('events_count')}")
    else:
        print("  2. Файл событий (sidecar): не создан (события F5 не зафиксированы)")

    if result.get("zoomed_path"):
        print(f"  3. Видео с зумом FFmpeg: {result.get('zoomed_path')}")

    if result.get("uploaded_url"):
        print(f"  4. Веб-сервис (дашборд): {result.get('uploaded_url')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
