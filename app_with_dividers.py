# app_with_dividers.py
# FVTT Journal -> PDF (PySide6 GUI)
# Desktop app only: loads Foundry journal export ZIPs and generates a PDF.

from __future__ import annotations

import traceback
from typing import List, Optional, Tuple, Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fvtt_parser_with_images_and_zip import parse_journal
from pdf_builder_with_images import build_pdf, Selection


def _ensure_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _extract_page_headings(page) -> List[str]:
    # For tree UI: show heading titles if present
    hs = getattr(page, "headings", None) or []
    out = []
    for h in hs:
        t = getattr(h, "title", None)
        if t:
            out.append(t)
    return out


class BuildWorker(QThread):
    ok = Signal(str)
    fail = Signal(str)

    def __init__(self, out_path: str, title: str, journals: List[Any], selection: Selection, divider_pages: bool):
        super().__init__()
        self.out_path = out_path
        self.title = title
        self.journals = journals
        self.selection = selection
        self.divider_pages = divider_pages

    def run(self) -> None:
        try:
            build_pdf(
                out_path=self.out_path,
                title=self.title,
                journals=self.journals,
                selection=self.selection,
                divider_pages=self.divider_pages,
            )
            self.ok.emit(self.out_path)
        except Exception:
            self.fail.emit(traceback.format_exc())


class BusyDialog(QDialog):
    def __init__(self, parent=None, title="Working…", message="Building PDF…"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FVTT Journal → PDF")
        self.resize(1100, 700)

        self.journals: List[Any] = []
        self.divider_pages = True

        # UI
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        top = QHBoxLayout()
        self.btn_add = QPushButton("Open Journals (ZIP)…")
        self.btn_remove = QPushButton("Remove Selected Journal")
        self.btn_generate = QPushButton("Generate PDF…")
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_none = QPushButton("Select None")
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_remove)
        top.addStretch(1)
        top.addWidget(self.btn_select_all)
        top.addWidget(self.btn_select_none)
        top.addWidget(self.btn_generate)
        outer.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Table of Contents"])
        self.tree.setUniformRowHeights(True)
        outer.addWidget(self.tree, 1)

        self.lbl_status = QLabel("Load a ZIP export to begin.")
        outer.addWidget(self.lbl_status)

        # Wiring
        self.btn_add.clicked.connect(self.add_journals)
        self.btn_remove.clicked.connect(self.remove_selected_journal)
        self.btn_select_all.clicked.connect(lambda: self.set_all_checks(True))
        self.btn_select_none.clicked.connect(lambda: self.set_all_checks(False))
        self.btn_generate.clicked.connect(self.generate_pdf)

    def add_journals(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add journal export(s)",
            "",
            "FVTT Export ZIP (*.zip);;All Files (*)",
        )
        if not paths:
            return

        errors: List[str] = []
        for path in paths:
            try:
                parsed = parse_journal(path)
                for j in _ensure_list(parsed):
                    self.journals.append(j)
            except Exception as e:
                errors.append(f"{path}\n{e}")

        self.populate_tree()

        if errors:
            QMessageBox.warning(self, "Some files failed to load", "These exports could not be parsed:\n\n" + "\n\n".join(errors))

    def populate_tree(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            for j in self.journals:
                j_title = getattr(j, "title", "Journal")
                j_item = QTreeWidgetItem([j_title])
                j_item.setFlags(j_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                j_item.setCheckState(0, Qt.Checked)
                j_item.setData(0, Qt.UserRole, ("journal", j_title, None, None))
                self.tree.addTopLevelItem(j_item)

                for p in getattr(j, "pages", []) or []:
                    p_title = getattr(p, "title", "Page")
                    p_item = QTreeWidgetItem([p_title])
                    p_item.setFlags(p_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    p_item.setCheckState(0, Qt.Checked)
                    p_item.setData(0, Qt.UserRole, ("page", j_title, p_title, None))
                    j_item.addChild(p_item)

                    for h in _extract_page_headings(p):
                        h_item = QTreeWidgetItem([h])
                        h_item.setFlags(h_item.flags() | Qt.ItemIsUserCheckable)
                        h_item.setCheckState(0, Qt.Checked)
                        h_item.setData(0, Qt.UserRole, ("heading", j_title, p_title, h))
                        p_item.addChild(h_item)

                j_item.setExpanded(True)

            self.lbl_status.setText(f"Loaded {len(self.journals)} journal(s).")
        finally:
            self.tree.blockSignals(False)

    def set_all_checks(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                self.tree.topLevelItem(i).setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)

    def _selected_top_journal_index(self) -> Optional[int]:
        item = self.tree.currentItem()
        if not item:
            return None
        while item.parent():
            item = item.parent()
        idx = self.tree.indexOfTopLevelItem(item)
        return idx if idx >= 0 else None

    def remove_selected_journal(self) -> None:
        idx = self._selected_top_journal_index()
        if idx is None:
            return
        if 0 <= idx < len(self.journals):
            self.journals.pop(idx)
        self.populate_tree()

    def _gather_selection(self) -> Selection:
        sel_items: List[Tuple[str, str, Optional[str]]] = []

        def walk(it: QTreeWidgetItem):
            data = it.data(0, Qt.UserRole)
            if data and it.checkState(0) == Qt.Checked:
                kind, j_title, p_title, heading = data
                if kind == "page":
                    sel_items.append((j_title, p_title, None))
                elif kind == "heading":
                    sel_items.append((j_title, p_title, heading))
            for k in range(it.childCount()):
                walk(it.child(k))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

        return Selection(items=sel_items)

    def generate_pdf(self) -> None:
        if not self.journals:
            QMessageBox.information(self, "Nothing loaded", "Load at least one ZIP export first.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        title = self.journals[0].title if len(self.journals) == 1 else "FVTT Journals"
        selection = self._gather_selection()

        busy = BusyDialog(self)
        worker = BuildWorker(out_path, title, self.journals, selection, divider_pages=self.divider_pages)

        def ok(p: str):
            busy.accept()
            QMessageBox.information(self, "PDF created", f"Saved:\n{p}")

        def fail(err: str):
            busy.accept()
            QMessageBox.critical(self, "Failed to build PDF", err)

        worker.ok.connect(ok)
        worker.fail.connect(fail)
        worker.start()
        busy.exec()


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
