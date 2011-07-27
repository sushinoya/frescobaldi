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
Builds the LilyPond score from the settings in the Score Wizard.
"""

import __builtin__
import re

import ly.dom
import po.mofile

from . import parts
import parts._base



class PartData(object):
    """Represents what a Part wants to add to the LilyPond score.
    
    A Part may append to the following instance attributes (which are lists):
    
    includes:           (string) filename to be included
    codeblocks:         (ly.dom.Node) global blocks of code a part depends on
    assignments:        (ly.dom.Assignment) assignment of an expression to a
                        variable, most times the music stub for a part
    nodes:              (ly.dom.Node) the nodes a part adds to the parent \score
    afterblocks:        (ly.dom.Node) other blocks, appended ad the end
    
    The num instance attribute is set to 0 by default but can be increased by
    the Builder, when there are more parts of the exact same type in the same
    score.
    
    This is used by the builder afterwards to adjust identifiers and instrument
    names to this.
    
    """
    def __init__(self):
        self.num = 0
        self.includes = []
        self.codeblocks = []
        self.assignments = []
        self.nodes = []
        self.afterblocks = []
        
        



class Builder(object):
    """Builds the LilyPond score from all user input in the score wizard.
    
    Reads settings and other input from the dialog on construction.
    Does not need the dialog after that.
    
    """
    def __init__(self, dialog):
        """Initializes ourselves from all user settings in the dialog."""
        self._includeFiles = []
        
        generalPreferences = dialog.settings.widget().generalPreferences
        lilyPondPreferences = dialog.settings.widget().lilyPondPreferences
        instrumentNames = dialog.settings.widget().instrumentNames
        
        # attributes the Part and Container types may read and we need later as well
        self.header = dialog.header.widget().headers()
        self.headerDict = dict(self.header)
        self.lyVersionString = lilyPondPreferences.version.currentText().strip()
        self.lyVersion = tuple(map(int, re.findall('\\d+', self.lyVersionString)))
        self.midi = generalPreferences.midi.isChecked()
        self.pitchLanguage = dialog.pitchLanguage()
        self.suppressTagLine = generalPreferences.tagl.isChecked()
        self.removeBarNumbers = generalPreferences.barnum.isChecked()
        self.showMetronomeMark = generalPreferences.metro.isChecked()
        self.paperSize = generalPreferences.getPaperSize()
        self.paperLandscape = generalPreferences.paperLandscape.isChecked()
        self.showInstrumentNames = instrumentNames.isChecked()
        names = ['long', 'short', None]
        self.firstInstrumentName = names[instrumentNames.firstSystem.currentIndex()]
        self.otherInstrumentName = names[instrumentNames.otherSystems.currentIndex()]
        
        # translator for instrument names
        self._ = __builtin__._
        if instrumentNames.isChecked():
            lang = instrumentNames.getLanguage()
            if lang == 'C':
                self._ = po.translator(None)
            elif lang:
                mofile = po.find(lang)
                if mofile:
                    self._ = po.translator(po.mofile.MoFile(mofile))
        
        # printer that converts the ly.dom tree to text
        p = self._printer = ly.dom.Printer()
        p.indentString = "  " # will be re-indented anyway
        p.typographicalQuotes = generalPreferences.typq.isChecked()
        if self.pitchLanguage:
            p.language = self.pitchLanguage
        
        # get the parts
        globalGroup = dialog.parts.widget().parts()
        
        # move parts down the tree to subgroups that have no parts
        assignparts(globalGroup)
        
        # now prepare the different blocks
        # variable assignments
        self.assignments = ly.dom.Block()
        # the \score { }, \book { } etc. blocks
        self.scores = ly.dom.Block()
        # the aftermath, things that parts may add
        self.backmatter = ly.dom.Block()
        
        usePrefix = needsPrefix(globalGroup)
        groupCount = sum(1 for g in itergroups(globalGroup) if g and g.parts)
        
        def makeBlock(group, node):
            if group.part:
                node = group.part.makeNode(node)
            if group.parts:
                # add parts here, always in \score { }
                if not isinstance(node,ly.dom.Score):
                    node = ly.dom.Score(node)
                ly.dom.Layout(node)
                if self.midi:
                    midi = ly.dom.Midi(node)
                music = ly.dom.Simr()
                node.insert(0, music)
                # TODO: add the parts to the music << >>
                for p in group.parts:
                    ly.dom.Comment("Part {0}".format(p.part.title()), music)
            for g in group.groups:
                makeBlock(g, node)
                
        makeBlock(globalGroup, self.scores)
        
    def text(self, doc=None):
        """Return LilyPond formatted output. """
        return self.printer().indent(doc or self.document())
        
    def printer(self):
        """Returns a ly.dom.Printer, that converts the ly.dom structure to LilyPond text. """
        return self._printer
        
    def document(self):
        """Creates and returns a ly.dom tree representing the full LilyPond document."""
        doc = ly.dom.Document()
        
        # version
        ly.dom.Version(self.lyVersionString, doc)
        
        # language
        if self.pitchLanguage:
            if self.lyVersion >= (2, 13, 38):
                ly.dom.Line('\\language "{0}"'.format(self.pitchLanguage), doc)
            else:
                ly.dom.Include("{0}.ly".format(self.pitchLanguage), doc)
        ly.dom.BlankLine(doc)

        # other include files
        if self._includeFiles:
            for filename in self._includeFiles:
                ly.dom.Include(filename, doc)
            ly.dom.BlankLine(doc)
            
        # general header
        h = ly.dom.Header()
        for name, value in self.header:
            h[name] = value
        if 'tagline' not in h and self.suppressTagLine:
            ly.dom.Comment(_("Remove default LilyPond tagline"), h)
            h['tagline'] = ly.dom.Scheme('#f')
        if len(h):
            doc.append(h)
            ly.dom.BlankLine(doc)

        # paper size
        if self.paperSize:
            ly.dom.Scheme(
                '(set-paper-size "{0}"{1})'.format(
                    self.paperSize, " 'landscape" if self.paperLandscape else ""),
                ly.dom.Paper(doc)
            ).after = 1
            ly.dom.BlankLine(doc)

        # remove bar numbers
        if self.removeBarNumbers:
            ly.dom.Line('\\remove "Bar_number_engraver"',
                ly.dom.Context('Score',
                    ly.dom.Layout(doc)))
            ly.dom.BlankLine(doc)

        # add the main scores
        doc.append(self.scores)
        return doc


    def setMidiInstrument(self, node, midiInstrument):
        """Sets the MIDI instrument for the node, if the user wants MIDI output."""
        if self.midi:
            node.getWith()['midiInstrument'] = midiInstrument

    def setInstrumentNames(self, staff, longName, shortName):
        """Sets the instrument names to the staff (or group).
        
        longName and shortName may either be a string or a ly.dom.Node object (markup)
        The settings in the score wizard are honored.
        
        """
        if self.showInstrumentNames:
            staff.addInstrumentNameEngraverIfNecessary()
            w = staff.getWith()
            first = longName if self.firstInstrumentName == 'long' else shortName
            w['instrumentName'] = first
            if self.otherInstrumentName:
                other = longName if self.otherInstrumentName == 'long' else shortName
                # If these are markup objects, copy them otherwise the assignment
                # to shortInstrumentName takes it away from the instrumentName.
                if other is first and isinstance(first, ly.dom.Node):
                    other = other.copy()
                w['shortInstrumentName'] = other



def assignparts(group):
    """Moves the parts to sub-groups that contain no parts.
    
    If at least one subgroup uses the parts, the parent's parts are removed.
    This way a user can specify some parts and then multiple scores, and they will all
    use the same parts again.
    
    """
    partsOfParentUsed = False
    for g in group.groups:
        if not g.parts:
            g.parts = group.parts
            partsOfParentUsed = True
        assignparts(g)
    if partsOfParentUsed:
        group.parts = []


def itergroups(group):
    """Iterates over the group and its subgroups as an event list.
    
    When a group is yielded, it means the group starts.
    When None is yielded, it means that the last started groups ends.
    
    """
    yield group
    for g in group.groups:
        for i in itergroups(g):
            yield i
    yield None # end a group


def descendants(group):
    """Iterates over the descendants of a group (including the group itself).
    
    First the group, then its children, then the grandchildren, etc.
    
    """
    def _descendants(group):
        children = group.groups
        while children:
            new = []
            for g in children:
                yield g
                new.extend(g.groups)
            children = new
    yield group
    for g in _descendants(group):
        yield g


def needsPrefix(globalGroup):
    """Returns True if there are multiple scores in group with shared part types.
    
    This means the music assignments will need a prefix (e.g. scoreAsoprano,
    scoreBsoprano, etc.)
    
    """
    counter = {}    # collections.Counter() would be nice but requires Python 2.7
    for group in itergroups(globalGroup):
        if group:
            partTypes = set(type(g.part) for g in group.parts)
            for partType in partTypes:
                counter[partType] = counter.get(partType, 0) + 1
    return any(v for v in counter.values() if v > 1)


