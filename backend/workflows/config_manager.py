import os
from typing import List


class WorkflowConfigManager:
    """Resolves the prompts directory and lists persona (character) names.

    A character is a directory under ``prompts/personas/`` whose only content is
    ``identity_lock.txt`` (the fixed user-prompt text). Persona *types* and the
    per-type template files were removed with the single-agent pipeline.
    """

    def __init__(self):
        # Use PROMPTS_DIR env var, defaulting to a 'prompts/' dir at the repo root
        self.PROMPTS_DIR = os.path.abspath(
            os.getenv("PROMPTS_DIR", os.path.join(os.path.dirname(__file__), '..', '..', 'prompts'))
        )
        self.PERSONAS_DIR = os.path.join(self.PROMPTS_DIR, 'personas')
        os.makedirs(self.PERSONAS_DIR, exist_ok=True)

    def get_personas(self) -> List[str]:
        """Returns the sorted list of persona (character) names — one per directory."""
        if not os.path.exists(self.PERSONAS_DIR):
            return []
        return sorted(
            item for item in os.listdir(self.PERSONAS_DIR)
            if os.path.isdir(os.path.join(self.PERSONAS_DIR, item))
        )
