# Kindling

**Open-source healthcare interoperability and analytics tools, set up to work together.**

There's no shortage of good open-source healthcare software: Synthea generates realistic
synthetic patients, HAPI FHIR and Blaze are solid FHIR servers, Medplum and OpenEMR are
working EHRs, the Tuva Project turns raw claims and clinical data into analytics-ready
marts with dbt, and cqframework provides a reference Clinical Quality Language (CQL)
engine for running eCQMs and clinical decision support.

Each project documents itself well. What's missing is **the whole story**: how these
pieces fit together, which versions work with which, what glue code is needed between
them, and a running system where you can see all of them working at once.

Kindling provides that, with four things:

1. **Guides.** Narrative, end-to-end documentation that follows data from generation to
   storage, exchange, analytics, quality measurement and decision support. The guides
   explain *why* each piece exists as well as how to run it.
2. **A reference stack.** Docker Compose profiles (and later Helm charts) that stand up a
   pinned, tested combination of tools with one command, loaded with synthetic data.
3. **Glue libraries.** Small, focused Python packages on PyPI (`kindling-*`) that handle
   the tedious parts: loading Synthea into any FHIR server, bulk export to Parquet/DuckDB,
   feeding FHIR into Tuva, and running CQL against different backends through one API.
4. **A hosted reference implementation.** A public, synthetic-data-only deployment where
   anyone can click through the EHR, query the FHIR API, run a quality measure and look
   at the resulting dashboards without installing anything.

> **Status:** planning. See [`docs/PLAN.md`](docs/PLAN.md) for the roadmap and
> [`docs/landscape.md`](docs/landscape.md) for the tool catalog.

## Principles

- **Tell the whole story.** Every guide ends with something running, and every component
  is explained in terms of the one before and after it.
- **Glue, don't fork.** Use upstream projects as released and fix problems upstream.
  Kindling owns only the seams between projects.
- **Pinned and proven.** Each supported combination of versions is tested end-to-end in
  CI. If it's on the compatibility matrix, it works.
- **One golden path, many alternatives.** An opinionated default stack, with documented
  swaps (a different FHIR server, CQL engine or warehouse) that pass the same tests.
- **Synthetic data only.** No PHI, ever, in this repository or the hosted demo.
- **License clarity.** Say plainly what is free to use, what needs a (free) license such
  as UMLS/VSAC, and what can't be redistributed, such as CPT codes.

## License

Apache-2.0 (proposed). Upstream components keep their own licenses. See the landscape doc.
