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
import argparse
import os
import json
import re
from pathlib import Path
from itertools import product

import requests


import pandas as pd


BIBBIAS_CACHE_PATH = Path(
    os.getenv("BIBBIAS_CACHE_PATH", str(Path.home() / ".cache" / "bibbias"))
)
BIBBIAS_CACHE_PATH.mkdir(exist_ok=True, parents=True)

BIB_KEY = "bib_key"
FA_NAME = "fa_name"
FA_SEX = "fa_sex"
LA_NAME = "la_name"
LA_SEX = "la_sex"
NAME = "name"

FF = "FF"
FM = "FM"
MM = "MM"
MF = "MF"
CATEGORY = "Category"
RATIO = "Ratio"


def _parser():
    parser = argparse.ArgumentParser(
        description="Run gender analytics on an existing BibTeX file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("bib_file", type=Path, help="The input bibtex file")
    parser.add_argument("missed_query_file", type=Path, help="The missed query data file")
    parser.add_argument("resolved_query_file", type=Path, help="The resolved query data file")
    parser.add_argument("gender_report_file", type=Path, help="The gender report data file")
    parser.add_argument("stats_report_file", type=Path, help="The stats report data file")
    return parser


def main(argv=None):
    """Execute querying."""

    pargs = _parser().parse_args(argv)
    # Read bib file
    # to minimize bibtex -o minimized.bib texfile.aux
    bibstr = pargs.bib_file.read_text()

    # first pass
    resolved, missed = find_gender(bibstr)

    if missed:
        resolved, missed = find_gender(bibstr, query_names(missed))

    gender_report = report_gender(resolved)
    print(gender_report)

    # Save data
    sep = "\t"
    index = False
    na_rep = "NA"

    # Missed and resolved query data
    df_missed = pd.DataFrame(list(missed), columns=[NAME])
    df_missed.to_csv(pargs.missed_query_file, sep=sep, index=index, na_rep=na_rep)

    df_resolved = create_author_gender_df(resolved)
    df_resolved.to_csv(pargs.resolved_query_file, sep=sep, index=index, na_rep=na_rep)

    # Gender report
    df_gender = pd.DataFrame([gender_report])
    df_gender.to_csv(pargs.gender_report_file, sep=sep, index=index)

    # Compute stats
    df = compute_gender_stats(df_gender)
    df.to_csv(pargs.stats_report_file, sep=sep, index=index, na_rep=na_rep)


def find_gender(bibstr, cached=None):
    """Find the gender for a given bib file."""

    matches = re.findall(r"author\s=\s+\{(.*?)\}", bibstr, re.DOTALL)
    author_lists = [m.replace("\n", " ") for m in matches]
    bib_id = re.findall(r"@\w+\{(.*?),", bibstr)
    strip_initial = re.compile(r"\s*\w\.\s*")

    if cached is None and (BIBBIAS_CACHE_PATH / "names.cache").exists():
        cached = json.loads((BIBBIAS_CACHE_PATH / "names.cache").read_text())

    cached = cached or {}

    data = {}
    missed = set()
    for bid, authors in zip(bib_id, author_lists):
        authlst = authors.split(" and")
        first = strip_initial.sub("", authlst[0].strip().split(",")[-1].strip().lower())
        last = strip_initial.sub("", authlst[-1].strip().split(",")[-1].strip().lower())
        data[bid] = (
            (first, cached.get(first, None)),
            (last, cached.get(last, None)),
        )

        for f, n in data[bid]:
            if n is None:
                missed.add(f)

    return data, missed


def query_names(nameset):
    """Lookup names in local cache, if not found hit Gender API."""

    cached = (
        json.loads((BIBBIAS_CACHE_PATH / "names.cache").read_text())
        if (BIBBIAS_CACHE_PATH / "names.cache").exists()
        else {}
    )
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
                cached[n] = "F" if responses[n]["gender"] == "female" else "M"

    # Store cache
    (BIBBIAS_CACHE_PATH / "names.cache").write_text(json.dumps(cached, indent=2))

    # Store responses?
    return cached


def report_gender(data):
    """Generate a dictionary reporting gender of first and last authors."""

    retval = {"".join(c): 0 for c in product(("M", "F", "None"), repeat=2)}
    for first, last in data.values():
        retval[f"{first[1]}{last[1]}"] += 1

    return retval


def create_author_gender_df(author_gender_data):

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
        "BIB_KEY": keys,
        "FA_NAME": fa_names,
        "FA_GENDER": fa_gender,
        "LA_NAME": la_names,
        "LA_GENDER": la_gender,
    })


def compute_gender_stats(df):
    total = df.sum(axis=1).iloc[0]
    ratios = df.iloc[0] / total

    ratios_df = pd.DataFrame(ratios).reset_index()
    ratios_df.columns = [CATEGORY, RATIO]

    return ratios_df


if __name__ == "__main__":
    main()
