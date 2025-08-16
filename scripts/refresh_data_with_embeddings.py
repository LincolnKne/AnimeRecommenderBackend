import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

def run_script(script_path):
    print(f"Running: {script_path}")
    result = subprocess.run([sys.executable, str(script_path)])
    if result.returncode != 0:
        print(f"Error running {script_path}")
        sys.exit(result.returncode)

def main():
    # 1. Run the data fetcher
    run_script(BASE_DIR / "scripts" / "mal_data_fetcher.py")

    # 2. Run the embedding generator
    run_script(Path(__file__).resolve().parent / "embed_generator.py")

    print("\n Data and embeddings updated successfully!")

if __name__ == "__main__":
    main()
