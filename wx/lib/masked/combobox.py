#----------------------------------------------------------------------------
# Name:         masked.combobox.py
# Authors:      Will Sadkin
# Email:        wsadkin@nameconnector.com
# Created:      02/11/2003
# Copyright:    (c) 2003 by Will Sadkin, 2003
# RCS-ID:       $Id$
# License:      wxWidgets license
#----------------------------------------------------------------------------
#
# This masked edit class allows for the semantics of masked controls
# to be applied to combo boxes.
#
#----------------------------------------------------------------------------

import  wx
from wx.lib.masked import *

# jmg 12/9/03 - when we cut ties with Py 2.2 and earlier, this would
# be a good place to implement the 2.3 logger class
from wx.tools.dbg import Logger
dbg = Logger()
##dbg(enable=0)

## ---------- ---------- ---------- ---------- ---------- ---------- ----------
## Because calling SetSelection programmatically does not fire EVT_COMBOBOX
## events, we have to do it ourselves when we auto-complete.
class MaskedComboBoxSelectEvent(wx.PyCommandEvent):
    def __init__(self, id, selection = 0, object=None):
        wx.PyCommandEvent.__init__(self, wx.wxEVT_COMMAND_COMBOBOX_SELECTED, id)

        self.__selection = selection
        self.SetEventObject(object)

    def GetSelection(self):
        """Retrieve the value of the control at the time
        this event was generated."""
        return self.__selection


class BaseMaskedComboBox( wx.ComboBox, MaskedEditMixin ):
    """
    This masked edit control adds the ability to use a masked input
    on a combobox, and do auto-complete of such values.
    """
    def __init__( self, parent, id=-1, value = '',
                  pos = wx.DefaultPosition,
                  size = wx.DefaultSize,
                  choices = [],
                  style = wx.CB_DROPDOWN,
                  validator = wx.DefaultValidator,
                  name = "maskedComboBox",
                  setupEventHandling = True,        ## setup event handling by default):
                  **kwargs):


        # This is necessary, because wxComboBox currently provides no
        # method for determining later if this was specified in the
        # constructor for the control...
        self.__readonly = style & wx.CB_READONLY == wx.CB_READONLY

        kwargs['choices'] = choices                 ## set up maskededit to work with choice list too

        ## Since combobox completion is case-insensitive, always validate same way
        if not kwargs.has_key('compareNoCase'):
            kwargs['compareNoCase'] = True

        MaskedEditMixin.__init__( self, name, **kwargs )

        self._choices = self._ctrl_constraints._choices
##        dbg('self._choices:', self._choices)

        if self._ctrl_constraints._alignRight:
            choices = [choice.rjust(self._masklength) for choice in choices]
        else:
            choices = [choice.ljust(self._masklength) for choice in choices]

        wx.ComboBox.__init__(self, parent, id, value='',
                            pos=pos, size = size,
                            choices=choices, style=style|wx.WANTS_CHARS,
                            validator=validator,
                            name=name)

        self.controlInitialized = True

        # Set control font - fixed width by default
        self._setFont()

        if self._autofit:
            self.SetClientSize(self._CalcSize())
            self.SetSizeHints(self.GetSize())

        if value:
            # ensure value is width of the mask of the control:
            if self._ctrl_constraints._alignRight:
                value = value.rjust(self._masklength)
            else:
                value = value.ljust(self._masklength)

        if self.__readonly:
            self.SetStringSelection(value)
        else:
            self._SetInitialValue(value)


        self._SetKeycodeHandler(wx.WXK_UP, self.OnSelectChoice)
        self._SetKeycodeHandler(wx.WXK_DOWN, self.OnSelectChoice)

        if setupEventHandling:
            ## Setup event handlers
            self.Bind(wx.EVT_SET_FOCUS, self._OnFocus )         ## defeat automatic full selection
            self.Bind(wx.EVT_KILL_FOCUS, self._OnKillFocus )    ## run internal validator
            self.Bind(wx.EVT_LEFT_DCLICK, self._OnDoubleClick)  ## select field under cursor on dclick
            self.Bind(wx.EVT_RIGHT_UP, self._OnContextMenu )    ## bring up an appropriate context menu
            self.Bind(wx.EVT_CHAR, self._OnChar )               ## handle each keypress
            self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown )         ## for special processing of up/down keys
            self.Bind(wx.EVT_KEY_DOWN, self._OnKeyDown )        ## for processing the rest of the control keys
                                                                ## (next in evt chain)
            self.Bind(wx.EVT_TEXT, self._OnTextChange )         ## color control appropriately & keep
                                                                ## track of previous value for undo



    def __repr__(self):
        return "<MaskedComboBox: %s>" % self.GetValue()


    def _CalcSize(self, size=None):
        """
        Calculate automatic size if allowed; augment base mixin function
        to account for the selector button.
        """
        size = self._calcSize(size)
        return (size[0]+20, size[1])


    def _GetSelection(self):
        """
        Allow mixin to get the text selection of this control.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        return self.GetMark()

    def _SetSelection(self, sel_start, sel_to):
        """
        Allow mixin to set the text selection of this control.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        return self.SetMark( sel_start, sel_to )


    def _GetInsertionPoint(self):
        return self.GetInsertionPoint()

    def _SetInsertionPoint(self, pos):
        self.SetInsertionPoint(pos)


    def _GetValue(self):
        """
        Allow mixin to get the raw value of the control with this function.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        return self.GetValue()

    def _SetValue(self, value):
        """
        Allow mixin to set the raw value of the control with this function.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        # For wxComboBox, ensure that values are properly padded so that
        # if varying length choices are supplied, they always show up
        # in the window properly, and will be the appropriate length
        # to match the mask:
        if self._ctrl_constraints._alignRight:
            value = value.rjust(self._masklength)
        else:
            value = value.ljust(self._masklength)

        # Record current selection and insertion point, for undo
        self._prevSelection = self._GetSelection()
        self._prevInsertionPoint = self._GetInsertionPoint()
        wx.ComboBox.SetValue(self, value)
        # text change events don't always fire, so we check validity here
        # to make certain formatting is applied:
        self._CheckValid()

    def SetValue(self, value):
        """
        This function redefines the externally accessible .SetValue to be
        a smart "paste" of the text in question, so as not to corrupt the
        masked control.  NOTE: this must be done in the class derived
        from the base wx control.
        """
        if not self._mask:
            wx.ComboBox.SetValue(value)   # revert to base control behavior
            return
        # else...
        # empty previous contents, replacing entire value:
        self._SetInsertionPoint(0)
        self._SetSelection(0, self._masklength)

        if( len(value) < self._masklength                # value shorter than control
            and (self._isFloat or self._isInt)            # and it's a numeric control
            and self._ctrl_constraints._alignRight ):   # and it's a right-aligned control
            # try to intelligently "pad out" the value to the right size:
            value = self._template[0:self._masklength - len(value)] + value
##            dbg('padded value = "%s"' % value)

        # For wxComboBox, ensure that values are properly padded so that
        # if varying length choices are supplied, they always show up
        # in the window properly, and will be the appropriate length
        # to match the mask:
        elif self._ctrl_constraints._alignRight:
            value = value.rjust(self._masklength)
        else:
            value = value.ljust(self._masklength)


        # make SetValue behave the same as if you had typed the value in:
        try:
            value, replace_to = self._Paste(value, raise_on_invalid=True, just_return_value=True)
            if self._isFloat:
                self._isNeg = False     # (clear current assumptions)
                value = self._adjustFloat(value)
            elif self._isInt:
                self._isNeg = False     # (clear current assumptions)
                value = self._adjustInt(value)
            elif self._isDate and not self.IsValid(value) and self._4digityear:
                value = self._adjustDate(value, fixcentury=True)
        except ValueError:
            # If date, year might be 2 digits vs. 4; try adjusting it:
            if self._isDate and self._4digityear:
                dateparts = value.split(' ')
                dateparts[0] = self._adjustDate(dateparts[0], fixcentury=True)
                value = string.join(dateparts, ' ')
##                dbg('adjusted value: "%s"' % value)
                value = self._Paste(value, raise_on_invalid=True, just_return_value=True)
            else:
                raise

        self._SetValue(value)
####        dbg('queuing insertion after .SetValue', replace_to)
        wx.CallAfter(self._SetInsertionPoint, replace_to)
        wx.CallAfter(self._SetSelection, replace_to, replace_to)


    def _Refresh(self):
        """
        Allow mixin to refresh the base control with this function.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        wx.ComboBox.Refresh(self)

    def Refresh(self):
        """
        This function redefines the externally accessible .Refresh() to
        validate the contents of the masked control as it refreshes.
        NOTE: this must be done in the class derived from the base wx control.
        """
        self._CheckValid()
        self._Refresh()


    def _IsEditable(self):
        """
        Allow mixin to determine if the base control is editable with this function.
        REQUIRED by any class derived from MaskedEditMixin.
        """
        return not self.__readonly


    def Cut(self):
        """
        This function redefines the externally accessible .Cut to be
        a smart "erase" of the text in question, so as not to corrupt the
        masked control.  NOTE: this must be done in the class derived
        from the base wx control.
        """
        if self._mask:
            self._Cut()             # call the mixin's Cut method
        else:
            wx.ComboBox.Cut(self)    # else revert to base control behavior


    def Paste(self):
        """
        This function redefines the externally accessible .Paste to be
        a smart "paste" of the text in question, so as not to corrupt the
        masked control.  NOTE: this must be done in the class derived
        from the base wx control.
        """
        if self._mask:
            self._Paste()           # call the mixin's Paste method
        else:
            wx.ComboBox.Paste(self)  # else revert to base control behavior


    def Undo(self):
        """
        This function defines the undo operation for the control. (The default
        undo is 1-deep.)
        """
        if self._mask:
            self._Undo()
        else:
            wx.ComboBox.Undo()       # else revert to base control behavior


    def Append( self, choice, clientData=None ):
        """
        This function override is necessary so we can keep track of any additions to the list
        of choices, because wxComboBox doesn't have an accessor for the choice list.
        The code here is the same as in the SetParameters() mixin function, but is
        done for the individual value as appended, so the list can be built incrementally
        without speed penalty.
        """
        if self._mask:
            if type(choice) not in (types.StringType, types.UnicodeType):
                raise TypeError('%s: choices must be a sequence of strings' % str(self._index))
            elif not self.IsValid(choice):
                raise ValueError('%s: "%s" is not a valid value for the control as specified.' % (str(self._index), choice))

            if not self._ctrl_constraints._choices:
                self._ctrl_constraints._compareChoices = []
                self._ctrl_constraints._choices = []
                self._hasList = True

            compareChoice = choice.strip()

            if self._ctrl_constraints._compareNoCase:
                compareChoice = compareChoice.lower()

            if self._ctrl_constraints._alignRight:
                choice = choice.rjust(self._masklength)
            else:
                choice = choice.ljust(self._masklength)
            if self._ctrl_constraints._fillChar != ' ':
                choice = choice.replace(' ', self._fillChar)
##            dbg('updated choice:', choice)


            self._ctrl_constraints._compareChoices.append(compareChoice)
            self._ctrl_constraints._choices.append(choice)
            self._choices = self._ctrl_constraints._choices     # (for shorthand)

            if( not self.IsValid(choice) and
               (not self._ctrl_constraints.IsEmpty(choice) or
                (self._ctrl_constraints.IsEmpty(choice) and self._ctrl_constraints._validRequired) ) ):
                raise ValueError('"%s" is not a valid value for the control "%s" as specified.' % (choice, self.name))

        wx.ComboBox.Append(self, choice, clientData)



    def Clear( self ):
        """
        This function override is necessary so we can keep track of any additions to the list
        of choices, because wxComboBox doesn't have an accessor for the choice list.
        """
        if self._mask:
            self._choices = []
            self._ctrl_constraints._autoCompleteIndex = -1
            if self._ctrl_constraints._choices:
                self.SetCtrlParameters(choices=[])
        wx.ComboBox.Clear(self)


    def _OnCtrlParametersChanged(self):
        """
        Override mixin's default OnCtrlParametersChanged to detect changes in choice list, so
        we can update the base control:
        """
        if self.controlInitialized and self._choices != self._ctrl_constraints._choices:
            wx.ComboBox.Clear(self)
            self._choices = self._ctrl_constraints._choices
            for choice in self._choices:
                wx.ComboBox.Append( self, choice )


    def GetMark(self):
        """
        This function is a hack to make up for the fact that wxComboBox has no
        method for returning the selected portion of its edit control.  It
        works, but has the nasty side effect of generating lots of intermediate
        events.
        """
##        dbg(suspend=1)  # turn off debugging around this function
##        dbg('MaskedComboBox::GetMark', indent=1)
        if self.__readonly:
##            dbg(indent=0)
            return 0, 0 # no selection possible for editing
##        sel_start, sel_to = wxComboBox.GetMark(self)        # what I'd *like* to have!
        sel_start = sel_to = self.GetInsertionPoint()
##        dbg("current sel_start:", sel_start)
        value = self.GetValue()
##        dbg('value: "%s"' % value)

        self._ignoreChange = True               # tell _OnTextChange() to ignore next event (if any)

        wx.ComboBox.Cut(self)
        newvalue = self.GetValue()
##        dbg("value after Cut operation:", newvalue)

        if newvalue != value:                   # something was selected; calculate extent
##            dbg("something selected")
            sel_to = sel_start + len(value) - len(newvalue)
            wx.ComboBox.SetValue(self, value)    # restore original value and selection (still ignoring change)
            wx.ComboBox.SetInsertionPoint(self, sel_start)
            wx.ComboBox.SetMark(self, sel_start, sel_to)

        self._ignoreChange = False              # tell _OnTextChange() to pay attn again

##        dbg('computed selection:', sel_start, sel_to, indent=0, suspend=0)
        return sel_start, sel_to


    def SetSelection(self, index):
        """
        Necessary for bookkeeping on choice selection, to keep current value
        current.
        """
##        dbg('MaskedComboBox::SetSelection(%d)' % index)
        if self._mask:
            self._prevValue = self._curValue
            self._curValue = self._choices[index]
            self._ctrl_constraints._autoCompleteIndex = index
        wx.ComboBox.SetSelection(self, index)


    def OnKeyDown(self, event):
        """
        This function is necessary because navigation and control key
        events do not seem to normally be seen by the wxComboBox's
        EVT_CHAR routine.  (Tabs don't seem to be visible no matter
        what... {:-( )
        """
        if event.GetKeyCode() in self._nav + self._control:
            self._OnChar(event)
            return
        else:
            event.Skip()    # let mixin default KeyDown behavior occur


    def OnSelectChoice(self, event):
        """
        This function appears to be necessary, because the processing done
        on the text of the control somehow interferes with the combobox's
        selection mechanism for the arrow keys.
        """
##        dbg('MaskedComboBox::OnSelectChoice', indent=1)

        if not self._mask:
            event.Skip()
            return

        value = self.GetValue().strip()

        if self._ctrl_constraints._compareNoCase:
            value = value.lower()

        if event.GetKeyCode() == wx.WXK_UP:
            direction = -1
        else:
            direction = 1
        match_index, partial_match = self._autoComplete(
                                                direction,
                                                self._ctrl_constraints._compareChoices,
                                                value,
                                                self._ctrl_constraints._compareNoCase,
                                                current_index = self._ctrl_constraints._autoCompleteIndex)
        if match_index is not None:
##            dbg('setting selection to', match_index)
            # issue appropriate event to outside:
            self._OnAutoSelect(self._ctrl_constraints, match_index=match_index)
            self._CheckValid()
            keep_processing = False
        else:
            pos = self._adjustPos(self._GetInsertionPoint(), event.GetKeyCode())
            field = self._FindField(pos)
            if self.IsEmpty() or not field._hasList:
##                dbg('selecting 1st value in list')
                self._OnAutoSelect(self._ctrl_constraints, match_index=0)
                self._CheckValid()
                keep_processing = False
            else:
                # attempt field-level auto-complete
##                dbg(indent=0)
                keep_processing = self._OnAutoCompleteField(event)
##        dbg('keep processing?', keep_processing, indent=0)
        return keep_processing


    def _OnAutoSelect(self, field, match_index):
        """
        Override mixin (empty) autocomplete handler, so that autocompletion causes
        combobox to update appropriately.
        """
##        dbg('MaskedComboBox::OnAutoSelect', field._index, indent=1)
##        field._autoCompleteIndex = match_index
        if field == self._ctrl_constraints:
            self.SetSelection(match_index)
##            dbg('issuing combo selection event')
            self.GetEventHandler().ProcessEvent(
                MaskedComboBoxSelectEvent( self.GetId(), match_index, self ) )
        self._CheckValid()
##        dbg('field._autoCompleteIndex:', match_index)
##        dbg('self.GetSelection():', self.GetSelection())
        end = self._goEnd(getPosOnly=True)
##        dbg('scheduling set of end position to:', end)
        # work around bug in wx 2.5
        wx.CallAfter(self.SetInsertionPoint, 0)
        wx.CallAfter(self.SetInsertionPoint, end)
##        dbg(indent=0)


    def _OnReturn(self, event):
        """
        For wxComboBox, it seems that if you hit return when the dropdown is
        dropped, the event that dismisses the dropdown will also blank the
        control, because of the implementation of wxComboBox.  So here,
        we look and if the selection is -1, and the value according to
        (the base control!) is a value in the list, then we schedule a
        programmatic wxComboBox.SetSelection() call to pick the appropriate
        item in the list. (and then do the usual OnReturn bit.)
        """
##        dbg('MaskedComboBox::OnReturn', indent=1)
##        dbg('current value: "%s"' % self.GetValue(), 'current index:', self.GetSelection())
        if self.GetSelection() == -1 and self.GetValue().lower().strip() in self._ctrl_constraints._compareChoices:
            wx.CallAfter(self.SetSelection, self._ctrl_constraints._autoCompleteIndex)

        event.m_keyCode = wx.WXK_TAB
        event.Skip()
##        dbg(indent=0)


class ComboBox( BaseMaskedComboBox, MaskedEditAccessorsMixin ):
    """
    This extra level of inheritance allows us to add the generic set of
    masked edit parameters only to this class while allowing other
    classes to derive from the "base" masked combobox control, and provide
    a smaller set of valid accessor functions.
    """
    pass


