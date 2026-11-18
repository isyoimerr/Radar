"""Export a clean snapshot of attributed news for Vercel."""

import argparse
from pathlib import Path

from radar import store
from radar.catalog import export_catalog, import_catalog
from radar.pipeline import collect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--collect', action='store_true', help='Run an RSS collection before exporting')
    parser.add_argument('--previous', type=Path, help='Retain public headlines from the previous snapshot')
    args = parser.parse_args()
    if args.previous:
        store.init()
        import_catalog(args.previous.read_bytes())
    if args.collect:
        collect(enable_ai=False)
    print(f'{export_catalog(args.output)} noticias públicas exportadas')


if __name__ == '__main__':
    main()
