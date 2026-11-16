import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = (
        "postgresql://postgres.bkxapdsnpucrqptupzbz@"
        "aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    )
