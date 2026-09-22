"""Pure scoring functions.

Nothing in this package performs I/O, calls an LLM, touches a database or
imports Streamlit. Given the same inputs it returns the same outputs, which is
what makes every number in a result traceable and testable
(project.md section 2.3). ``tests/test_architecture.py`` enforces this.
"""
