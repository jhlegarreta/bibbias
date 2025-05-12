#!/usr/bin/env python
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
#
# Copyright 2022 Oscar Esteban <code@oscaresteban.es>
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

import os
import json
import argparse
import requests
import re
from collections import Counter
from itertools import chain, product
from pathlib import Path

import pandas as pd


BIBBIAS_CACHE_PATH = Path(
    os.getenv("BIBBIAS_CACHE_PATH", str(Path.home() / ".cache" / "bibbias"))
)
BIBBIAS_CACHE_PATH.mkdir(exist_ok=True, parents=True)

MALE = "M"
FEMALE = "F"
UNKNOWN = "None"

BIB_KEY = "bib_key"
FA_NAME = "fa_name"
FA_GENDER = "fa_gender"
LA_NAME = "la_name"
LA_GENDER = "la_gender"
NAME = "name"

FF = "FF"
FM = "FM"
MM = "MM"
MF = "MF"
RATIO = "ratio"

SUM = "sum"
MEDIAN = "median"
NONZERO = "nonzero"

MISSED = "missed"
RESOLVED = "resolved"
REFERENCES = "references"
STATS = "stats"

AUTHORS = "authors"
COUNT = "count"
GENDER = "gender"
FIRST_LAST = "first_last"
FIRST_AUTHOR = "first_author"
LAST_AUTHOR = "last_author"
RELEVANT_AUTHOR = "relevant_author"
REFS_REPEATS = "refs_repeats"

TSV = "tsv"
FNAME_SEP = "."
LABEL_SEP = "_"


def compose_filename(dirname, labels, extension):

    file_rootname = "".join([label + LABEL_SEP for label in labels])[:-1]
    file_basename = file_rootname + FNAME_SEP + extension
    return dirname / file_basename


def get_cached_gender_mapping() -> dict:
    """Get cached (first) name to gender mapping.

    Returns
    -------
    cached : :obj:`dict`
        Cached (first) name to gender mapping.
    """

    cached = {}
    if (BIBBIAS_CACHE_PATH / "names.cache").exists():
        cached = json.loads((BIBBIAS_CACHE_PATH / "names.cache").read_text())

    return cached


def split_authors(authors: str) -> list:
    """Split a string of authors into the individual authors.

    Assumes individual authors are joined with ``and``.

    Parameters
    ----------
    authors : :obj:`str`
        Author list string.

    Returns
    -------
    :obj:`list`
        Author list.
    """

    return authors.split(" and")


def get_authors(authors: str) -> list:
    """Get authors from a string.

    Parameters
    ----------
    authors : :obj:`str`
        Author list string.

    Returns
    -------
    :obj:`list`
        Author list.
    """

    return list(map(lambda x: x.strip(), split_authors(authors)))


def get_bib_authors(bibstr: str) -> dict:
    """Get the author list for the given BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    :obj:`dict`
        Author list for each BibTeX key.
    """

    matches = re.findall(r"author\s=\s+\{(.*?)\}", bibstr, re.DOTALL)
    author_lists = [m.replace("\n", " ") for m in matches]
    bib_id = re.findall(r"@\w+\{(.*?),", bibstr)

    return dict(sorted(zip(bib_id, author_lists)))


def count_position_instances(authors: list, pos: tuple = (0, -1)) -> tuple[Counter, Counter]:
    """Count the number of instances an author is at a given position.

    Parameters
    ----------
    authors : :obj:`list`
        Author list.
    pos : :obj:`tuple`, optional
        Positions where the instances are to be counted.

    Returns
    -------
    :obj:`tuple`
        Name to number of instance mapping.
    """

    return tuple(Counter(name[i] for name in authors) for i in pos)


def extract_first_last_authors(bibstr: str) -> list:
    """Extract first and last author names from a BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    first_last : :obj:`list`
        First and last author name tuples.
    """

    authors = get_bib_authors(bibstr)

    first_last = []
    for _authors in authors.values():
        _auth = get_authors(_authors)
        first_last.append((_auth[0], _auth[-1]))

    return first_last


def get_first_name(authors: str) -> list:
    """Get first names from the given author list.

    Initials are removed from the author name.

    Parameters
    ----------
    authors : :obj:`str`
        Author list.

    Returns
    -------
    :obj:`list`
        Author first names.
    """

    strip_initial = re.compile(r"\s*\w\.\s*")

    _authors = split_authors(authors)
    return [strip_initial.sub("", auth.strip().split(",")[-1].strip().lower()) for auth in _authors]


def query_names(nameset: set) -> dict:
    """Lookup names in local cache, if not found hit Gender API.

    Parameters
    ----------
    nameset : :obj:`set`
        (First) Names.

    Returns
    -------
    cached : :obj:`dict`
        (First) Name to gender mapping.
    """

    cached = get_cached_gender_mapping()

    misses = sorted(set(nameset) - set(cached.keys()))

    if not misses:
        return cached

    # gender-api key
    api_key = os.getenv("GENDER_API_KEY", None)
    if api_key is None:
        print(f"No Gender API key - {len(misses)} names could not be mapped.")
        return cached

    gender_api_query = f"https://gender-api.com/get?name={{name}}&key={api_key}".format

    responses = {}
    for n in misses:
        print(f"Querying for {n}")
        q = requests.get(gender_api_query(name=n))
        if q.ok:
            responses[n] = q.json()
            if int(responses[n]["accuracy"]) >= 60:
                cached[n] = FEMALE if responses[n]["gender"] == "female" else MALE

    # Store cache
    (BIBBIAS_CACHE_PATH / "names.cache").write_text(json.dumps(cached, indent=2))

    # Store responses?
    return cached


def find_author_gender(bibstr: str, cached: dict | None = None) -> tuple[dict, dict]:
    """Find the gender for the authors in the given BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.
    cached : :obj:`dict`, optional
        (First) Name to gender mapping.

    Returns
    -------
    data : :obj:`dict`
        Dictionary of ((first) name, gender) tuples for the authors for each
        citation key.
    missed : :obj:`dict`
        Mapping of (first) names whose gender could not be determined to their
        number of instances.
    """

    authors = get_bib_authors(bibstr)

    cached = cached or get_cached_gender_mapping()

    data = {}
    missed = {}
    for bib_id, _authors in authors.items():
        first_names = get_first_name(_authors)
        data[bib_id] = tuple((name, cached.get(name, None)) for name in first_names)

        missed[bib_id] = {}
        for f, n in data[bib_id]:
            if n is None:
                missed[bib_id][f] = missed.get(f, 0) + 1

    return data, missed


def compute_gender_totals(data: dict) -> dict:
    """Compute the gender totals in the data.

    Parameters
    ----------
    data : :obj:`dict`
        Dictionary of ((first) name, gender) tuples for the authors for each
        citation key.

    Returns
    -------
    gender_distr : :obj:`dict`
        Gender totals for each citation key.
    """

    gender_distr = {bib_id: {"".join(c): 0 for c in (MALE, FEMALE, UNKNOWN)} for bib_id in data}
    for bib_id, author_gender in data.items():
        list(map(lambda auth: gender_distr[bib_id].__setitem__(f"{auth[1]}", gender_distr[bib_id][f"{auth[1]}"] + 1),  author_gender))

    return gender_distr


def find_first_last_gender(bibstr: str, cached: dict | None = None) -> tuple[dict, dict]:
    """Find the gender for the first and last authors in the given BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.
    cached : :obj:`dict`, optional
        (First) Name to gender mapping.

    Returns
    -------
    data : :obj:`dict`
        Dictionary of ((first) name, gender) tuple pairs for the first and last
        author for each citation key.
    missed : :obj:`dict`
        Mapping of (first) names whose gender could not be determined to their
        number of instances.
    """

    authors = get_bib_authors(bibstr)

    cached = cached or get_cached_gender_mapping()

    data = {}
    missed = {}
    for bib_id, _authors in authors.items():
        first_auth_name, last_auth_name = (first_names := get_first_name(_authors))[0], first_names[-1]
        data[bib_id] = (
            (first_auth_name, cached.get(first_auth_name, None)),
            (last_auth_name, cached.get(last_auth_name, None)),
        )

        for f, n in data[bib_id]:
            if n is None:
                missed[f] = missed.get(f, 0) + 1

    return data, missed


def get_author_gender_distribution(bibstr: str) -> tuple[dict, dict]:
    """Get the author gender distribution from a BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    resolved : :obj:`dict`
        Dictionary of ((first) name, gender) tuples for the authors for each
        citation key.
    missed : :obj:`dict`
        Mapping of (first) names whose gender could not be determined to their
        number of instances.
    """

    # first pass
    resolved, missed = find_author_gender(bibstr)

    if missed:
        resolved, missed = find_author_gender(bibstr, query_names(missed))

    return resolved, missed


def get_first_last_gender_distribution(bibstr: str) -> tuple[dict, dict]:
    """Get the first and last author gender distribution from a BibTeX file string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    resolved : :obj:`dict`
        Dictionary of ((first) name, gender) tuple pairs for the first and last
        author for each citation key.
    missed : :obj:`dict`
        Mapping of (first) names whose gender could not be determined to their
        number of instances.
    """

    # first pass
    resolved, missed = find_first_last_gender(bibstr)

    if missed:
        resolved, missed = find_first_last_gender(bibstr, query_names(missed))

    return resolved, missed


def compute_first_last_gender_totals(data: dict) -> dict:
    """Compute the (first, last) author gender pair totals in the data.

    Parameters
    ----------
    data : :obj:`dict`
        Dictionary of ((first) name, gender) tuple pairs for the first and last
        author for each citation key.

    Returns
    -------
    gender_distr : :obj:`dict`
        Dictionary of {gender: count} items where the gender contains the
        products for the ("M", "F", "None") strings (the first element denoting
        the gender of the first author, the second denoting the gender for the
        last), and the count contains the number of times of the event.
    """

    gender_distr = {"".join(c): 0 for c in product((MALE, FEMALE, UNKNOWN), repeat=2)}
    for first, last in data.values():
        gender_distr[f"{first[1]}{last[1]}"] += 1

    return gender_distr


def count_author_reference_instances(author_bibstr: str, refs_bibstr: str) -> dict:
    """Count the number of instances an author is referenced.

    Counts the number of instances an author from the ``author_bibstr`` BibTeX
    string appears as an author in the ``refs_bibstr`` BibTeX string.

    Parameters
    ----------
    author_bibstr : :obj:`str`
        Autor BibTeX file string.
    refs_bibstr : :obj:`str`
        References BibTeX file string.

    Returns
    -------
    common_auth_count : :obj:`dict`
        Number of instances an author is referenced.
    """

    authors = get_bib_authors(author_bibstr)
    ref_authors = get_bib_authors(refs_bibstr)

    # Flatten the values in references and count occurrences of each author
    _ref_authors = sorted(chain.from_iterable([split_authors(names) for names in ref_authors.values()]))
    # Remove leading and trailing whitespaces
    _ref_authors = sorted([item.strip() for item in _ref_authors])

    common_auth = {}
    common_auth_count = {}
    for bib_id, _authors in authors.items():
        _auth = get_authors(_authors)
        # Find common authors
        common_auth[bib_id] = sorted(set(_auth) & set(_ref_authors))
        # Number of times each author appears
        ref_counts = Counter(name for name in _ref_authors)
        common_auth_count[bib_id] = {author: ref_counts[author] for author in common_auth[bib_id]}

    return common_auth_count


def count_first_last_instances(bibstr: str) -> tuple[dict, dict, list]:
    """Count the number of instances an author is first or last in a BibTeX file
    string.

    Parameters
    ----------
    bibstr : :obj:`str`
        BibTeX file string.

    Returns
    -------
    first_auth_count : :obj:`dict`
        Name to first author instance count mapping.
    self_last_author_counts : :obj:`dict`
        Name to last author instance count mapping.
    first_last_auth : :obj:`list`
        First and last author name tuples.
    """

    first_last = extract_first_last_authors(bibstr)

    _first_auth_count, _last_auth_count = count_position_instances(first_last, pos=(0, -1))

    first_auth_count = dict(sorted(_first_auth_count.items()))
    last_auth_count = dict(sorted(_last_auth_count.items()))

    return first_auth_count, last_auth_count, first_last


def count_self_first_last_instances(author_bibstr: str, refs_bibstr: str) -> tuple[dict, dict]:
    """Count the number of instances an author is first or last author.

    Counts the number of instances an author from the ``author_bibstr`` BibTeX
    string appears as a first or last author in the ``refs_bibstr`` BibTeX
    string.

    Parameters
    ----------
    author_bibstr : :obj:`str`
        Autor BibTeX file string.
    refs_bibstr : :obj:`str`
        References BibTeX file string.

    Returns
    -------
    self_first_auth_count : :obj:`dict`
        Name to first author instance count mapping for each BibTeX key.
    self_last_auth_count : :obj:`dict`
        Name to last author instance count mapping for each BibTeX key.
    """

    authors = get_bib_authors(author_bibstr)
    ref_first_last_authors = extract_first_last_authors(refs_bibstr)

    _ref_first_auth_count, _ref_last_auth_count = count_position_instances(ref_first_last_authors, pos=(0, -1))

    self_first_auth_count = {}
    self_last_auth_count = {}
    for bib_id, _authors in authors.items():
        _auth = get_authors(_authors)
        self_first_auth_count[bib_id] = {author: _ref_first_auth_count[author] for author in _auth}
        self_last_auth_count[bib_id] = {author: _ref_last_auth_count[author] for author in _auth}

    return self_first_auth_count, self_last_auth_count


def create_first_last_author_gender_df(author_gender_data: dict) -> pd.DataFrame:
    """Create a fist/last author gender dataframe.

    Parameters
    ----------
    author_gender_data : :obj:`dict`
        Dictionary of ((first) name, gender) tuple pairs for the first and last
        author for each citation key.

    Returns
    -------
    :obj:`pd.DataFrame`
        First/last author gender.
    """

    # Prepare lists to hold the data for the DataFrame
    keys = []
    fa_names = []
    fa_gender = []
    la_names = []
    la_gender = []

    # Process each key and tuple
    for key, value in author_gender_data.items():
        keys.append(key)

        # Unpack the tuples (ensure handling of cases with one tuple only)
        _fa_name, _fa_gender = value[0]
        _la_name, _la_gender = value[1]

        fa_names.append(_fa_name)
        fa_gender.append(_fa_gender)
        la_names.append(_la_name)
        la_gender.append(_la_gender)

    # Create a DataFrame
    return pd.DataFrame({
        BIB_KEY: keys,
        FA_NAME: fa_names,
        FA_GENDER: fa_gender,
        LA_NAME: la_names,
        LA_GENDER: la_gender,
    })


def compute_first_last_gender(df: pd.DataFrame) -> pd.DataFrame:
    """Compute counts on first/last author gender.

    Parameters
    ----------
    df : :obj:`pd.DataFrame`
        Gender data.

    Returns
    -------
    df_fa_la_gender_count : :obj:`pd.DataFrame`
        First/last author gender counts.
    """

    # Define possible categories
    categories = [MALE, FEMALE, UNKNOWN]

    # Parse first and second by checking against known categories
    def _parse_pair(pair):
        for cat in categories:
            if pair.startswith(cat):
                first = cat
                second = pair[len(cat):]
                return first, second
        return None, None  # fallback, shouldn't happen

    _df = df.copy()
    _df[[FIRST_AUTHOR, LAST_AUTHOR]] = _df[GENDER].apply(
        lambda x: pd.Series(_parse_pair(x)))

    # Group and sum
    fa_gender_count = _df.groupby(FIRST_AUTHOR)[COUNT].sum()
    la_gender_count = _df.groupby(LAST_AUTHOR)[COUNT].sum()

    df_fa_la_gender_count = pd.DataFrame({
        GENDER: fa_gender_count.keys(),
        FIRST_AUTHOR: fa_gender_count,
        LAST_AUTHOR: la_gender_count
    }).reset_index(drop=True)

    return df_fa_la_gender_count


def compute_gender_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """Compute gender ratio.

    Parameters
    ----------
    df : :obj:`pd.DataFrame`
        Gender data.

    Returns
    -------
    :obj:`pd.DataFrame`
        Gender ratio.
    """

    total = df[COUNT].sum()
    ratios = df[COUNT] / total

    ratios_df = pd.DataFrame([df[GENDER], ratios]).T
    ratios_df.columns = [GENDER, RATIO]

    return ratios_df


def compute_count_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute count statistics.

    Parameters
    ----------
    df : :obj:`pd.DataFrame`
        Count data.

    Returns
    -------
    :obj:`pd.DataFrame`
        Count statistics.
    """

    desc = df.describe()
    desc.loc[SUM] = df.sum(numeric_only=True)
    desc.loc[MEDIAN] = df.median(numeric_only=True)
    desc.loc[NONZERO] = df.astype(bool).sum(axis=0)

    return desc


def _parser():
    parser = argparse.ArgumentParser(
        description="Run author and citation diversity, equity and inclusiveness analytics on BibTeX files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("author_bib_file", type=Path, help="Input author BibTeX file")
    parser.add_argument("refs_bib_file", type=Path, help="Input references BibTeX file")
    parser.add_argument("output_folder", type=Path, help="Output folder")

    return parser


def main(argv=None):
    """Execute querying."""

    pargs = _parser().parse_args(argv)
    # Read bib files
    # to minimize bibtex -o minimized.bib texfile.aux
    author_bibstr = pargs.author_bib_file.read_text()
    refs_bibstr = pargs.refs_bib_file.read_text()

    resolved, missed = get_first_last_gender_distribution(refs_bibstr)
    ref_gender_report = compute_first_last_gender_totals(resolved)

    print("Gender diversity bias in references")
    print(f"Number of references: {len(resolved.keys())}")
    print("Resolved")
    print(resolved)
    print("Missed")
    print(missed)
    print(ref_gender_report)

    first_auth_count, last_auth_count, first_last = count_first_last_instances(refs_bibstr)

    print("\nFirst/last diversity bias in references")
    print(f"First author repeats across refs: {first_auth_count}")
    print(f"Last author repeats across refs: {last_auth_count}")
    print(f"Number of different firsts: {len(first_auth_count)/len(first_last)} ({len(first_auth_count)}/{len(first_last)})")
    print(f"Number of different lasts: {len(last_auth_count)/len(first_last)} ({len(last_auth_count)}/{len(first_last)})")

    _resolved, _missed = get_author_gender_distribution(author_bibstr)
    auth_gender_report = compute_gender_totals(_resolved)

    print("\nAuthor gender bias")
    print(f"Number of authors: {len(list(_resolved.values())[0])}")
    print("Resolved")
    print(_resolved)
    print("Missed")
    print(_missed)
    print(auth_gender_report)

    print("\nAuthor reference bias")

    common_auth_count = count_author_reference_instances(author_bibstr, refs_bibstr)
    self_first_auth_count, self_last_auth_count = count_self_first_last_instances(author_bibstr, refs_bibstr)

    print("Authors that also appear in references")
    print(common_auth_count)

    print("Self first/last instances")
    print("Self authors as first authors in refs")
    print(self_first_auth_count)
    print("Self authors as last authors in refs")
    print(self_last_auth_count)

    # Save data
    sep = "\t"
    report_index = False
    stats_index = True
    ratio_index = False
    na_rep = "NA"

    # Refs gender diversity bias
    labels = [REFERENCES, GENDER, MISSED]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_missed = pd.DataFrame(list(missed.items()), columns=[NAME, COUNT])
    df_missed.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    labels = [REFERENCES, GENDER, RESOLVED]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_resolved = create_first_last_author_gender_df(resolved)
    df_resolved.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    labels = [REFERENCES, FIRST_LAST, GENDER, COUNT]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_gender = pd.DataFrame(list(ref_gender_report.items()), columns=[GENDER, COUNT])
    df_gender.to_csv(fname, sep=sep, index=report_index)

    df_ratio = compute_gender_ratio(df_gender)

    labels = [REFERENCES, FIRST_LAST, GENDER, RATIO]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_ratio.to_csv(fname, sep=sep, index=ratio_index, na_rep=na_rep)

    df_fa_la_gender_count = compute_first_last_gender(df_gender)

    labels = [REFERENCES, GENDER, FIRST_AUTHOR, LAST_AUTHOR, COUNT]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_fa_la_gender_count.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    df_fa_gender_count = df_fa_la_gender_count[[GENDER, FIRST_AUTHOR]].rename(columns={FIRST_AUTHOR: COUNT})

    df_fa_gender_ratio = compute_gender_ratio(df_fa_gender_count)

    labels = [REFERENCES, GENDER, FIRST_AUTHOR, RATIO]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_fa_gender_ratio.to_csv(fname, sep=sep, index=ratio_index, na_rep=na_rep)

    df_la_gender_count = df_fa_la_gender_count[[GENDER, LAST_AUTHOR]].rename(columns={LAST_AUTHOR: COUNT})

    df_la_gender_ratio= compute_gender_ratio(df_la_gender_count)

    labels = [REFERENCES, GENDER, LAST_AUTHOR, RATIO]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_la_gender_ratio.to_csv(fname, sep=sep, index=ratio_index, na_rep=na_rep)

    df_relevant_gender_count = pd.DataFrame({
        GENDER: df_fa_la_gender_count[GENDER],
        COUNT: df_fa_la_gender_count[FIRST_AUTHOR] + df_fa_la_gender_count[LAST_AUTHOR]
    })
    labels = [REFERENCES, GENDER, RELEVANT_AUTHOR, COUNT]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_relevant_gender_count.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    df_relevant_gender_ratio = compute_gender_ratio(df_relevant_gender_count)

    labels = [REFERENCES, GENDER, RELEVANT_AUTHOR, RATIO]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_relevant_gender_ratio.to_csv(fname, sep=sep, index=ratio_index, na_rep=na_rep)

    # Refs first/last count diversity bias
    labels = [REFERENCES, FIRST_AUTHOR, COUNT]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_fa_count = pd.DataFrame(list(first_auth_count.items()), columns=[NAME, COUNT])
    df_fa_count.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    df_fa_stats = compute_count_stats(df_fa_count)

    labels = [REFERENCES, FIRST_AUTHOR, STATS]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_fa_stats.to_csv(fname, sep=sep, index=stats_index)

    labels = [REFERENCES, LAST_AUTHOR, COUNT]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_la_count = pd.DataFrame(list(last_auth_count.items()), columns=[NAME, COUNT])
    df_la_count.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    df_la_stats = compute_count_stats(df_la_count)

    labels = [REFERENCES, LAST_AUTHOR, STATS]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_la_stats.to_csv(fname, sep=sep, index=stats_index)

    labels = [REFERENCES, FIRST_LAST]
    fname = compose_filename(pargs.output_folder, labels, TSV)
    df_fl = pd.DataFrame(first_last, columns=[FIRST_AUTHOR, LAST_AUTHOR])
    df_fl.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

    # Authors gender diversity bias
    bib_id = list(auth_gender_report.keys())
    for _id in bib_id:
        labels = [AUTHORS, GENDER, MISSED, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_missed = pd.DataFrame(list(_missed[_id].items()), columns=[NAME, COUNT])
        df_missed.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

        labels = [AUTHORS, GENDER, RESOLVED, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_resolved = pd.DataFrame(_resolved[_id], columns=[NAME, COUNT])
        df_resolved.to_csv(fname, sep=sep, index=report_index, na_rep=na_rep)

        labels = [AUTHORS, GENDER, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_gender = pd.DataFrame(list(auth_gender_report[_id].items()), columns=[GENDER, COUNT])
        df_gender.to_csv(fname, sep=sep, index=report_index)

        # Compute ratio
        df_ratio = compute_gender_ratio(df_gender)

        labels = [AUTHORS, GENDER, RATIO, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ratio.to_csv(fname, sep=sep, index=ratio_index)

    # Authors ref count diversity bias
    for _id in bib_id:
        labels = [AUTHORS, REFERENCES, COUNT, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_count = pd.DataFrame(common_auth_count[_id].items(), columns=[NAME, COUNT])
        df_ref_count.to_csv(fname, sep=sep, index=report_index)

        df_ref_stats = compute_count_stats(df_ref_count)
        labels = [AUTHORS, REFERENCES, STATS, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_stats.to_csv(fname, sep=sep, index=stats_index)

        labels = [AUTHORS, REFERENCES, FIRST_AUTHOR, COUNT, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_fa_count = pd.DataFrame(self_first_auth_count[_id].items(), columns=[NAME, COUNT])
        df_ref_fa_count.to_csv(fname, sep=sep, index=report_index)

        df_ref_fa_stats = compute_count_stats(df_ref_fa_count)
        labels = [AUTHORS, REFERENCES, FIRST_AUTHOR, STATS, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_fa_stats.to_csv(fname, sep=sep, index=stats_index)

        labels = [AUTHORS, REFERENCES, LAST_AUTHOR, COUNT, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_la_count = pd.DataFrame(self_last_auth_count[_id].items(), columns=[NAME, COUNT])
        df_ref_la_count.to_csv(fname, sep=sep, index=report_index)

        df_ref_la_stats = compute_count_stats(df_ref_la_count)
        labels = [AUTHORS, REFERENCES, LAST_AUTHOR, STATS, _id]
        fname = compose_filename(pargs.output_folder, labels, TSV)
        df_ref_la_stats.to_csv(fname, sep=sep, index=stats_index)


if __name__ == "__main__":
    main()
