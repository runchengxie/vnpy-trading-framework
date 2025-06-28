import os
from pathlib import Path
from typing import Set

# --- CONFIGURATION ---
# This section defines the script's behavior.

# 1. Project Root Directory
# ... (rest of configuration is the same) ...
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    PROJECT_ROOT = Path.cwd()

# 2. Output File
OUTPUT_FILENAME = "full_code_text.txt"

# 3. Excluded Directories
EXCLUDE_DIRS: Set[str] = {
    '.git', '__pycache__', 'patf_trading_framework.egg-info', 'cache',
    'output', '.vscode', '.idea', 'venv', '.venv', 'env', 'build', 'dist', 'logs',
}

# 4. Excluded File Extensions
EXCLUDE_EXTS: Set[str] = {
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.png', '.jpg', '.jpeg', '.gif',
    '.ico', '.svg', '.parquet', '.arrow', '.feather', '.csv', '.json',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.db', '.sqlite3', '.pdf',
    '.docx', '.xlsx',
}

# 5. Excluded Specific Files
EXCLUDE_FILES: Set[str] = {
    # CRITICAL: Exclude the output file itself to prevent it from being
    # included in subsequent runs. This is a key safeguard against
    # the output file growing infinitely.
    OUTPUT_FILENAME,
    
    '.DS_Store',     # macOS system file
    'Thumbs.db',     # Windows system file
    '.env',          # Environment variables file
}


def is_likely_text_file(filepath: Path) -> bool:
    """Checks if a file is likely to be a text file."""
    if filepath.suffix.lower() in EXCLUDE_EXTS:
        return False
    try:
        with open(filepath, 'rb') as f:
            return b'\0' not in f.read(1024)
    except (IOError, PermissionError):
        return False


def combine_project_files() -> None:
    """
    Scans the project directory and combines all text files into a single output file.
    """
    output_filepath = PROJECT_ROOT / OUTPUT_FILENAME

    print(f"Project root identified as: {PROJECT_ROOT}")
    print(f"Output will be saved to: {output_filepath}\n")

    files_processed_count = 0
    files_skipped_count = 0

    try:
        # CRITICAL: The file is opened in 'w' (write) mode.
        # This means the file is TRUNCATED (emptied) before anything is written
        # to it. This ensures that each run creates a fresh output file,
        # preventing it from growing with each execution.
        with open(output_filepath, 'w', encoding='utf-8', errors='ignore') as outfile:
            outfile.write("Here are the full project files, structured with relative paths.\n\n")

            for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

                for filename in sorted(filenames):
                    # This check uses the EXCLUDE_FILES set defined above.
                    if filename in EXCLUDE_FILES:
                        continue

                    filepath = Path(dirpath) / filename
                    relative_path_str = filepath.relative_to(PROJECT_ROOT).as_posix()

                    if not is_likely_text_file(filepath):
                        print(f"  - Skipping binary/excluded file: {relative_path_str}")
                        files_skipped_count += 1
                        continue

                    print(f"  + Processing: {relative_path_str}")
                    files_processed_count += 1
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as infile:
                            content = infile.read()
                        
                        outfile.write(f"<{relative_path_str}>\n")
                        outfile.write(content.strip())
                        outfile.write(f"\n</{relative_path_str}>\n\n")
                        
                    except Exception as e:
                        print(f"    [ERROR] Could not read file {relative_path_str}: {e}")
                        files_skipped_count += 1

        print("\n--- Summary ---")
        print(f"Successfully processed {files_processed_count} files.")
        print(f"Skipped {files_skipped_count} binary, excluded, or unreadable files.")
        print(f"Combined output saved to: {output_filepath}")

    except IOError as e:
        print(f"\n[FATAL ERROR] Could not write to output file {output_filepath}: {e}")
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred: {e}")


if __name__ == "__main__":
    combine_project_files()