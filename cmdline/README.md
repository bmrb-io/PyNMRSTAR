# BMRB command line scripts

## About

These scripts are developed to ease certain common tasks performed against
NMR-STAR files. To run, they must be able to find a copy of `pynmrstar.py`
either in the same directory as them, or in the directory above them. Therefore
if you copy the script elsewhere make sure to copy `pynmrstar.py` as well.

Most of the tools' functions are clear from their names, but they are described
in detail here for reference. If you want to use the bmrb python library but
are intimidated looking at these scripts will provide you with an idea of how
to read data from NMR-STAR files using the library.

### pynmrstar.py

The python module itself has several command line flags that allow it to perform
useful functions on the command line. Those are:

#### Tag fetching

Run `pynmrstar.py --tag` and then a filename followed by a list of comma separated
tag names in order to extract the specified tags from the file and print
them in a tabular format.

For example:

```bash

./pynmrstar.py --tag bmr15000_3.str "_Citation_author.Given_name,_Citation_author.Family_name"
Gabriel Cornilescu
Erik    Hadley
Matthew Woll
John    Markley
Samuel  Gellman
Claudia Cornilescu
```

Note that when there are multiple values for a tag they are separated by newlines,
and when multiple tags are queried the individual tag results are separated by tabs.

**WARNING** - It is possible to query tags from different saveframes or loops with
this tool. That means that the tags will not always have the same number of results. To
properly machine parse the output you *must* look for one tab character `\t` as
the separator rather than a generic "space" regular expression like such `\s`. The
following example demonstrates the potential problem for improperly written code:

```bash

./pynmrstar.py --tag bmr15000_3.str "_Citation.Year,_Citation_author.Given_name,_Citation_author.Family_name"

2007    Gabriel Cornilescu
    Erik    Hadley
    Matthew Woll
    John    Markley
    Samuel  Gellman
    Claudia Cornilescu
```

You can see how one could mistakenly interpret "Erik" as a second result for
the `_Citation.Year` tag. Careful inspection of the tab characters show this isn't
the case. A warning will print to stdout if the tags you query have a mismatched
number of results, and you will never have to worry about this if you only query
one tag at a time.

Finally, and newlines in the value of tags will be replaced with `\n` escape
sequences, and any tabs will be replaced with the `\t` escape sequence.

An example of parsing the results using the `cut` tool to get just the last name
from the above query:

```bash

./pynmrstar.py --tag bmr15000_3.str "_Citation.Year,_Citation_author.Given_name,_Citation_author.Family_name" | cut -f3

Cornilescu
Hadley
Woll
Markley
Gellman
Cornilescu
```

#### Entry validation

To validate a NMR-STAR file against the NMR-STAR schema run:

```bash

./pynmrstar.py --validate bmr15000_3.str
No problems found during validation.
```

#### Entry comparison

To compare two NMR-STAR entries for equivalence (syntactically aware):

```bash

./pynmrstar.py --diff entry_1.str entry_2.str
Identical entries.
```

### Command line scripts

#### get_chemical_shifts_from_entry.py

Provide the filename of an NMR-STAR file as the first argument.

Prints a list of the chemical shifts from an entry in csv format as a result.

```bash
./get_chemical_shifts_from_entry.py bmr15000_3.str
_Atom_chem_shift.ID,_Atom_chem_shift.Assembly_atom_ID,_Atom_chem_shift.Entity_assembly_ID,_Atom_chem_shift.Entity_ID,_Atom_chem_shift.Comp_index_ID,_Atom_chem_shift.Seq_ID,_Atom_chem_shift.Comp_ID,_Atom_chem_shift.Atom_ID,_Atom_chem_shift.Atom_type,_Atom_chem_shift.Atom_isotope_number,_Atom_chem_shift.Val,_Atom_chem_shift.Val_err,_Atom_chem_shift.Assign_fig_of_merit,_Atom_chem_shift.Ambiguity_code,_Atom_chem_shift.Occupancy,_Atom_chem_shift.Resonance_ID,_Atom_chem_shift.Auth_entity_assembly_ID,_Atom_chem_shift.Auth_asym_ID,_Atom_chem_shift.Auth_seq_ID,_Atom_chem_shift.Auth_comp_ID,_Atom_chem_shift.Auth_atom_ID,_Atom_chem_shift.Details,_Atom_chem_shift.Entry_ID,_Atom_chem_shift.Assigned_chem_shift_list_ID
1,.,1,1,2,2,SER,H,H,1,9.3070,0.01,.,.,.,.,.,.,2,SER,H,.,15000,1
2,.,1,1,2,2,SER,HA,H,1,4.5970,0.01,.,.,.,.,.,.,2,SER,HA,.,15000,1
3,.,1,1,2,2,SER,HB2,H,1,4.3010,0.01,.,.,.,.,.,.,2,SER,HB2,.,15000,1
...
```

#### get_polymer_sequence.py

Provide the filename of an NMR-STAR file as the first argument.

Prints the polymer sequence(s) from the file, newline separated if multiple
entities are present.

```bash

./get_polymer_sequence.py bmr15000_3.str
LSDEDFRAVXGMTRSAFANLPLWRQQNLRRERGLF
```

#### list_saveframes_in_entry.py

Provide the filename of an NMR-STAR file as the first argument.

Prints a list of the saveframes in the entry in `saveframe_name: saveframe_category`
format.

```bash

./list_saveframes_in_entry.py bmr15000_3.str
entry_information: entry_information
citation_1: citations
assembly: assembly
F5-Phe-cVHP: entity
natural_source: natural_source
experimental_source: experimental_source
chem_comp_PHF: chem_comp
unlabeled_sample: sample
selectively_labeled_sample: sample
sample_conditions: sample_conditions
NMRPipe: software
PIPP: software
SPARKY: software
CYANA: software
X-PLOR_NIH: software
spectrometer_1: NMR_spectrometer
spectrometer_2: NMR_spectrometer
spectrometer_3: NMR_spectrometer
spectrometer_4: NMR_spectrometer
spectrometer_5: NMR_spectrometer
spectrometer_6: NMR_spectrometer
NMR_spectrometer_list: NMR_spectrometer_list
experiment_list: experiment_list
chemical_shift_reference_1: chem_shift_reference
assigned_chem_shift_list_1: assigned_chemical_shifts

```

#### list_tags_in_entry.py

Provide the filename of an NMR-STAR file as the first argument.

Prints a list of all of the saveframes, loop, and tags that exist in a given
NMR-STAR file.

```bash

./list_tags_in_entry.py bmr15000_3.str
Entry 15000
  Saveframe entry_information:entry_information
    _Entry.Sf_category
    _Entry.Sf_framecode
    _Entry.ID
    _Entry.Title
    _Entry.Type
    _Entry.Version_type
    _Entry.Submission_date
    _Entry.Accession_date
    _Entry.Last_release_date
    _Entry.Original_release_date
    _Entry.Origination
    _Entry.NMR_STAR_version
    _Entry.Original_NMR_STAR_version
    _Entry.Experimental_method
    _Entry.Experimental_method_subtype
    _Entry.Details
    _Entry.BMRB_internal_directory_name
    Loop _Entry_author
      _Entry_author.Ordinal
      _Entry_author.Given_name
      _Entry_author.Family_name
      _Entry_author.First_initial
      _Entry_author.Middle_initials
      _Entry_author.Family_title
      _Entry_author.Entry_ID
...

```

#### print_tags_in_saveframe.py

Provide the filename of an NMR-STAR saveframe file as the first argument.

Prints all of the tags and their values from a NMR-STAR saveframe file in the format:
`tag_name: tag_value`

```bash

./print_tags_in_saveframe.py bmr15000_3_Entry_saveframe.str
_Entry.Sf_category: entry_information
_Entry.Sf_framecode: entry_information
_Entry.ID: 15000
_Entry.Title: Solution structure of chicken villin headpiece subdomain containing a fluorinated side chain in the core\n
_Entry.Type: macromolecule
_Entry.Version_type: original
_Entry.Submission_date: 2006-09-07
_Entry.Accession_date: 2006-09-07
_Entry.Last_release_date: .
_Entry.Original_release_date: .
_Entry.Origination: author
_Entry.NMR_STAR_version: 3.1.1.61
_Entry.Original_NMR_STAR_version: .
_Entry.Experimental_method: NMR
_Entry.Experimental_method_subtype: solution
_Entry.Details: .
_Entry.BMRB_internal_directory_name: .

```
