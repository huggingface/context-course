from pathlib import Path
import unittest


# This immutable revision contains the upstream kit fix that leaves /learn links alone.
DOC_BUILDER_LEARN_NAVIGATION_FIX = "7e31a94f70994bd73656a81690b13aaed439e798"


class DocumentationWorkflowTests(unittest.TestCase):
    def test_main_docs_build_pins_a_revision_with_the_course_navigation_fix(self):
        """Keep the production build reproducible on a revision with the /learn fix."""
        workflow = Path(".github/workflows/build_documentation.yml").read_text()

        self.assertIn(
            f"huggingface/doc-builder/.github/workflows/build_main_documentation.yml@{DOC_BUILDER_LEARN_NAVIGATION_FIX}",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
