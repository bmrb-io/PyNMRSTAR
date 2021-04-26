
Introduction to NMR-STAR
------------------------

To understand how the library works, you first need to understand the
NMR-STAR terminology and file format. If you are already familiar with
NMR-STAR, feel free to `jump ahead <#quick-start-to-pynmrstar>`__ to the
section on this library.

A NMR-STAR entry/file is composed of one or more saveframes
(conceptually you should think of a saveframe as loosely resembling
objects in an object-relational data model), each of which contain tags
and loops. There can only be one of each tag in a saveframe. If a tag
has multiple values, the only way to represent it is to place it inside
a loop. A loop is simply a set of tags with multiple values.

Therefore, hierarchically, you can picture a NMR-STAR file as a tree
where the entry is the trunk, the large branches are the saveframes, and
each saveframe may contain one or more loops - the branches.

Here is a very simple example of a NMR-STAR file:

::

    data_dates
        save_special_dates_saveframe_1
            _Special_Dates.Type     Holidays
            loop_
                _Events.Date
                _Events.Desciption
                12/31/2017 "New Year's Eve"
                01/01/2018 "New Year's Day"
            stop_
        save_

In the previous example, the entry name is ``dates`` because that is
what follows the ``data_`` tag. Next, there is one saveframe, with a
name of ``special_dates_saveframe_1`` and a tag prefix (which
corresponds to the saveframe category) of ``Special_Dates``. There is
one tag in the saveframe, with a tag name of ``Type`` and a value of
``Holidays``. There is also one loop of category ``events`` that has
information about two different events (though an unlimited number of
events could be present).

The first datum in each row corresponds to the first tag, ``Date``, and
the second corresponds to the second tag, ``Description``.

Values in NMR-STAR format need to be quoted if they contain a space,
tab, vertical tab, or newline in the value. This library takes care of
that for you, but it is worth knowing. That is why in the example the
dates are not quoted, but the event descriptions are.

Go on to the :doc:`quick-start`.