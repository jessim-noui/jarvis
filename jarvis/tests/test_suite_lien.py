"""Fait entrer les tests de la suite (jarvis\\suite\\tests) dans `unittest discover -s tests`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite.tests.test_suite import *  # noqa: E402,F401,F403

from suite.tests.test_labo_fiabilite import *  # noqa: E402,F401,F403
from suite.tests.test_fiabilite import *  # noqa: E402,F401,F403
