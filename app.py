from __future__ import annotations

import os
from typing import Any, Optional, Tuple, List

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from fvtt_parser import parse_journal
from pdf_builder import build_pdf, Selection


class MainWindow(QMainWindow):
    """
    Multi-journal version:
      - Add Journals... (multi-select)
      - Tree: Journal -> Page -> Heading (with checkboxes on pages/headings)
      - Reorder journals with Move Up/Down
      - Remove selected journal
      - Generate one combined PDF (journals in UI order)
      - Optional divider pages between journals (default ON)
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FVTT Journal → PDF (Compendium Export JSON)")

        # Each entry: {"title": str, "pages": List[PageNode], "path": str}
        self.journals: List[dict[str, Any]] = []

        # UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Add Journals…")
        self.btn_remove = QtWidgets.QPushButton("Remove Selected Journal")
        self.btn_up = QtWidgets.QPushButton("Move Journal Up")
        self.btn_down = QtWidgets.QPushButton("Move Journal Down")
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_select_none = QtWidgets.QPushButton("Select None")
        self.btn_pdf = QtWidgets.QPushButton("Generate PDF…")
        self.btn_pdf.setEnabled(False)

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_up)
        btn_row.addWidget(self.btn_down)
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_pdf)
        layout.addLayout(btn_row)

        # Options row
        opt_row = QtWidgets.QHBoxLayout()
        self.chk_dividers = QtWidgets.QCheckBox("Insert divider pages between journals")
        self.chk_dividers.setChecked(True)  # default ON
        opt_row.addWidget(self.chk_dividers)
        opt_row.addStretch(1)
        layout.addLayout(opt_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Content"])
        self.tree.setColumnCount(1)
        layout.addWidget(self.tree, 1)

        self.status = QtWidgets.QLabel("Add one or more Compendium Exporter JournalEntry JSON files to begin.")
        layout.addWidget(self.status)

        # Signals
        self.btn_add.clicked.connect(self.add_journals)
        self.btn_remove.clicked.connect(self.remove_selected_journal)
        self.btn_up.clicked.connect(lambda: self.move_selected_journal(-1))
        self.btn_down.clicked.connect(lambda: self.move_selected_journal(+1))
        self.btn_select_all.clicked.connect(lambda: self.set_all_checks(QtCore.Qt.Checked))
        self.btn_select_none.clicked.connect(lambda: self.set_all_checks(QtCore.Qt.Unchecked))
        self.btn_pdf.clicked.connect(self.generate_pdf)

    # ---------- Journal loading / ordering ----------

    def add_journals(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add JournalEntry JSON files", "", "JSON Files (*.json)"
        )
        if not paths:
            return

        added = 0
        for path in paths:
            try:
                journal_title, pages = self._parse_journal_compat(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to parse:\n{path}\n\n{e}")
                continue

            journal_title = self._dedupe_title(journal_title)
            self.journals.append({"title": journal_title, "pages": pages, "path": path})
            added += 1

        if added:
            self.populate_tree()
            self.btn_pdf.setEnabled(len(self.journals) > 0)
            self.status.setText(f"Loaded {len(self.journals)} journal(s).")


    def _parse_journal_compat(self, path: str) -> Tuple[str, Any]:
        """Compatibility helper:
        - New parse_journal returns (journal_title, pages)
        - Old parse_journal returns pages only
        """
        result = parse_journal(path)
        if isinstance(result, tuple) and len(result) == 2:
            journal_title, pages = result
            if not journal_title:
                journal_title = os.path.splitext(os.path.basename(path))[0]
            return str(journal_title), pages

        # Back-compat: result is pages list
        pages = result
        journal_title = os.path.splitext(os.path.basename(path))[0]
        return journal_title, pages


    def _dedupe_title(self, title: str) -> str:
        base = title.strip() or "Journal"
        existing = {j["title"] for j in self.journals}
        if base not in existing:
            return base
        i = 2
        while f"{base} ({i})" in existing:
            i += 1
        return f"{base} ({i})"


    def _selected_journal_title(self) -> Optional[str]:
        item = self.tree.currentItem()
        if not item:
            return None

        # Climb to top-level journal node
        while item.parent() is not None:
            item = item.parent()

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return None
        if isinstance(data, tuple) and len(data) >= 2 and data[0] == "journal":
            return data[1]
        return None


    def remove_selected_journal(self):
        title = self._selected_journal_title()
        if not title:
            QMessageBox.information(self, "Select a journal", "Click a journal (top-level) to remove it.")
            return

        self.journals = [j for j in self.journals if j["title"] != title]
        self.populate_tree()
        self.btn_pdf.setEnabled(len(self.journals) > 0)
        self.status.setText(f"Loaded {len(self.journals)} journal(s).")


    def move_selected_journal(self, direction: int):
        title = self._selected_journal_title()
        if not title:
            QMessageBox.information(self, "Select a journal", "Click a journal (top-level) to move it.")
            return

        idx = next((i for i, j in enumerate(self.journals) if j["title"] == title), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.journals):
            return

        self.journals[idx], self.journals[new_idx] = self.journals[new_idx], self.journals[idx]
        self.populate_tree()


    # ---------- Tree ----------

    def populate_tree(self):
        self.tree.clear()

        for j in self.journals:
            j_title = j["title"]
            j_item = QTreeWidgetItem([j_title])
            j_item.setData(0, QtCore.Qt.UserRole, ("journal", j_title))
            j_item.setExpanded(True)

            for page in j["pages"]:
                page_item = QTreeWidgetItem([page.title])
                page_item.setFlags(page_item.flags() | QtCore.Qt.ItemIsUserCheckable)
                page_item.setCheckState(0, QtCore.Qt.Unchecked)
                page_item.setData(0, QtCore.Qt.UserRole, ("page", j_title, page.title, None))

                for h in page.headings:
                    h_item = QTreeWidgetItem([h.title])
                    h_item.setFlags(h_item.flags() | QtCore.Qt.ItemIsUserCheckable)
                    h_item.setCheckState(0, QtCore.Qt.Unchecked)
                    h_item.setData(0, QtCore.Qt.UserRole, ("heading", j_title, page.title, h.title))
                    page_item.addChild(h_item)

                j_item.addChild(page_item)

            self.tree.addTopLevelItem(j_item)

        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))


    def set_all_checks(self, state: QtCore.Qt.CheckState):
        # Only pages/headings are checkable; journals are containers.
        for i in range(self.tree.topLevelItemCount()):
            j_item = self.tree.topLevelItem(i)
            for p in range(j_item.childCount()):
                page_item = j_item.child(p)
                page_item.setCheckState(0, state)
                for h in range(page_item.childCount()):
                    page_item.child(h).setCheckState(0, state)


    def collect_selection(self) -> Selection:
        items = []
        for i in range(self.tree.topLevelItemCount()):
            j_item = self.tree.topLevelItem(i)

            for p in range(j_item.childCount()):
                page_item = j_item.child(p)
                data = page_item.data(0, QtCore.Qt.UserRole)  # ("page", journal, page, None)
                if not data or data[0] != "page":
                    continue
                _, j, page_title, _ = data

                if page_item.checkState(0) == QtCore.Qt.Checked:
                    items.append((j, page_title, None))
                    continue

                for h in range(page_item.childCount()):
                    h_item = page_item.child(h)
                    hdata = h_item.data(0, QtCore.Qt.UserRole)  # ("heading", journal, page, heading)
                    if (
                        h_item.checkState(0) == QtCore.Qt.Checked
                        and hdata
                        and hdata[0] == "heading"
                    ):
                        _, jj, pp, hh = hdata
                        items.append((jj, pp, hh))

        return Selection(items=items)


    # ---------- PDF ----------

    def generate_pdf(self):
        if not self.journals:
            return

        sel = self.collect_selection()
        if not sel.items:
            QMessageBox.information(self, "Nothing selected", "Select at least one page or heading.")
            return

        if len(self.journals) == 1:
            base = os.path.splitext(os.path.basename(self.journals[0]["path"]))[0]
            default_name = f"{base}.pdf"
        else:
            default_name = "combined.pdf"

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", default_name, "PDF Files (*.pdf)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        title = "Foundry Journal Export"
        try:
            journals_payload = [(j["title"], j["pages"]) for j in self.journals]
            build_pdf(
                out_path=out_path,
                title=title,
                journals=journals_payload,
                selection=sel,
                divider_pages=self.chk_dividers.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to build PDF:\n{e}")
            return

        QMessageBox.information(self, "Done", f"PDF created:\n{out_path}")


if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.resize(1100, 740)
    w.show()
    app.exec()
