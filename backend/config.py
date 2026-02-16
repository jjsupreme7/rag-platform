import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    CLAUDE_SIMPLE_MODEL: str = os.getenv("CLAUDE_SIMPLE_MODEL", "claude-haiku-4-5-20251001")
    CLAUDE_MODERATE_MODEL: str = os.getenv("CLAUDE_MODERATE_MODEL", "claude-sonnet-4-5-20250929")
    CLAUDE_COMPLEX_MODEL: str = os.getenv("CLAUDE_COMPLEX_MODEL", "claude-opus-4-6")
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.3"))
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))
    SCRAPE_RATE_LIMIT: float = float(os.getenv("SCRAPE_RATE_LIMIT", "0.5"))
    SCRAPE_MAX_PAGES: int = int(os.getenv("SCRAPE_MAX_PAGES", "5000"))
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    NOTIFICATION_EMAIL: str = os.getenv("NOTIFICATION_EMAIL", "")
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3001")
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
        if o.strip()
    ]


settings = Settings()
