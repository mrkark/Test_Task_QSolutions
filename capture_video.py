import os
import sys
import csv
import qscript


def process_csv(csv_filepath: str = "input.csv") -> list[str]:
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
            else:
                print(f"Warning: Failed to capture video for {company}", file=sys.stderr)

    print(f"\nProcessing complete. Successfully generated {len(saved_video_paths)} video(s).")
    return saved_video_paths


def main():
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
    process_csv(csv_file)


if __name__ == "__main__":
    main()
