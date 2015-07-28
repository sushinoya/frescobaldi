# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2014 by Wilbert Berendsen
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
The Manuscript viewer panel widget.
"""

from __future__ import unicode_literals

import os

from PyQt4.QtGui import QFileDialog, QMessageBox

import app
import sessions
import userguide.util
try:
    import popplerqt4
except ImportError:
    pass

import viewers
from viewers import documents
from . import contextmenu

class ManuscriptViewWidget(viewers.popplerwidget.AbstractPopplerWidget):
    def __init__(self, panel):
        """Widget holding a manuscript view."""
        super(ManuscriptViewWidget, self).__init__(panel)

    def translateUI(self):
        self.setWhatsThis(_(
            "<p>The Manuscript Viewer displays an original manuscript " +
            "one is copying from.</p>\n"
            "<p>See {link} for more information.</p>").format(link=
                userguide.util.format_link(self.parent().viewerName())))

    def connectSlots(self):
        super(ManuscriptViewWidget, self).connectSlots()
        ac = self.actionCollection

        # TODO: These actions have to be moved to the base class
        # (maybe also to the panel) and renamed to be harmonized with
        # the music_NN actions.
        # This method override can then be removed.
        ac.manuscript_open.triggered.connect(self.openManuscripts)
        ac.manuscript_close.triggered.connect(self.closeManuscript)
        ac.manuscript_close_other.triggered.connect(self.closeOtherManuscripts)
        ac.manuscript_close_all.triggered.connect(self.closeAllManuscripts)
        ac.music_document_select.documentsMissing.connect(self.reportMissingManuscripts)

    def createContextMenu(self):
        """Creates the context menu."""
        self._contextMenu = contextmenu.ManuscriptViewerContextMenu(self.parent())

    def openDocument(self, doc):
        """Opens a documents.Document instance."""
        try:
            super(ManuscriptViewWidget, self).openDocument(doc)
        except OSError:
            # remove manuscript if it can't be opened
            mds = self.actionCollection.music_document_select
            mds.removeManuscript(doc)

    def slotSessionChanged(self, name):
        if name:
            session = sessions.sessionGroup(name)
            manuscripts = session.value("manuscripts", "")
            active_manuscript = session.value("active-manuscript", None)
            if session.contains("urls"): # the session is not new
                self.closeAllManuscripts()
                ds = self.actionCollection.music_document_select
                if manuscripts:
                    for m in manuscripts:
                        doc = documents.Document(m[0])
                        self._positions[doc] = m[1]
                        ds.addManuscript(doc)
                if active_manuscript:
                    doc = documents.Document(active_manuscript[0])
                    self._positions[doc] = active_manuscript[1]
                    ds.addManuscript(doc)
                    self.view._centerPos = None

    def slotSaveSessionData(self):
        g = sessions.currentSessionGroup()
        if g:
            docs = self.actionCollection.music_document_select.documents()
            if docs:
                currentfile = self._currentDocument.filename()
                currpos = self.view.position()
                g.setValue("active-manuscript", (currentfile, currpos))
                pos = []
                for d in docs:
                    if d != self._currentDocument:
                        p = self._positions.get(d, (0, 0, 0))
                        pos.append((d.filename(), p))
                g.setValue("manuscripts", pos)
            else:
                g.setValue("active-manuscript", False)
                g.remove("manuscripts")


    def closeManuscript(self):
        """ Close current manuscript. """
        mds = self.actionCollection.music_document_select
        mds.removeManuscript(self._currentDocument)
        if len(mds.documents()) == 0:
            self.clear()

    def closeOtherManuscripts(self):
        """Close all manuscripts except the one currently opened"""
        mds = self.actionCollection.music_document_select
        mds.removeOtherManuscripts(self._currentDocument)

    def closeAllManuscripts(self):
        """Close all opened manuscripts"""
        mds = self.actionCollection.music_document_select
        mds.removeAllManuscripts()
        self.clear()

    def openManuscripts(self):
        """ Displays an open dialog to open a manuscript PDF. """
        caption = app.caption(_("dialog title", "Open Manuscript(s)"))
        directory = app.basedir()

        current_ms = self._currentDocument
        current_manuscript_document = current_ms.filename() if current_ms else None
        current_editor_document = self.parent().mainwindow().currentDocument().url().toLocalFile()
        directory = os.path.dirname(current_manuscript_document or current_editor_document or app.basedir())
        filenames = QFileDialog().getOpenFileNames(self, caption, directory, '*.pdf',)
        if filenames:
            self.actionCollection.music_document_select.loadManuscripts(filenames, filenames[-1])

    def reportMissingManuscripts(self, missing):
        """Report missing manuscript files when restoring a session."""
        report_msg = (_('The following file/s are/is missing and could not be loaded ' +
                     'when restoring a session:\n\n'))
        QMessageBox.warning(self, (_("Missing manuscript files")),
                                    report_msg + '\n'.join(missing))

    def slotShowDocument(self):
        """Bring the document to front that was selected from the context menu"""
        # TODO: Probably this has to go to the base class
        doc_filename = self.sender().checkedAction()._document_filename
        self.actionCollection.music_document_select.setActiveDocument(doc_filename)
