import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

SKILL_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_DIR / ".env")

DEFAULT_OUTPUT_DIR = SKILL_DIR / "assets" / "generated_images"
DEFAULT_DRIVER_PATH = Path("/Users/papazed/00_Publiac Account/scripts/gemini_driver.py")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate images from prompt entries using the local Gemini image driver."
    )
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        help="Prompt entry in the form name::prompt text. Repeatable.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated images.",
    )
    parser.add_argument(
        "--driver-path",
        default=os.getenv("GEMINI_DRIVER_PATH", str(DEFAULT_DRIVER_PATH)),
        help="Path to gemini_driver.py",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    return parser.parse_args()


def load_driver_module(driver_path: Path):
    if not driver_path.exists():
        raise FileNotFoundError(f"gemini_driver.py not found: {driver_path}")
    spec = importlib.util.spec_from_file_location("skill_gemini_driver", driver_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def parse_prompt_items(raw_items):
    items = []
    for raw in raw_items:
        if "::" not in raw:
            raise ValueError(f"Invalid --prompt value: {raw}")
        name, prompt = raw.split("::", 1)
        items.append({"name": name.strip(), "prompt": prompt.strip()})
    if not items:
        raise ValueError("No prompts provided. Use --prompt repeatedly.")
    return items


async def run_generation(args):
    items = parse_prompt_items(args.prompt)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    driver_module = load_driver_module(Path(args.driver_path).expanduser().resolve())
    driver = driver_module.AsyncGeminiDriver(headless=args.headless)
    await driver.start()
    try:
        for index, item in enumerate(items, start=1):
            print(f"[{index}/{len(items)}] Generating {item['name']}")
            generated = await driver.generate_image(item["prompt"], output_dir=str(output_dir))
            if not generated:
                print(f"   Failed: {item['name']}")
                continue
            generated_path = Path(generated)
            final_path = output_dir / item["name"]
            if final_path.suffix == "":
                final_path = final_path.with_suffix(generated_path.suffix or ".png")
            if generated_path.resolve() != final_path.resolve():
                generated_path.replace(final_path)
            print(f"   Saved: {final_path}")
    finally:
        await driver.close()


def main():
    args = parse_args()
    asyncio.run(run_generation(args))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
