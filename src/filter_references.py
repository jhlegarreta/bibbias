# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
#
# Copyright The NiPreps Developers <nipreps@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# We support and encourage derived works from this project, please read
# about our expectations at
#
#     https://www.nipreps.org/community/licensing/
#

import argparse
import re
from pathlib import Path


def extract_citation_keys(latexstr: str) -> set:
    """Extract citation keys from LaTeX file string.

    Parameters
    ----------
    latexstr : :obj:`str`
        LaTeX file string.

    Returns
    -------
    :obj:`set`
        Citation keys.
    """

    pattern = r"\\(?:cite|citep|citet|citeauthor|citeyear)\s*\{([^}]+)\}"
    bib_id = re.findall(pattern, latexstr)

    # Split multiple citation keys in one command (e.g., \cite{key1,key2})
    return set([key.strip() for sublist in bib_id for key in sublist.split(",")])


def extract_bib_keys(bibstr: str) -> list:
    """Get the key for the given BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    :obj:`list`
        BibTeX keys.
    """

    pattern = r"@\w+\{([^,]+),"
    # pattern = r"@\w+\{(.*?),"

    return re.findall(pattern, bibstr)


def extract_bib_entries(bibstr: str) -> dict:
    """.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    entries : :obj:`dict`
        Citation keys and corresponding BibTeX entries.
    """

    # Match full entries using a greedy match with balanced braces
    entries = {}
    brace_level = 0
    entry = ""
    inside_entry = False

    for line in bibstr.splitlines():
        if line.strip().startswith("@"):
            inside_entry = True
            brace_level = 0
            entry = ""

        if inside_entry:
            entry += line + "\n"
            brace_level += line.count("{") - line.count("}")
            if brace_level <= 0:
                bib_id = extract_bib_keys(entry)[0]
                entries[bib_id] = entry
                inside_entry = False

    return entries


def filter_bibtex_references(bib_entries: dict, bib_id: set) -> dict:
    """Filter the BibTeX entries according to the given keys.

    Parameters
    ----------
    bib_entries : :obj:`dict`
        Citation keys and corresponding BibTeX entries.
    bib_id : :obj:`set`
        Citation keys.

    Returns
    -------
    filtered_bib_entries : :obj:`dict`
        Filtered BibTeX keys and corresponding entries.
    """

    return {key: value for key, value in bib_entries.items() if key in bib_id}



def save_bibtex(filtered_entries: list, output_file: Path) ->None:
    """Save BibTeX entries to file.

    Parameters
    ----------
    filtered_entries : :obj:`list`
        BibTeX entries.
    output_file : :obj:`Path`
        Output filename.
    """

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(filtered_entries))


def _parser():
    parser = argparse.ArgumentParser(
        description="Filter the BibTeX references not used in the author LaTeX file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("latex_file", type=Path, help="Input author LaTeX file")
    parser.add_argument("refs_bib_file", type=Path, help="Input references BibTeX file")
    parser.add_argument("output_bib_file", type=Path, help="Output references BibTeX file")

    return parser


def main(argv=None):

    pargs = _parser().parse_args(argv)

    latexstr = pargs.latex_file.read_text()
    bibstr = pargs.refs_bib_file.read_text()

    # Extract citation keys from LaTeX file
    used_cite_keys = extract_citation_keys(latexstr)

    print(f"Found {len(used_cite_keys)} citation keys in LaTeX file: {used_cite_keys}")

    # Extract citation keys from BibTeX file
    all_entries = extract_bib_entries(bibstr)

    print(f"Found {len(all_entries)} citation keys in BibTeX file: {list(all_entries.keys())}")

    # Discard references used in LaTeX file
    filtered_entries = filter_bibtex_references(all_entries, used_cite_keys)

    print(f"Found {len(filtered_entries)} citation keys used: {list(filtered_entries.keys())}")

    # Save used references to file
    save_bibtex(list(filtered_entries.values()), pargs.output_bib_file)

    print(f"Filtered BibTeX entries saved to {pargs.output_bib_file}")


if __name__ == "__main__":
    main()
