from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
LOG_DIR = ROOT / "logs"

PRICES_PATH = DATA_DIR / "prices.json"
RULES_PATH = DATA_DIR / "rules.txt"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"
