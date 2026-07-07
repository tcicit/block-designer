"""
Python UTF8 Block Designer — PyQt6 Edition
=======================================

Classes:
    EditorModel   — data storage: layers, undo/redo, grid operations
    CanvasWidget  — drawing surface (QPlainTextEdit subclass)
    CharPalette   — right sidebar: character selection
    ToolSidebar   — left sidebar: tools, layers, shapes, export
    MainWindow    — main window: menu, layout, status bar, shortcuts
"""

import os
import sys
import copy

try:
    import yaml
except ImportError:
    print("Error: The 'pyyaml' module is required. Install with: pip install pyyaml")
    sys.exit(1)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QScrollArea,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QRadioButton, QCheckBox, QButtonGroup, QGroupBox, QComboBox,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QInputDialog,
    QFileDialog, QFrame, QSizePolicy, QPlainTextEdit,
    QFontDialog,
)
from PyQt6.QtGui import (
    QFont, QFontMetrics, QKeySequence, QAction, QTextCursor,
    QTextOption, QPalette, QColor, QShortcut, QIcon
)
from PyQt6.QtCore import (
    Qt, QSize, QTimer, pyqtSignal, QObject, QPoint,
)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
NUM_LAYERS = 3
LAYER_BACKGROUND = 0
LAYER_MIDDLE = 1
LAYER_FOREGROUND = 2
LAYER_NAMES = {LAYER_BACKGROUND: "Background", LAYER_MIDDLE: "Middle", LAYER_FOREGROUND: "Foreground"}

DEFAULT_FONT= ("Courier New", 12)

INITIAL_ROWS = 150
INITIAL_COLS = 150
EXPAND_STEP_ROWS = 20
EXPAND_STEP_COLS = 20

YAML_FILEPATH = "shapes.yaml"

TOOL_PEN    = "pen"
TOOL_BOX    = "box"
TOOL_LINE   = "line"
TOOL_TEXT   = "text"
TOOL_SELECT = "select"
TOOL_STAMP  = "stamp"

CHARS = [
" ", "─", "│", "┼", "┌", "┐", "└", "┘", "╱", "╲", "╳",
"▲", "▶", "▼", "◀", "○",
"┤", "├", "┬", "┴", "█", "▓", "▒", "░", "▉", "▊", "▋", "▌", "▍", "▎", "▏",
"▁", "▂", "▃", "▄", "▅", "▆", "▇",
"═", "║", "╔", "╗", "╚", "╝", "╠", "╣", "╦", "╩", "╬",
"(", ")", "◯", "[", "]", "{", "}", "<", ">", "∧", "∨", "«", "»",
"●", "■", "□", "◼", "◻", "◆", "◇", "◊",
"♥", "♦", "♣", "♠",
"☺", "☻", "☼", "☽", "☾", "☀", "☁", "☂", "☃",
"★", "☆", "✦", "✧", "✩", "✪", "✫", "✬", "✭", "✮", "✯",
"✰", "✱", "✲", "✳", "✴", "✵", "✶", "✷", "✸", "✹", "✺", "✻", "✼", "✽", "✾", "✿",
]


# ---------------------------------------------------------------------------
# EditorModel — Daten, Grid-Logik, Undo/Redo
# ---------------------------------------------------------------------------
class EditorModel(QObject):
    """Holds all editor content and performs data-side operations."""

    grid_changed  = pyqtSignal()
    layer_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.rows = INITIAL_ROWS
        self.cols = INITIAL_COLS

        self.layers = [
            [[" "] * self.cols for _ in range(self.rows)]
            for _ in range(NUM_LAYERS)
        ]
        self.layer_visibility = [True, True, True]
        self._current_layer = LAYER_MIDDLE

        self.undo_stack = []
        self.redo_stack = []

        self.selected_coords = None
        self.clipboard_selection = None
        self.pending_selection_action = None

        self.active_tool = TOOL_PEN
        self.current_char = "█"
        self.current_stamp = None

        self.shapes_templates = {}
        self.load_shapes_from_yaml()

    @property
    def current_layer(self):
        return self._current_layer

    @current_layer.setter
    def current_layer(self, value):
        if 0 <= value < NUM_LAYERS:
            self._current_layer = value
            self.layer_changed.emit(value)

    @property
    def grid(self):
        return self.layers[self._current_layer]

    # --- YAML ---
    def load_shapes_from_yaml(self):
        default_shapes = {
            "Arrow": ["   ▲   ", "  ███  ", "███████", "  ███  ", "  ███  "],
            "Tree":  ["   ▲   ", "  /░\\  ", " /░░░\\ ", "  ███  ", "  ███  "],
            "House": ["   /\\   ", "  /  \\  ", " /____\\ ", " | [] | ", " |____| "],
        }
        if not os.path.exists(YAML_FILEPATH):
            with open(YAML_FILEPATH, "w", encoding="utf-8") as f:
                yaml.dump(default_shapes, f, allow_unicode=True, default_flow_style=False)
            self.shapes_templates = default_shapes
        else:
            try:
                with open(YAML_FILEPATH, "r", encoding="utf-8") as f:
                    self.shapes_templates = yaml.safe_load(f) or {}
            except Exception as e:
                QMessageBox.critical(None, "YAML Error", f"Error loading {YAML_FILEPATH}:\n{e}")
                self.shapes_templates = default_shapes

    def save_shapes_to_yaml(self):
        try:
            with open(YAML_FILEPATH, "w", encoding="utf-8") as f:
                yaml.dump(self.shapes_templates, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            QMessageBox.critical(None, "YAML Error", f"Error writing {YAML_FILEPATH}:\n{e}")

    # --- Undo/Redo ---
    def save_state(self):
        self.undo_stack.append(copy.deepcopy(self.layers))
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.layers))
            self.layers = self.undo_stack.pop()
            self.grid_changed.emit()
            return "Action undone."
        return "Nothing to undo."

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.layers))
            self.layers = self.redo_stack.pop()
            self.grid_changed.emit()
            return "Action redone."
        return "Nothing to redo."

    # --- Grid-Erweiterung ---
    def expand_grid_if_needed(self, min_rows=None, min_cols=None):
        target_rows = self.rows
        target_cols = self.cols
        if min_rows is not None and min_rows > target_rows:
            target_rows = max(target_rows + EXPAND_STEP_ROWS, min_rows)
        if min_cols is not None and min_cols > target_cols:
            target_cols = max(target_cols + EXPAND_STEP_COLS, min_cols)
        if target_rows == self.rows and target_cols == self.cols:
            return False
        if target_cols > self.cols:
            for layer in self.layers:
                for row in layer:
                    row.extend([" "] * (target_cols - len(row)))
            self.cols = target_cols
        if target_rows > self.rows:
            for layer in self.layers:
                layer.extend([[" "] * self.cols for _ in range(target_rows - self.rows)])
            self.rows = target_rows
        return True

    # --- Zeichen/Formen ---
    def put_char(self, r, c, char):
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self.grid[r][c] = char

    def draw_box(self, r1, c1, r2, c2):
        min_r, max_r = min(r1, r2), max(r1, r2)
        min_c, max_c = min(c1, c2), max(c1, c2)
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if r == min_r or r == max_r or c == min_c or c == max_c:
                    if   r == min_r and c == min_c: self.grid[r][c] = "┌"
                    elif r == min_r and c == max_c: self.grid[r][c] = "┐"
                    elif r == max_r and c == min_c: self.grid[r][c] = "└"
                    elif r == max_r and c == max_c: self.grid[r][c] = "┘"
                    elif r == min_r or r == max_r:  self.grid[r][c] = "─"
                    else:                           self.grid[r][c] = "│"

    def draw_line(self, r1, c1, r2, c2):
        steps = max(abs(r2 - r1), abs(c2 - c1))
        if steps == 0:
            return
        for i in range(steps + 1):
            r = int(r1 + (r2 - r1) * i / steps)
            c = int(c1 + (c2 - c1) * i / steps)
            if 0 <= r < self.rows and 0 <= c < self.cols:
                if   abs(r2 - r1) > abs(c2 - c1): self.grid[r][c] = "│"
                elif abs(r2 - r1) < abs(c2 - c1): self.grid[r][c] = "─"
                else: self.grid[r][c] = "/" if (r2 - r1) * (c2 - c1) < 0 else "\\"

    def paint_stamp(self, center_r, center_c):
        if self.current_stamp not in self.shapes_templates:
            return
        template = self.shapes_templates[self.current_stamp]
        if not template:
            return
        h = len(template)
        w = max(len(row) for row in template)
        offset_r = h // 2
        offset_c = w // 2
        for r_idx, row_str in enumerate(template):
            for c_idx, char in enumerate(row_str):
                tr = center_r - offset_r + r_idx
                tc = center_c - offset_c + c_idx
                if 0 <= tr < self.rows and 0 <= tc < self.cols and char != " ":
                    self.grid[tr][tc] = char

    # --- Zeile/Spalte löschen ---
    def delete_row(self, row_idx):
        if not (0 <= row_idx < self.rows):
            return ""
        self.save_state()
        for layer in self.layers:
            del layer[row_idx]
            layer.append([" "] * self.cols)
        self.grid_changed.emit()
        return f"Row {row_idx + 1} deleted."

    def delete_col(self, col_idx):
        if not (0 <= col_idx < self.cols):
            return ""
        self.save_state()
        for layer in self.layers:
            for row in layer:
                del row[col_idx]
                row.append(" ")
        self.grid_changed.emit()
        return f"Column {col_idx} deleted."

    # --- Auswahl ---
    def copy_selection_data(self, r1, c1, r2, c2):
        min_r, max_r = min(r1, r2), max(r1, r2)
        min_c, max_c = min(c1, c2), max(c1, c2)
        self.selected_coords = (min_r, min_c, max_r, max_c)
        self.clipboard_selection = [
            [self.grid[r][c] for c in range(min_c, max_c + 1)]
            for r in range(min_r, max_r + 1)
        ]

    def clear_selection(self):
        self.selected_coords = None
        self.clipboard_selection = None
        self.pending_selection_action = None

    def selection_contains(self, r, c):
        if self.selected_coords is None:
            return False
        min_r, min_c, max_r, max_c = self.selected_coords
        return min_r <= r <= max_r and min_c <= c <= max_c

    def selection_edge_handle(self, r, c):
        if self.selected_coords is None:
            return None
        min_r, min_c, max_r, max_c = self.selected_coords
        if not (min_r <= r <= max_r and min_c <= c <= max_c):
            return None
        on_top = r == min_r
        on_bottom = r == max_r
        on_left = c == min_c
        on_right = c == max_c
        if on_top and on_left:
            return "top-left"
        if on_top and on_right:
            return "top-right"
        if on_bottom and on_left:
            return "bottom-left"
        if on_bottom and on_right:
            return "bottom-right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        if on_left:
            return "left"
        if on_right:
            return "right"
        return "inside"

    def delete_selected_area(self):
        if not self.selected_coords:
            return
        self.save_state()
        min_r, min_c, max_r, max_c = self.selected_coords
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if 0 <= r < self.rows and 0 <= c < self.cols:
                    self.grid[r][c] = " "
        self.grid_changed.emit()

    def clone_selection_to(self, start_r, start_c):
        if not self.selected_coords or not self.clipboard_selection:
            return
        self.save_state()
        for r_idx, row_data in enumerate(self.clipboard_selection):
            for c_idx, char in enumerate(row_data):
                tr, tc = start_r + r_idx, start_c + c_idx
                if 0 <= tr < self.rows and 0 <= tc < self.cols:
                    self.grid[tr][tc] = char
        self.grid_changed.emit()

    def move_selection_to(self, start_r, start_c):
        if not self.selected_coords or not self.clipboard_selection:
            return
        self.save_state()
        original = copy.deepcopy(self.clipboard_selection)
        height = len(original)
        width = len(original[0]) if height else 0
        self.expand_grid_if_needed(min_rows=start_r + height, min_cols=start_c + width)
        min_r, min_c, max_r, max_c = self.selected_coords
        for r_idx in range(height):
            for c_idx in range(width):
                sr, sc = min_r + r_idx, min_c + c_idx
                if 0 <= sr < self.rows and 0 <= sc < self.cols:
                    self.grid[sr][sc] = " "
        for r_idx in range(height):
            for c_idx in range(width):
                tr, tc = start_r + r_idx, start_c + c_idx
                if 0 <= tr < self.rows and 0 <= tc < self.cols:
                    self.grid[tr][tc] = original[r_idx][c_idx]
        self.selected_coords = (start_r, start_c, start_r + height - 1, start_c + width - 1)
        self.grid_changed.emit()

    def paste_clipboard_at(self, start_r, start_c):
        if not self.clipboard_selection:
            return
        self.save_state()
        height = len(self.clipboard_selection)
        width = len(self.clipboard_selection[0]) if height else 0
        self.expand_grid_if_needed(min_rows=start_r + height, min_cols=start_c + width)
        for r_idx, row_data in enumerate(self.clipboard_selection):
            for c_idx, char in enumerate(row_data):
                tr, tc = start_r + r_idx, start_c + c_idx
                if 0 <= tr < self.rows and 0 <= tc < self.cols:
                    self.grid[tr][tc] = char
        self.grid_changed.emit()

    def clear_current_layer(self):
        self.save_state()
        self.layers[self._current_layer] = [[" "] * self.cols for _ in range(self.rows)]
        self.selected_coords = None
        self.grid_changed.emit()

    # --- Rendering ---
    def build_display(self, preview=None):
        display = [[" "] * self.cols for _ in range(self.rows)]
        for layer_idx in range(NUM_LAYERS):
            if not self.layer_visibility[layer_idx]:
                continue
            layer = self.layers[layer_idx]
            for r in range(self.rows):
                for c in range(self.cols):
                    ch = layer[r][c]
                    if ch != " ":
                        display[r][c] = ch

        if self.selected_coords and (not preview or preview[0] != TOOL_SELECT):
            min_r, min_c, max_r, max_c = self.selected_coords
            for r in range(min_r, max_r + 1):
                for c in range(min_c, max_c + 1):
                    if r == min_r or r == max_r or c == min_c or c == max_c:
                        display[r][c] = "░"

        if preview:
            tool, r1, c1, r2, c2 = preview
            if tool in (TOOL_BOX, TOOL_LINE, TOOL_SELECT) and r2 is not None:
                min_r, max_r = min(r1, r2), max(r1, r2)
                min_c, max_c = min(c1, c2), max(c1, c2)
                if tool == TOOL_BOX:
                    for r in range(min_r, max_r + 1):
                        for c in range(min_c, max_c + 1):
                            if r == min_r or r == max_r or c == min_c or c == max_c:
                                display[r][c] = "+"
                elif tool == TOOL_LINE:
                    steps = max(abs(r2 - r1), abs(c2 - c1))
                    if steps > 0:
                        for i in range(steps + 1):
                            r = int(r1 + (r2 - r1) * i / steps)
                            c = int(c1 + (c2 - c1) * i / steps)
                            if 0 <= r < self.rows and 0 <= c < self.cols:
                                display[r][c] = "*"
                elif tool == TOOL_SELECT:
                    for r in range(min_r, max_r + 1):
                        for c in range(min_c, max_c + 1):
                            display[r][c] = "░"
            elif tool == TOOL_STAMP and self.current_stamp in self.shapes_templates:
                template = self.shapes_templates[self.current_stamp]
                if template:
                    offset_r = len(template) // 2
                    offset_c = max(len(row) for row in template) // 2
                    for r_idx, row_str in enumerate(template):
                        for c_idx, char in enumerate(row_str):
                            tr = r1 - offset_r + r_idx
                            tc = c1 - offset_c + c_idx
                            if 0 <= tr < self.rows and 0 <= tc < self.cols and char != " ":
                                display[tr][tc] = "░"
        return display

    def get_flat_text(self):
        display = self.build_display()
        return "\n".join("".join(row).rstrip() for row in display)

    def load_from_file(self, filename):
        try:
            self.save_state()
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
            max_line_len = max((len(ln.rstrip("\n")) for ln in lines), default=0)
            self.expand_grid_if_needed(min_rows=len(lines), min_cols=max_line_len)
            for r in range(self.rows):
                self.layers[self._current_layer][r] = [" "] * self.cols
            for i, line in enumerate(lines[:self.rows]):
                cleaned = line.rstrip("\n").ljust(self.cols)
                self.layers[self._current_layer][i] = list(cleaned[:self.cols])
            self.grid_changed.emit()
            return ""
        except Exception as e:
            return str(e)

    def save_to_file(self, filename):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.get_flat_text())
            return ""
        except Exception as e:
            return str(e)


# ---------------------------------------------------------------------------
# CanvasWidget
# ---------------------------------------------------------------------------
class CanvasWidget(QPlainTextEdit):
    """Monospace drawing surface. Delegates data to EditorModel."""

    status_message = pyqtSignal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model

        font = QFont(DEFAULT_FONT[0], DEFAULT_FONT[1])
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.document().setDocumentMargin(0)  # kein interner Abstand oben

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#fafafa"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1a1a2e"))
        self.setPalette(pal)

        self._dragging = False
        self._start_row = None
        self._start_col = None
        self._preview = None
        self._selection_move = False
        self._selection_resize = False
        self._selection_handle = None
        self._selection_origin = None
        self._selection_drag_start = None
        self._hover_row = None
        self._hover_col = None

        model.grid_changed.connect(self.refresh)
        self.refresh()

    # --- Koordinaten ---
    def _pos_to_rc(self, x, y):
        tc = self.cursorForPosition(QPoint(int(x), int(y)))
        return tc.blockNumber(), tc.positionInBlock()

    def _ensure_valid(self, r, c):
        if r is None or c is None:
            return None, None
        if r >= self.model.rows or c >= self.model.cols:
            self.model.expand_grid_if_needed(min_rows=r + 1, min_cols=c + 1)
        return r, c

    # --- Rendering ---
    def refresh(self, preview=None):
        display = self.model.build_display(preview or self._preview)

        cur = self.textCursor()
        saved_block = cur.blockNumber()
        saved_col   = cur.positionInBlock()
        v_val = self.verticalScrollBar().value()
        h_val = self.horizontalScrollBar().value()

        lines = ["".join(("." if ch == " " else ch) for ch in row) for row in display]
        new_text = "\n".join(lines)

        self.blockSignals(True)
        self.setPlainText(new_text)
        self.blockSignals(False)

        # Cursor restaurieren
        block = min(saved_block, self.document().blockCount() - 1)
        tc = self.textCursor()
        tc.movePosition(QTextCursor.MoveOperation.Start)
        if block > 0:
            tc.movePosition(QTextCursor.MoveOperation.NextBlock,
                            QTextCursor.MoveMode.MoveAnchor, block)
        line_len = len(self.document().findBlockByNumber(block).text())
        col = min(saved_col, line_len)
        if col > 0:
            tc.movePosition(QTextCursor.MoveOperation.Right,
                            QTextCursor.MoveMode.MoveAnchor, col)
        self.setTextCursor(tc)
        self.verticalScrollBar().setValue(v_val)
        self.horizontalScrollBar().setValue(h_val)

    # --- Maus ---
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        r, c = self._pos_to_rc(event.position().x(), event.position().y())
        r, c = self._ensure_valid(r, c)
        if r is None:
            return

        model = self.model
        tool  = model.active_tool

        if model.pending_selection_action and model.selected_coords and tool == TOOL_SELECT:
            self._apply_pending_action(r, c)
            return

        self._dragging = True
        self._start_row, self._start_col = r, c
        self._hover_row, self._hover_col = r, c
        self._selection_move = False
        self._selection_resize = False
        self._selection_handle = None
        self._selection_origin = None
        self._selection_drag_start = None

        if tool == TOOL_SELECT:
            if model.selected_coords:
                handle = model.selection_edge_handle(r, c)
                if handle:
                    self._selection_drag_start = (r, c)
                    self._selection_origin = model.selected_coords
                    if handle == "inside":
                        self._selection_move = True
                        self._selection_handle = "inside"
                        self.status_message.emit("Drag selection to move it.")
                        return
                    self._selection_resize = True
                    self._selection_handle = handle
                    self.status_message.emit("Drag selection border to resize it.")
                    return
            self._preview = (TOOL_SELECT, r, c, r, c)
            self.refresh()
            return

        if tool == TOOL_PEN:
            model.save_state()
            model.expand_grid_if_needed(min_rows=r + 1, min_cols=c + 1)
            model.put_char(r, c, model.current_char)
            self.refresh()
        elif tool == TOOL_TEXT:
            model.save_state()
            self._move_cursor_to(r, c)
        elif tool == TOOL_STAMP and model.current_stamp:
            model.save_state()
            model.expand_grid_if_needed(min_rows=r + 1, min_cols=c + 1)
            model.paint_stamp(r, c)
            self.refresh()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            r, c = self._pos_to_rc(event.position().x(), event.position().y())
            self._hover_row, self._hover_col = r, c
            if self.model.active_tool == TOOL_STAMP and self.model.current_stamp:
                self._preview = (TOOL_STAMP, r, c, None, None)
                self.refresh()
            return

        r, c = self._pos_to_rc(event.position().x(), event.position().y())
        r, c = self._ensure_valid(r, c)
        if r is None:
            return
        self._hover_row, self._hover_col = r, c

        model = self.model
        tool  = model.active_tool

        if tool == TOOL_PEN:
            model.expand_grid_if_needed(min_rows=r + 1, min_cols=c + 1)
            model.put_char(r, c, model.current_char)
            self.refresh()
        elif tool == TOOL_SELECT:
            if self._start_row is None:
                return
            if self._selection_move or self._selection_resize:
                origin = self._selection_origin
                if origin is None:
                    return
                min_r, min_c, max_r, max_c = origin
                if self._selection_move:
                    dr = r - self._selection_drag_start[0]
                    dc = c - self._selection_drag_start[1]
                    new_min_r = max(0, min_r + dr)
                    new_min_c = max(0, min_c + dc)
                    new_max_r = max(0, max_r + dr)
                    new_max_c = max(0, max_c + dc)
                    self._preview = (TOOL_SELECT, new_min_r, new_min_c, new_max_r, new_max_c)
                else:
                    new_min_r, new_min_c, new_max_r, new_max_c = min_r, min_c, max_r, max_c
                    if self._selection_handle in ("top-left", "top", "top-right"):
                        new_min_r = min(r, max_r)
                    if self._selection_handle in ("bottom-left", "bottom", "bottom-right"):
                        new_max_r = max(r, min_r)
                    if self._selection_handle in ("top-left", "left", "bottom-left"):
                        new_min_c = min(c, max_c)
                    if self._selection_handle in ("top-right", "right", "bottom-right"):
                        new_max_c = max(c, min_c)
                    self._preview = (TOOL_SELECT, new_min_r, new_min_c, new_max_r, new_max_c)
                self.refresh()
                return
            if self._start_row is not None:
                self._preview = (TOOL_SELECT, self._start_row, self._start_col, r, c)
                self.refresh()
        elif tool in (TOOL_BOX, TOOL_LINE):
            if self._start_row is not None:
                self._preview = (tool, self._start_row, self._start_col, r, c)
                self.refresh()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False

        r, c = self._pos_to_rc(event.position().x(), event.position().y())
        r, c = self._ensure_valid(r, c)
        preview = self._preview

        if r is None or self._start_row is None:
            self._reset_selection_state()
            self.refresh()
            return

        model = self.model
        tool  = model.active_tool

        if tool == TOOL_BOX:
            model.save_state()
            model.draw_box(self._start_row, self._start_col, r, c)
            model.grid_changed.emit()
        elif tool == TOOL_LINE:
            model.save_state()
            model.draw_line(self._start_row, self._start_col, r, c)
            model.grid_changed.emit()
        elif tool == TOOL_SELECT:
            if self._selection_move or self._selection_resize:
                if preview:
                    _, min_r, min_c, max_r, max_c = preview
                    model.copy_selection_data(min_r, min_c, max_r, max_c)
                    self.status_message.emit("Selection adjusted.")
            else:
                model.copy_selection_data(self._start_row, self._start_col, r, c)
                self.status_message.emit("Selection made. Choose an action or use Ctrl+V.")

        self._reset_selection_state()
        self.refresh()

    def leaveEvent(self, event):
        if self._preview:
            self._preview = None
            self.refresh()
        super().leaveEvent(event)

    # --- Tastatur ---
    def keyPressEvent(self, event):
        model = self.model
        tool  = model.active_tool
        key   = event.key()
        mods  = event.modifiers()

        if mods & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_V:
            if self._hover_row is not None and self._hover_col is not None:
                r, c = self._hover_row, self._hover_col
            else:
                tc = self.textCursor()
                r, c = tc.blockNumber(), tc.positionInBlock()
            model.paste_clipboard_at(r, c)
            self.status_message.emit("Pasted selection at mouse position.")
            event.accept()
            return

        if tool != TOOL_TEXT:
            if key in (
                Qt.Key.Key_Left, Qt.Key.Key_Right,
                Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_Home, Qt.Key.Key_End,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
                Qt.Key.Key_Escape,
            ):
                super().keyPressEvent(event)
                return
            event.accept()
            return

        if tool == TOOL_TEXT:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Escape):
                model.active_tool = TOOL_PEN
                self.status_message.emit(self.make_status_text())
                return
            if key == Qt.Key.Key_Backspace:
                tc = self.textCursor()
                r, c = tc.blockNumber(), tc.positionInBlock()
                if c > 0:
                    model.grid[r][c - 1] = " "
                    self.refresh()
                    self._move_cursor_to(r, c - 1)
                return
            ch = event.text()
            if ch and len(ch) == 1 and ch.isprintable():
                tc = self.textCursor()
                r, c = tc.blockNumber(), tc.positionInBlock()
                model.expand_grid_if_needed(min_rows=r + 1, min_cols=c + 2)
                model.grid[r][c] = ch
                self.refresh()
                self._move_cursor_to(r, min(model.cols - 1, c + 1))
                return
            return

    # --- Hilfsmethoden ---
    def _move_cursor_to(self, r, c):
        tc = self.textCursor()
        tc.movePosition(QTextCursor.MoveOperation.Start)
        if r > 0:
            tc.movePosition(QTextCursor.MoveOperation.NextBlock,
                            QTextCursor.MoveMode.MoveAnchor, r)
        if c > 0:
            tc.movePosition(QTextCursor.MoveOperation.Right,
                            QTextCursor.MoveMode.MoveAnchor, c)
        self.setTextCursor(tc)

    def _reset_selection_state(self):
        self._start_row = None
        self._start_col = None
        self._selection_move = False
        self._selection_resize = False
        self._selection_handle = None
        self._selection_origin = None
        self._selection_drag_start = None
        self._preview = None

    def _apply_pending_action(self, r, c):
        model = self.model
        action = model.pending_selection_action
        if action == "clone":
            model.clone_selection_to(r, c)
        elif action == "move":
            model.move_selection_to(r, c)
        model.pending_selection_action = None
        self.status_message.emit("Fertig.")
        self.refresh()

    def make_status_text(self):
        model = self.model
        layer_name = LAYER_NAMES.get(model.current_layer, "?")
        tool_names = {
            TOOL_PEN:    f"Pen (Char: {model.current_char})",
            TOOL_BOX:    "Draw box",
            TOOL_LINE:   "Draw line",
            TOOL_TEXT:   "Click to type",
            TOOL_SELECT: "Select area",
            TOOL_STAMP:  f"Stamp [{model.current_stamp}]",
        }
        return f"Layer: {layer_name} | Mode: {tool_names.get(model.active_tool, model.active_tool)}"


# ---------------------------------------------------------------------------
# LineNumberWidget
# ---------------------------------------------------------------------------
class LineNumberWidget(QPlainTextEdit):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(canvas.font())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(42)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(0, 0, 0, 0)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#888888"))
        self.setPalette(pal)
        self.setFrameShape(QFrame.Shape.NoFrame)
        canvas.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)

    def set_display_font(self, font):
        self.setFont(font)
        # width stays reasonable as before (fixed minimal width)

    def update_numbers(self, rows):
        self.setPlainText("\n".join(f"{i+1:2}" for i in range(rows)))


# ---------------------------------------------------------------------------
# ColNumberWidget
# ---------------------------------------------------------------------------
class ColNumberWidget(QPlainTextEdit):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(canvas.font())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fm = QFontMetrics(canvas.font())
        # lineSpacing() = height + leading — entspricht dem tatsächlichen Zeilenabstand in QPlainTextEdit
        self.setFixedHeight(fm.lineSpacing() + 2)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(0, 0, 0, 0)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#888888"))
        self.setPalette(pal)
        self.setFrameShape(QFrame.Shape.NoFrame)
        canvas.horizontalScrollBar().valueChanged.connect(self.horizontalScrollBar().setValue)

    def set_display_font(self, font):
        self.setFont(font)
        fm = QFontMetrics(font)
        self.setFixedHeight(fm.lineSpacing() + 2)

    def update_numbers(self, cols):
        row = []
        for c in range(cols):
            if c == 0:          row.append("0")
            elif c % 10 == 0:   row.append(str((c // 10) % 10))
            elif c % 5 == 0:    row.append("┼")
            else:               row.append("·")
        self.setPlainText("".join(row))


# ---------------------------------------------------------------------------
# CharPalette
# ---------------------------------------------------------------------------
class CharPalette(QScrollArea):
    char_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(160)
        self.setMaximumWidth(320)

        self._container = QGroupBox("Character Palette")
        self._grid_layout = QGridLayout(self._container)
        self._grid_layout.setSpacing(2)
        self._grid_layout.setContentsMargins(4, 8, 4, 4)
        self.setWidget(self._container)

        self._buttons = []
        self._cols = 0
        for char in CHARS:
            display = "Eraser" if char == " " else char
            btn = QPushButton(display)
            btn.setFixedSize(QSize(34, 28))
            btn.setFont(QFont("Courier New", 10))
            btn.clicked.connect(lambda checked, c=char: self.char_selected.emit(c))
            self._buttons.append(btn)

    def relayout(self, available_width):
        btn_w = 38
        new_cols = max(1, (available_width - 20) // btn_w)
        if new_cols == self._cols:
            return
        self._cols = new_cols
        for btn in self._buttons:
            self._grid_layout.removeWidget(btn)
        for idx, btn in enumerate(self._buttons):
            self._grid_layout.addWidget(btn, idx // new_cols, idx % new_cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout(event.size().width())


# ---------------------------------------------------------------------------
# ToolSidebar
# ---------------------------------------------------------------------------
class ToolSidebar(QScrollArea):
    tool_selected      = pyqtSignal(str)
    stamp_selected     = pyqtSignal(str)
    layer_changed      = pyqtSignal(int)
    visibility_changed = pyqtSignal(int, bool)
    delete_row_req     = pyqtSignal()
    delete_col_req     = pyqtSignal()
    selection_action   = pyqtSignal(str)
    export_clipboard   = pyqtSignal()

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWidgetResizable(True)
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        root = QWidget()
        vbox = QVBoxLayout(root)
        vbox.setSpacing(4)
        vbox.setContentsMargins(4, 4, 4, 4)

        # Tools
        tg = QGroupBox("Tools")
        tg_l = QVBoxLayout(tg)
        tg_l.setSpacing(2)
        for label, tool in [("✏️ Pen (freehand) [P]", TOOL_PEN),
                             ("🧱 Box (Drag) [B]",     TOOL_BOX),
                             ("📏 Line (Drag) [L]",   TOOL_LINE),
                             ("🔤 Insert text [T]",    TOOL_TEXT)]:
            b = QPushButton(label)
            b.clicked.connect(lambda checked, t=tool: self.tool_selected.emit(t))
            tg_l.addWidget(b)
        vbox.addWidget(tg)

        # Selection
        sg = QGroupBox("Selection")
        sg_l = QVBoxLayout(sg)
        sg_l.setSpacing(2)
        for label, act in [(" 🖍️ Select area [C]", "select_tool"),
                            ("🧬 Clone",              "clone"),
                            ("➡️ Move",               "move"),
                            ("🗑️ Delete",             "delete"),
                            ("📋 Selection → Clipboard",  "copy"),
                            ("✨ Selection → Shape",   "to_shape")]:
            b = QPushButton(label)
            if act == "select_tool":
                b.clicked.connect(lambda: self.tool_selected.emit(TOOL_SELECT))
            else:
                b.clicked.connect(lambda checked, a=act: self.selection_action.emit(a))
            sg_l.addWidget(b)
        vbox.addWidget(sg)

        # Layers
        lg = QGroupBox("Layers")
        lg_l = QVBoxLayout(lg)
        lg_l.setSpacing(2)
        self._layer_radio_group = QButtonGroup(self)
        self._visibility_checks = []
        for layer_idx, label in [(LAYER_FOREGROUND, "3: Foreground"),
                                  (LAYER_MIDDLE,     "2: Middle (Active)"),
                                  (LAYER_BACKGROUND, "1: Background")]:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            cb = QCheckBox()
            cb.setChecked(True)
            cb.checkStateChanged.connect(
                lambda state, li=layer_idx: self.visibility_changed.emit(
                    li, state == Qt.CheckState.Checked))
            self._visibility_checks.append(cb)
            rb = QRadioButton(label)
            if layer_idx == model.current_layer:
                rb.setChecked(True)
            self._layer_radio_group.addButton(rb, layer_idx)
            rb.toggled.connect(
                lambda checked, li=layer_idx: self.layer_changed.emit(li) if checked else None)
            row_l.addWidget(cb)
            row_l.addWidget(rb)
            row_l.addStretch()
            lg_l.addWidget(row_w)
        vbox.addWidget(lg)

        # Cursor Actions
        cg = QGroupBox("Cursor Actions")
        cg_l = QVBoxLayout(cg)
        cg_l.setSpacing(2)
        b_dr = QPushButton("Delete whole row")
        b_dc = QPushButton("Delete whole column")
        b_dr.clicked.connect(self.delete_row_req)
        b_dc.clicked.connect(self.delete_col_req)
        cg_l.addWidget(b_dr)
        cg_l.addWidget(b_dc)
        vbox.addWidget(cg)

        # Shapes
        shg = QGroupBox("Shapes (YAML)")
        shg_l = QVBoxLayout(shg)
        shg_l.setSpacing(2)
        self.shape_combo = QComboBox()
        self.shape_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.shape_combo.currentTextChanged.connect(self._on_shape_selected)
        shg_l.addWidget(self.shape_combo)
        vbox.addWidget(shg)
        self.update_shape_combo()

        # Export
        eg = QGroupBox("Export")
        eg_l = QVBoxLayout(eg)
        b_exp = QPushButton("Export All to clipboard")
        b_exp.clicked.connect(self.export_clipboard)
        eg_l.addWidget(b_exp)
        vbox.addWidget(eg)
        vbox.addStretch()
        self.setWidget(root)

    def _on_shape_selected(self, name):
        if name and name not in ("Select shape...", "No shapes available"):
            self.stamp_selected.emit(name)

    def update_shape_combo(self):
        self.shape_combo.blockSignals(True)
        self.shape_combo.clear()
        names = list(self.model.shapes_templates.keys())
        if names:
            self.shape_combo.addItem("Select shape...")
            self.shape_combo.addItems(names)
        else:
            self.shape_combo.addItem("No shapes available")
        self.shape_combo.blockSignals(False)

    def reset_shape_combo(self):
        self.shape_combo.blockSignals(True)
        self.shape_combo.setCurrentIndex(0)
        self.shape_combo.blockSignals(False)


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python UTF8 Block-Editor — PyQt6 Edition")
        self.resize(1300, 850)

        self.model = EditorModel(self)
        self.current_file_path = None

        self._build_ui()
        self._build_menu()
        self._connect_signals()
        self._setup_shortcuts()
        self._update_status()
        QTimer.singleShot(0, self._refresh_headers)


        # Set App Icon (Global)
        self.setWindowIcon(QIcon("logo.png"))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_hbox = QHBoxLayout(central)
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setContentsMargins(0, 0, 0, 0)  # QSplitter-eigene Margins entfernen
        main_hbox.addWidget(splitter)

        # Linke Sidebar
        self.tool_sidebar = ToolSidebar(self.model)
        splitter.addWidget(self.tool_sidebar)

        # Mitte: Canvas + Header
        center_frame = QWidget()
        center_frame.setContentsMargins(0, 0, 0, 0)
        center_vbox = QVBoxLayout(center_frame)
        center_vbox.setContentsMargins(0, 0, 0, 0)
        center_vbox.setSpacing(0)

        self.canvas = CanvasWidget(self.model)
        self.line_numbers = LineNumberWidget(self.canvas)
        self.col_numbers  = ColNumberWidget(self.canvas)

        # Zeilennummer-Breite ermitteln (fixedWidth ist auch vor show() verfügbar)
        lnw = 42  # entspricht LineNumberWidget.setFixedWidth(42)
        fm = QFontMetrics(self.canvas.font())
        col_h = fm.lineSpacing() + 2   # gleiche Höhe wie ColNumberWidget

        # Spaltenheader-Zeile
        col_row = QWidget()
        col_row.setFixedHeight(col_h)   # explizit fixieren — kein Stretch-Artefakt
        col_row_l = QHBoxLayout(col_row)
        col_row_l.setContentsMargins(0, 0, 0, 0)
        col_row_l.setSpacing(0)
        corner = QWidget()
        corner.setFixedSize(lnw, col_h)
        col_row_l.addWidget(corner)
        col_row_l.addWidget(self.col_numbers)
        center_vbox.addWidget(col_row, 0)   # stretch=0: nimmt nur die fixe Höhe

        # Canvas-Zeile mit Zeilennummern
        canvas_row = QWidget()
        canvas_row_l = QHBoxLayout(canvas_row)
        canvas_row_l.setContentsMargins(0, 0, 0, 0)
        canvas_row_l.setSpacing(0)
        canvas_row_l.addWidget(self.line_numbers)
        canvas_row_l.addWidget(self.canvas)
        center_vbox.addWidget(canvas_row, 1)  # stretch=1: füllt restlichen Platz
        splitter.addWidget(center_frame)

        # Rechte Sidebar
        self.char_palette = CharPalette()
        splitter.addWidget(self.char_palette)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 860, 220])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        a = QAction("Open file…", self)
        a.setShortcut(QKeySequence.StandardKey.Open)
        a.triggered.connect(self._load_from_file)
        fm.addAction(a)

        a = QAction("Save", self)
        a.setShortcut(QKeySequence.StandardKey.Save)
        a.triggered.connect(self._save_to_file)
        fm.addAction(a)

        a = QAction("Save as…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+S"))
        a.triggered.connect(self._save_as_to_file)
        fm.addAction(a)

        fm.addSeparator()
        a = QAction("Exit", self)
        a.setShortcut(QKeySequence.StandardKey.Quit)
        a.triggered.connect(self.close)
        fm.addAction(a)

        em = mb.addMenu("&Edit")
        a = QAction("Undo", self)
        a.setShortcut(QKeySequence.StandardKey.Undo)
        a.triggered.connect(self._undo)
        em.addAction(a)

        a = QAction("Redo", self)
        a.setShortcut(QKeySequence.StandardKey.Redo)
        a.triggered.connect(self._redo)
        em.addAction(a)

        em.addSeparator()
        a = QAction("Clear current layer", self)
        a.triggered.connect(lambda: self.model.clear_current_layer())
        em.addAction(a)

        # a = QAction("Set font…", self)
        # a.setShortcut(QKeySequence("Ctrl+F"))
        # a.triggered.connect(self._choose_font)
        # em.addAction(a)

        hm = mb.addMenu("&Help")
        a = QAction("About…", self)
        a.triggered.connect(self._show_about)
        hm.addAction(a)

    def _connect_signals(self):
        m  = self.model
        sb = self.tool_sidebar
        m.grid_changed.connect(self._refresh_headers)
        m.layer_changed.connect(self._update_status)
        self.canvas.status_message.connect(self.status_bar.showMessage)
        sb.tool_selected.connect(self._set_tool)
        sb.stamp_selected.connect(self._set_stamp)
        sb.layer_changed.connect(self._change_layer)
        sb.visibility_changed.connect(self._toggle_visibility)
        sb.delete_row_req.connect(self._delete_current_row)
        sb.delete_col_req.connect(self._delete_current_col)
        sb.selection_action.connect(self._handle_selection_action)
        sb.export_clipboard.connect(self._export_to_clipboard)
        self.char_palette.char_selected.connect(self._set_char)

    def _setup_shortcuts(self):
        def tool_sc(key, tool):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(
                lambda t=tool: self._set_tool(t) if self.model.active_tool != TOOL_TEXT else None)

        tool_sc("p", TOOL_PEN)
        tool_sc("b", TOOL_BOX)
        tool_sc("l", TOOL_LINE)
        tool_sc("t", TOOL_TEXT)
        tool_sc("c", TOOL_SELECT)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._cancel_tool)

        for i in range(NUM_LAYERS):
            sc = QShortcut(QKeySequence(str(i + 1)), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(
                lambda li=i: self._change_layer(li) if self.model.active_tool != TOOL_TEXT else None)

    # --- Slots ---
    def _set_tool(self, tool):
        self.model.active_tool = tool
        if tool != TOOL_STAMP:
            self.model.current_stamp = None
        self._update_status()

    def _set_char(self, char):
        self.model.current_char = char
        self._set_tool(TOOL_PEN)

    def _set_stamp(self, name):
        self.model.active_tool = TOOL_STAMP
        self.model.current_stamp = name
        self._update_status()

    def _change_layer(self, layer_idx):
        self.model.current_layer = layer_idx
        btn = self.tool_sidebar._layer_radio_group.button(layer_idx)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self._update_status()

    def _toggle_visibility(self, layer_idx, visible):
        self.model.layer_visibility[layer_idx] = visible
        self.model.grid_changed.emit()

    def _update_status(self, *_):
        self.status_bar.showMessage(self.canvas.make_status_text())

    # def _choose_font(self):
    #     font, ok = QFontDialog.getFont(self.canvas.font(), self, "Choose font")
    #     if not ok:
    #         return
    #     self._apply_font(font)

    def _apply_font(self, font: QFont):
        # prefer monospace for alignment
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.canvas.setFont(font)
        self.line_numbers.set_display_font(font)
        self.col_numbers.set_display_font(font)
        # update palette buttons
        for btn in getattr(self.char_palette, "_buttons", []):
            btn.setFont(font)
        fm = QFontMetrics(font)
        self.col_numbers.setFixedHeight(fm.lineSpacing() + 2)
        self._refresh_headers()
        self._update_status()

    def _cancel_tool(self):
        self.model.selected_coords = None
        self.model.clipboard_selection = None
        self.model.pending_selection_action = None
        self.tool_sidebar.reset_shape_combo()
        self._set_tool(TOOL_PEN)
        self.canvas.refresh()
        # cleanup done; export button/widget already belongs to the sidebar
    def _delete_current_row(self):
        r = self.canvas.textCursor().blockNumber()
        msg = self.model.delete_row(r)
        if msg:
            self.status_bar.showMessage(msg)
            self._refresh_headers()

    def _delete_current_col(self):
        c = self.canvas.textCursor().positionInBlock()
        msg = self.model.delete_col(c)
        if msg:
            self.status_bar.showMessage(msg)
            self._refresh_headers()

    def _handle_selection_action(self, action):
        model = self.model
        if action == "copy":
            if not model.selected_coords:
                QMessageBox.warning(self, "No selection", "Please select an area first.")
                return
            min_r, min_c, max_r, max_c = model.selected_coords
            model.clipboard_selection = [
                [model.grid[r][c] for c in range(min_c, max_c + 1)]
                for r in range(min_r, max_r + 1)
            ]
            text = "\n".join(
                "".join(model.grid[r][c] for c in range(min_c, max_c + 1)).rstrip()
                for r in range(min_r, max_r + 1))
            QApplication.clipboard().setText(text)
            self.status_bar.showMessage("Selection copied to clipboard.")
            return
        if action == "to_shape":
            self._convert_selection_to_shape()
            return
        if not model.selected_coords:
            QMessageBox.warning(self, "No selection", "Please select an area first.")
            return
        if action == "delete":
            model.delete_selected_area()
            self.status_bar.showMessage("Selection deleted.")
        elif action in ("clone", "move"):
            model.active_tool = TOOL_SELECT
            model.pending_selection_action = action
            msg = {"clone": "Clone: click the target position.",
                   "move":  "Move: click the target position."}[action]
            self.status_bar.showMessage(msg)

    def _convert_selection_to_shape(self):
        model = self.model
        if not model.selected_coords:
            QMessageBox.warning(self, "No selection", "Please select an area first.")
            return
        min_r, min_c, max_r, max_c = model.selected_coords
        shape_lines = [
            "".join(model.grid[r][c] for c in range(min_c, max_c + 1))
            for r in range(min_r, max_r + 1)]
        name, ok = QInputDialog.getText(self, "Save Shape", "Name for the new shape:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in model.shapes_templates:
            reply = QMessageBox.question(
                self, "Overwrite", f"Shape '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        model.shapes_templates[name] = shape_lines
        model.save_shapes_to_yaml()
        self.tool_sidebar.update_shape_combo()
        QMessageBox.information(self, "Success", f"Shape '{name}' registered successfully!")

    def _export_to_clipboard(self):
        QApplication.clipboard().setText(self.model.get_flat_text())
        QMessageBox.information(self, "Clipboard", "UTF8 art exported successfully!")

    def _undo(self):
        self.status_bar.showMessage(self.model.undo())
        self._refresh_headers()

    def _redo(self):
        self.status_bar.showMessage(self.model.redo())
        self._refresh_headers()

    def _refresh_headers(self):
        self.line_numbers.update_numbers(self.model.rows)
        self.col_numbers.update_numbers(self.model.cols)

    def _save_to_file(self):
        if self.current_file_path:
            self._execute_save(self.current_file_path)
        else:
            self._save_as_to_file()

    def _save_as_to_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save UTF8 drawing as…", "",
            "Text files (*.txt);;All files (*.*)")
        if not filename:
            return
        self.current_file_path = filename
        self._execute_save(filename)

    def _execute_save(self, filename):
        err = self.model.save_to_file(filename)
        if err:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{err}")
        else:
            self.status_bar.showMessage(f"Saved: {os.path.basename(filename)}")

    def _load_from_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open UTF8 drawing…", "",
            "Text files (*.txt);;All files (*.*)")
        if not filename:
            return
        err = self.model.load_from_file(filename)
        if err:
            QMessageBox.critical(self, "Error", f"Could not load file:\n{err}")
        else:
            self.current_file_path = filename
            self._refresh_headers()
            self.status_bar.showMessage(f"Loaded: {os.path.basename(filename)}")

    def _show_about(self):
        QMessageBox.about(
            self, "About this editor",
            "Python UTF8 Block Designer — PyQt6 Edition\n"
            "Version 0.5\n\n"
            "Features:\n"
            "• Clean Model/View architecture\n"
            "• Three independent drawing layers\n"
            "• Tools: Pen, Box, Line, Text, Select, Stamp\n"
            "• YAML shape library\n"
            "• Undo/Redo, grid auto-expansion\n"
            "• Hotkeys: P/B/L/T/C, Ctrl+S/O/Z/Y, 1/2/3\n")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Python UTF8 Block Designer")
    app.setApplicationVersion("0.5")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
