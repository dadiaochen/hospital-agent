import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Tests must never use the developer's live model configuration from .env.
os.environ.update(
    {
        "MODEL_PROVIDER": "deterministic",
        "MODEL_API_BASE": "",
        "MODEL_API_KEY": "",
        "MODEL_NAME": "deterministic-local",
        "MODEL_THINKING_MODE": "default",
    }
)
