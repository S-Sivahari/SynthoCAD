"""SynthoCAD LLM CLI - Natural Language to STEP Pipeline

This CLI uses the main SynthoCadPipeline to convert natural language
prompts into parametric CAD models (STEP files).

Usage:
    python backend/llm_cli.py
    python backend/llm_cli.py -p "Create a cylinder 10mm radius and 20mm height"
"""
import sys
import argparse
from pathlib import Path

# Ensure backend directory is on sys.path
sys.path.append(str(Path(__file__).parent))

from core.main import SynthoCadPipeline


def main():
    parser = argparse.ArgumentParser(
        description="SynthoCAD LLM CLI - Convert natural language to CAD models (STEP files)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python backend/llm_cli.py -p "Create a cylinder 10mm radius, 20mm tall"
  python backend/llm_cli.py -p "Make a box 50x30x10 mm" 
  python backend/llm_cli.py  # Interactive mode
        """
    )
    parser.add_argument("-p", "--prompt", help="Natural language prompt describing the CAD part                                                                                         ")
    parser.add_argument("--no-freecad", action="store_true", help="Don't open result in FreeCAD")
    args = parser.parse_args()

    print("=" * 60)
    print("  SynthoCAD LLM CLI - Natural Language to STEP Pipeline")
    print("=" * 60)

    # Get prompt from args or interactive input
    if args.prompt:
        prompt = args.prompt
    else:
        print("\nEnter your CAD description (e.g., 'Create a cylinder 10mm radius, 20mm tall'):")
        prompt = input("> ").strip()
        if not prompt:
            print("Error: Empty prompt. Exiting.")
            sys.exit(1)

    print(f"\nPrompt: {prompt}")
    print("-" * 60)

    # Use the main pipeline
    pipeline = SynthoCadPipeline()
    result = pipeline.process_from_prompt(prompt, open_freecad=not args.no_freecad)

    print("-" * 60)
    
    if result['status'] == 'success':
        print("\n[SUCCESS] Pipeline completed!")
        print(f"  JSON:       {result['json_file']}")
        print(f"  Python:     {result['py_file']}")
        print(f"  STEP:       {result['step_file']}")
        print(f"  Parameters: {result['parameters']['total_count']} found")
        if result.get('freecad_opened'):
            print(f"  FreeCAD:    Opened")
    else:
        print(f"\n[FAILED] {result['error']}")
        sys.exit(1)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
