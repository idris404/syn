import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://syn:syn@localhost:5433/syn")
os.environ.setdefault("NCBI_EMAIL", "test@example.com")
