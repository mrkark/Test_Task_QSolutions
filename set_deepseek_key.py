#!/usr/bin/env python3
"""
DeepSeek API Key Setup Script.

Prompts the user for their DeepSeek API key (or accepts it via CLI argument)
and safely writes it to the local .env file. Ensures .env is added to .gitignore
so the key is never committed to Git, and enables Docker Compose to automatically
inject it into the container environment.

Usage:
    python set_deepseek_key.py [API_KEY]
    or run: set_deepseek_key.bat
"""
import os
import sys
import re

ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
GITIGNORE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".gitignore"))


def mask_key(key: str) -> str:
    """Returns a masked representation of the API key for safe display."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def ensure_gitignore():
    """Ensures .env is strictly ignored in .gitignore."""
    if not os.path.exists(GITIGNORE_FILE):
        with open(GITIGNORE_FILE, "w", encoding="utf-8") as f:
            f.write(".env\n*.env\n")
        return

    with open(GITIGNORE_FILE, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = [line.strip() for line in content.splitlines()]
    if ".env" not in lines:
        with open(GITIGNORE_FILE, "a", encoding="utf-8") as f:
            f.write("\n.env\n*.env\n")
        print("[*] Added .env to .gitignore for security.")


def save_api_key(api_key: str):
    """Saves DEEPSEEK_API_KEY into the .env file while preserving other variables."""
    api_key = api_key.strip().strip("'\"")
    if not api_key:
        print("[!] Error: Empty API key provided.", file=sys.stderr)
        sys.exit(1)

    existing_lines = []
    found = False

    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().startswith("DEEPSEEK_API_KEY="):
                    existing_lines.append(f"DEEPSEEK_API_KEY={api_key}\n")
                    found = True
                else:
                    existing_lines.append(line)

    if not found:
        existing_lines.append(f"DEEPSEEK_API_KEY={api_key}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(existing_lines)

    ensure_gitignore()

    print("=" * 68)
    print("  [SUCCESS] DeepSeek API Key successfully saved to .env!")
    print("=" * 68)
    print(f"  Key (masked):  {mask_key(api_key)}")
    print(f"  Target file:   {ENV_FILE}")
    print(f"  Git status:    Protected (.env is listed in .gitignore)")
    print(f"  Docker sync:   Docker Compose will automatically pass this key")
    print(f"                 into the container via environment variables.")
    print("=" * 68)


def main():
    if len(sys.argv) > 1:
        key = sys.argv[1]
    else:
        print("=" * 68)
        print("  QSolutions: Setup DeepSeek API Key")
        print("=" * 68)
        print("  Please paste your DeepSeek API Key below (e.g. sk-...)")
        try:
            key = input("  DEEPSEEK_API_KEY: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[!] Setup cancelled.")
            sys.exit(1)

    save_api_key(key)


if __name__ == "__main__":
    main()
