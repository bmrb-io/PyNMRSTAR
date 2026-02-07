# BMRB command line scripts

## About

These scripts are developed to ease certain common tasks performed against
NMR-STAR files. To run them, the `pynmrstar` package must be installed
(e.g. `pip install pynmrstar`).

Most of the tools' functions are clear from their names, but they are described
in detail here for reference. If you want to use the pynmrstar library but
are intimidated, looking at these scripts will provide you with an idea of how
to read data from NMR-STAR files using the library.

### Library equivalents

In addition to the scripts below, equivalent functionality for tag fetching,
validation, and entry comparison is available directly through the library:

```python
import pynmrstar

# Tag fetching
entry = pynmrstar.Entry.from_file("bmr15000_3.str")
entry.get_tag("_Citation_author.Given_name")

# Validation
pynmrstar.utils.validate(entry)

# Entry comparison
entry2 = pynmrstar.Entry.from_file("other_entry.str")
pynmrstar.utils.diff(entry, entry2)
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

Prints a list of all the saveframes, loops, and tags that exist in a given
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

Prints all the tags, and their values from a NMR-STAR saveframe file in the format:
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
