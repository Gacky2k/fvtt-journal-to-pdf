from __future__ import annotations

import os
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QTreeWidget, QTreeWidgetItem
)

from fvtt_parser import parse_journal
from pdf_builder import build_pdf, Selection


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FVTT Journal → PDF (Compendium Export JSON)")

        self.pages = []
        self.current_path = None

        # UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_open = QtWidgets.QPushButton("Open Journal JSON…")
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_select_none = QtWidgets.QPushButton("Select None")
        self.btn_pdf = QtWidgets.QPushButton("Generate PDF…")
        self.btn_pdf.setEnabled(False)

        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_pdf)
        layout.addLayout(btn_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Content"])
        self.tree.setColumnCount(1)
        layout.addWidget(self.tree, 1)

        self.status = QtWidgets.QLabel("Open a Compendium Exporter JournalEntry JSON to begin.")
        layout.addWidget(self.status)

        # Signals
        self.btn_open.clicked.connect(self.open_json)
        self.btn_select_all.clicked.connect(lambda: self.set_all_checks(QtCore.Qt.Checked))
        self.btn_select_none.clicked.connect(lambda: self.set_all_checks(QtCore.Qt.Unchecked))
        self.btn_pdf.clicked.connect(self.generate_pdf)

    def open_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open JournalEntry JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            pages = parse_journal(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse JSON:\n{e}")
            return

        self.current_path = path
        self.pages = pages
        self.populate_tree()
        self.btn_pdf.setEnabled(True)
        self.status.setText(f"Loaded: {os.path.basename(path)}")

    def populate_tree(self):
        self.tree.clear()

        for page in self.pages:
            page_item = QTreeWidgetItem([page.title])
            page_item.setFlags(page_item.flags() | QtCore.Qt.ItemIsUserCheckable)
            page_item.setCheckState(0, QtCore.Qt.Unchecked)
            page_item.setData(0, QtCore.Qt.UserRole, ("page", page.title, None))

            # Headings under page
            for h in page.headings:
                h_item = QTreeWidgetItem([h.title])
                h_item.setFlags(h_item.flags() | QtCore.Qt.ItemIsUserCheckable)
                h_item.setCheckState(0, QtCore.Qt.Unchecked)
                h_item.setData(0, QtCore.Qt.UserRole, ("heading", page.title, h.title))
                page_item.addChild(h_item)

            self.tree.addTopLevelItem(page_item)
            page_item.setExpanded(True)

    def set_all_checks(self, state: QtCore.Qt.CheckState):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top.setCheckState(0, state)
            for j in range(top.childCount()):
                top.child(j).setCheckState(0, state)

    def collect_selection(self) -> Selection:
        items = []
        for i in range(self.tree.topLevelItemCount()):
            page_item = self.tree.topLevelItem(i)
            kind, page_title, _ = page_item.data(0, QtCore.Qt.UserRole)
            if page_item.checkState(0) == QtCore.Qt.Checked:
                items.append((page_title, None))
                continue

            for j in range(page_item.childCount()):
                h_item = page_item.child(j)
                _, p, h = h_item.data(0, QtCore.Qt.UserRole)
                if h_item.checkState(0) == QtCore.Qt.Checked:
                    items.append((p, h))

        return Selection(items=items)

    def generate_pdf(self):
        if not self.pages:
            return

        sel = self.collect_selection()
        if not sel.items:
            QMessageBox.information(self, "Nothing selected", "Select at least one page or heading.")
            return

        default_name = "export.pdf"
        if self.current_path:
            base = os.path.splitext(os.path.basename(self.current_path))[0]
            default_name = f"{base}.pdf"

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", default_name, "PDF Files (*.pdf)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        title = "Foundry Journal Export"
        try:
            build_pdf(out_path=out_path, title=title, pages=self.pages, selection=sel)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to build PDF:\n{e}")
            return

        QMessageBox.information(self, "Done", f"PDF created:\n{out_path}")


if __name__ == "__main__":
    app = QApplication([])
    w = MainWindow()
    w.resize(900, 650)
    w.show()
    app.exec()
