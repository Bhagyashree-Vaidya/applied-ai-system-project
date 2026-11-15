"""Send test logs to a temp file so unit tests never pollute logs/pawpal_ai.log."""
import os
import tempfile

os.environ.setdefault("PAWPAL_LOG_FILE", os.path.join(tempfile.gettempdir(), "pawpal_ai_test.log"))
