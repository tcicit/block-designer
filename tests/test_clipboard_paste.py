import importlib.util
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData
from PyQt6.QtWidgets import QApplication

module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "block-designer.py")
spec = importlib.util.spec_from_file_location("block_designer", module_path)
block_designer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(block_designer)

CanvasWidget = block_designer.CanvasWidget
EditorModel = block_designer.EditorModel
TOOL_TEXT = block_designer.TOOL_TEXT


class ClipboardPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_paste_updates_model_grid(self):
        model = EditorModel()
        canvas = CanvasWidget(model)
        model.active_tool = TOOL_TEXT

        canvas._move_cursor_to(0, 0)
        mime_data = QMimeData()
        mime_data.setText("Hi")

        canvas.insertFromMimeData(mime_data)

        self.assertEqual(model.grid[0][0], "H")
        self.assertEqual(model.grid[0][1], "i")


if __name__ == "__main__":
    unittest.main()
