"""يجعل حقيبة الأدوات (harness.py) مستوردةً داخل حزمة hardening."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
