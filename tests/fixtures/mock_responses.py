"""Re-exports app.ai.demo_provider so existing test imports keep working.

The implementation lives in app/ai/demo_provider.py (production code) rather
than here, because app/cli.py's --mock flag and the UI's fixture-mode
checkbox both need it and must not depend on the tests/ tree being present in
a shipped install.
"""

from app.ai.demo_provider import (
    REACT_JD,
    RULES,
    TEAM_VOICE,
    build_mock_provider,
)

__all__ = ["RULES", "REACT_JD", "TEAM_VOICE", "build_mock_provider"]
