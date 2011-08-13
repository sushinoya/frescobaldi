# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2011 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
The PDF preview panel.

This file loads even if popplerqt4 is absent, although the PDF preview
panel only shows a message about missing the popplerqt4 module.

The widget module contains the real widget, the documents module a simple
abstraction and caching of Poppler documents with their filename,
and the printing module contains code to print a Poppler document, either
via a PostScript rendering or by printing raster images to a QPrinter.

All the point & click stuff is handled in the pointandclick module.

"""

from __future__ import unicode_literals

import os
import weakref

from PyQt4.QtCore import Qt, pyqtSignal
from PyQt4.QtGui import (
    QAction, QComboBox, QLabel, QMessageBox, QPalette, QKeySequence,
    QWidgetAction)

import app
import actioncollection
import actioncollectionmanager
import icons
import panels
import resultfiles
import jobattributes

from . import documents


# default zoom percentages
_zoomvalues = [50, 75, 100, 125, 150, 175, 200, 250, 300]

# viewModes from qpopplerview:
from qpopplerview import FixedScale, FitWidth, FitHeight, FitBoth


class MusicViewPanel(panels.Panel):
    def __init__(self, mainwindow):
        super(MusicViewPanel, self).__init__(mainwindow)
        self.toggleViewAction().setShortcut(QKeySequence("Meta+Alt+M"))
        mainwindow.addDockWidget(Qt.RightDockWidgetArea, self)
        
        ac = self.actionCollection = Actions(self)
        actioncollectionmanager.manager(mainwindow).addActionCollection(ac)
        ac.music_print.triggered.connect(self.printMusic)
        ac.music_zoom_in.triggered.connect(self.zoomIn)
        ac.music_zoom_out.triggered.connect(self.zoomOut)
        ac.music_zoom_combo.zoomChanged.connect(self.slotZoomChanged)
        ac.music_fit_width.triggered.connect(self.fitWidth)
        ac.music_fit_height.triggered.connect(self.fitHeight)
        ac.music_fit_both.triggered.connect(self.fitBoth)
        ac.music_jump_to_cursor.triggered.connect(self.jumpToCursor)
        ac.music_document_select.currentDocumentChanged.connect(self.openDocument)
        ac.music_document_select.documentClosed.connect(self.closeDocument)
        ac.music_document_select.documentsChanged.connect(self.updateActions)
        
    def translateUI(self):
        self.setWindowTitle(_("window title", "Music View"))
        self.toggleViewAction().setText(_("&Music View"))
    
    def createWidget(self):
        import widget
        w = widget.MusicView(self)
        w.zoomChanged.connect(self.slotMusicZoomChanged)
        w.updateZoomInfo()
        return w
        
    def openDocument(self, doc):
        """Opens the documents.Document instance (wrapping a lazily loaded Poppler document)."""
        self.widget().openDocument(doc)
    
    def closeDocument(self):
        self.widget().clear()
        
    def updateActions(self):
        ac = self.actionCollection
        ac.music_print.setEnabled(bool(ac.music_document_select.documents()))
        
    def printMusic(self):
        doc = self.actionCollection.music_document_select.currentDocument()
        if doc and doc.document():
            import popplerprint
            popplerprint.printDocument(doc, self)
    
    def zoomIn(self):
        self.widget().view.zoomIn()
    
    def zoomOut(self):
        self.widget().view.zoomOut()
    
    def fitWidth(self):
        self.widget().view.setViewMode(FitWidth)
    
    def fitHeight(self):
        self.widget().view.setViewMode(FitHeight)

    def fitBoth(self):
        self.widget().view.setViewMode(FitBoth)
    
    def jumpToCursor(self):
        self.activate()
        self.widget().showCurrentLinks()
    
    def slotZoomChanged(self, mode, scale):
        """Called when the combobox is changed, changes view zoom."""
        if mode == FixedScale:
            self.widget().view.zoom(scale)
        else:
            self.widget().view.setViewMode(mode)
    
    def slotMusicZoomChanged(self, mode, scale):
        """Called when the music view is changed, updates the toolbar actions."""
        ac = self.actionCollection
        ac.music_fit_width.setChecked(mode == FitWidth)
        ac.music_fit_height.setChecked(mode == FitHeight)
        ac.music_fit_both.setChecked(mode == FitBoth)
        ac.music_zoom_combo.updateZoomInfo(mode, scale)
        

class Actions(actioncollection.ActionCollection):
    name = "musicview"
    def createActions(self, panel):
        self.music_document_select = DocumentChooserAction(panel)
        self.music_print = QAction(panel)
        self.music_zoom_in = QAction(panel)
        self.music_zoom_out = QAction(panel)
        self.music_zoom_combo = ZoomerAction(panel)
        self.music_fit_width = QAction(panel)
        self.music_fit_height = QAction(panel)
        self.music_fit_both = QAction(panel)
        self.music_jump_to_cursor = QAction(panel)
        
        self.music_fit_width.setCheckable(True)
        self.music_fit_height.setCheckable(True)
        self.music_fit_both.setCheckable(True)

        self.music_print.setIcon(icons.get('document-print'))
        self.music_zoom_in.setIcon(icons.get('zoom-in'))
        self.music_zoom_out.setIcon(icons.get('zoom-out'))
        self.music_fit_width.setIcon(icons.get('zoom-fit-width'))
        self.music_fit_height.setIcon(icons.get('zoom-fit-height'))
        self.music_fit_both.setIcon(icons.get('zoom-fit-best'))
        self.music_jump_to_cursor.setIcon(icons.get('go-jump'))
        
        self.music_document_select.setShortcut(QKeySequence(Qt.SHIFT | Qt.CTRL | Qt.Key_O))
        self.music_print.setShortcuts(QKeySequence.Print)
        self.music_zoom_in.setShortcuts(QKeySequence.ZoomIn)
        self.music_zoom_out.setShortcuts(QKeySequence.ZoomOut)
        self.music_jump_to_cursor.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_J))
        
    def translateUI(self):
        self.music_document_select.setText(_("Select Music View Document"))
        self.music_print.setText(_("&Print Music..."))
        self.music_zoom_in.setText(_("Zoom &In"))
        self.music_zoom_out.setText(_("Zoom &Out"))
        self.music_zoom_combo.setText(_("Zoom Music"))
        self.music_fit_width.setText(_("Fit &Width"))
        self.music_fit_height.setText(_("Fit &Height"))
        self.music_fit_both.setText(_("Fit &Page"))
        self.music_jump_to_cursor.setText(_("&Jump to Cursor Position"))


class ComboBoxAction(QWidgetAction):
    """A widget action that opens a combobox widget popup when triggered."""
    def __init__(self, panel):
        super(ComboBoxAction, self).__init__(panel)
        self.triggered.connect(self.showPopup)
        
    def showPopup(self):
        """Called when our action is triggered by a keyboard shortcut."""
        # find the widget in our floating panel, if available there
        for w in self.createdWidgets():
            if w.window() == self.parent():
                w.showPopup()
                return
        # find the one in the main window
        for w in self.createdWidgets():
            if w.window() == self.parent().mainwindow():
                w.showPopup()
                return
    

class DocumentChooserAction(ComboBoxAction):
    """A ComboBoxAction that keeps track of the current text document.
    
    It manages the list of generated PDF documents for every text document.
    If the mainwindow changes its current document and there are PDFs to display,
    it switches the current document.
    
    It also switches to a text document if a job finished for that document,
    and it generated new PDF documents.
    
    """
    
    documentClosed = pyqtSignal()
    documentsChanged = pyqtSignal()
    currentDocumentChanged = pyqtSignal(documents.Document)
    
    def __init__(self, panel):
        super(DocumentChooserAction, self).__init__(panel)
        self._document = None
        self._documents = []
        self._currentIndex = -1
        self._indices = weakref.WeakKeyDictionary()
        panel.mainwindow().currentDocumentChanged.connect(self.slotDocumentChanged)
        documents.documentUpdated.connect(self.slotDocumentUpdated)
        
    def createWidget(self, parent):
        return DocumentChooser(self, parent)
    
    def slotDocumentChanged(self, doc):
        """Called when the mainwindow changes its current document."""
        # only switch our document if there are PDF documents to display
        if self._document is None or documents.group(doc).documents():
            self.setCurrentDocument(doc)
    
    def slotDocumentUpdated(self, doc, job):
        """Called when a Job, finished on the document, has created new PDFs."""
        if (doc == self._document or
                jobattributes.get(job).mainwindow == self.parent().mainwindow()):
            self.setCurrentDocument(doc)
    
    def setCurrentDocument(self, document):
        """Displays the DocumentGroup of the given text Document in our chooser."""
        prev = self._document
        self._document = document
        if prev:
            prev.loaded.disconnect(self.updateDocument)
            prev.closed.disconnect(self.closeDocument)
            self._indices[prev] = self._currentIndex
        document.loaded.connect(self.updateDocument)
        document.closed.connect(self.closeDocument)
        self.updateDocument()
        
    def updateDocument(self):
        """(Re)read the output documents of the current document and show them."""
        docs = self._documents = documents.group(self._document).documents()
        self.setVisible(bool(docs))
        self.setEnabled(bool(docs))
        for w in self.createdWidgets():
            w.updateContents(self)
        
        index = self._indices.get(self._document, 0)
        if index < 0 or index >= len(docs):
            index = 0
        self.documentsChanged.emit()
        self.setCurrentIndex(index)
    
    def closeDocument(self):
        """Called when the current document is closed by the user."""
        self._document = None
        self._documents = []
        self._currentIndex = -1
        self.setVisible(False)
        self.setEnabled(False)
        self.documentClosed.emit()
        self.documentsChanged.emit()
        
    def documents(self):
        return self._documents
        
    def setCurrentIndex(self, index):
        if self._documents:
            self._currentIndex = index
            for w in self.createdWidgets():
                w.setCurrentIndex(index)
            self.currentDocumentChanged.emit(self._documents[index])
    
    def currentIndex(self):
        return self._currentIndex
    
    def currentDocument(self):
        """Returns the currently selected Music document (Note: NOT the text document!)"""
        if self._documents:
            return self._documents[self._currentIndex]


class DocumentChooser(QComboBox):
    def __init__(self, action, parent):
        super(DocumentChooser, self).__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setFocusPolicy(Qt.NoFocus)
        self.activated[int].connect(action.setCurrentIndex)
        self.updateContents(action)
        app.translateUI(self)
        
    def translateUI(self):
        self.setToolTip(_("Choose the PDF document to display."))

    def updateContents(self, action):
        self.clear()
        self.addItems([os.path.basename(doc.filename()) for doc in action.documents()])
        self.setCurrentIndex(action.currentIndex())


class ZoomerAction(ComboBoxAction):
    zoomChanged = pyqtSignal(int, float)
    
    def createWidget(self, parent):
        return Zoomer(self, parent)
    
    def setCurrentIndex(self, index):
        """Called when a user manipulates a Zoomer combobox.
        
        Updates the other widgets and calls the corresponding method of the panel.
        
        """
        for w in self.createdWidgets():
            w.setCurrentIndex(index)
        if index == 0:
            self.zoomChanged.emit(FitWidth, 0)
        elif index == 1:
            self.zoomChanged.emit(FitHeight, 0)
        elif index == 2:
            self.zoomChanged.emit(FitBoth, 0)
        else:
            self.zoomChanged.emit(FixedScale, _zoomvalues[index-3] / 100.0)
    
    def updateZoomInfo(self, mode, scale):
        """Connect view.viewModeChanged and layout.scaleChanged to this."""
        if mode == FixedScale:
            text = "{0:.0f}%".format(round(scale * 100.0))
            for w in self.createdWidgets():
                w.setEditText(text)
        else:
            if mode == FitWidth:
                index = 0
            elif mode == FitHeight:
                index = 1
            else: # qpopplerview.FitBoth:
                index = 2
            for w in self.createdWidgets():
                w.setCurrentIndex(index)


class Zoomer(QComboBox):
    def __init__(self, action, parent):
        super(Zoomer, self).__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.activated[int].connect(action.setCurrentIndex)
        self.addItems(['']*3)
        self.addItems(list(map("{0}%".format, _zoomvalues)))
        self.setMaxVisibleItems(20)
        app.translateUI(self)
    
    def translateUI(self):
        self.setItemText(0, _("Fit Width"))
        self.setItemText(1, _("Fit Height"))
        self.setItemText(2, _("Fit Page"))
        

