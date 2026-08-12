#!/usr/bin/env python3
"""Runtime entrypoint for the RAG ingestion pipeline.

The command contract is intentionally stable so the KFP pipeline can use a single
image for all stages. Stage implementations are added incrementally without
changing the BuildConfig/ImageStream integration.
"""
import argparse
import logging

STAGES = (
    "fetch-redhat",
    "fetch-confluence",
    "detect-changes",
    "normalize",
    "chunk",
    "embed",
    "index-pgvector",
    "validate",
)

def main() -> int:
    parser = argparse.ArgumentParser(prog="rag-ingestion")
    parser.add_argument("stage", choices=STAGES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting RAG ingestion stage: %s", args.stage)
    # Deliberate guard: the Helm/BuildConfig layer is complete, while the
    # source-specific ingestion logic will be implemented once final endpoints,
    # bucket, spaces, pgvector schema and embedding model are fixed.
    raise RuntimeError(f"Stage implementation pending: {args.stage}")

if __name__ == "__main__":
    raise SystemExit(main())
