# bibbias
Analyze a bib file for biases.

This tool allows to compute:
- The gender diversity in first/last authors on a given BibTeX file.
- The number of distinct first/last authors on a given BibTeX file.
- The number of authors on a given BibTeX file.
- The gender diversity of the authors on a given BibTeX file.
- The number of instances the authors on a given BibTeX file are cited on another (e.g.
  references) BibTeX file.

The script can be called as:
```
bias.py \
  manuscript_references.bib \
  manuscript_bibfile.bib \
  output_dirname/
```
