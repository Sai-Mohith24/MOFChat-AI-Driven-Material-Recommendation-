"""
Backward-compatible entry point.

The review-1 scripts (e.g. reviews/1st_review/08_streamlit_dashboard.py) import
`MOFHybridAgent` from here and call `answer_query()`. The implementation now lives in
the `mofchat` package (planner -> validator -> SQL/NSGA-II -> answer validator).
"""

import mofchat  # noqa: F401  (safe native-library import order)
from mofchat.agent import MOFChatAgent


class MOFHybridAgent(MOFChatAgent):
    def answer_query(self, query: str) -> str:
        return self.answer(query).answer
