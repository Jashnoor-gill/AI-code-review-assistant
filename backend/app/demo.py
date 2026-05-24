from __future__ import annotations

from .adapters import LocalGitAdapter
from .llm import MockReviewModel
from .pipeline import ReviewPipeline
from .scanner import StaticRuleScanner


def main() -> None:
    adapter = LocalGitAdapter()
    context = adapter.fetch_context(
        """diff --git a/example.py b/example.py
index 1111111..2222222 100644
--- a/example.py
+++ b/example.py
@@ -1,3 +1,5 @@
 def run(user_input):
     TODO = True
     if user_input:
         eval(user_input)
"""
    )

    pipeline = ReviewPipeline(scanner=StaticRuleScanner(), model=MockReviewModel())
    job = pipeline.run(context)
    print(job.markdown_comment)


if __name__ == "__main__":
    main()
