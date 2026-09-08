"""Run privately in your own terminal; discovery only, never sends inference."""
import asyncio
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from cloud_api.cheaper_inference import discover_models


async def main():
    print('Cheaper Inference: read-only model discovery. No translation or paid requests.')
    print('The key is hidden while typing and is not saved. Start with your FREE key.')
    key = getpass.getpass('API key (hidden): ').strip()
    try:
        models = await discover_models(key)
    except HTTPException as error:
        print(error.detail)
        return 1
    finally:
        key = None
    for model in models:
        print(f"{model['id']} | {model['pricing']} | USD/1M input={model['input_per_million_usd']} output={model['output_per_million_usd']}")
    print(f'{len(models)} text models. Catalog-free does not establish a zero-charge key restriction.')
    print('You may share the model names/labels above, but never the key.')
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
