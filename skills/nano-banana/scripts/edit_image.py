#!/usr/bin/env python3
"""
Nano Banana Pro - Image Editing Script
Edits existing images based on text prompts using Google's Gemini 3 Pro Image model.

Usage:
    python edit_image.py input.png "editing instruction" output.png

Examples:
    python edit_image.py photo.png "Add a sunset to the background" edited.png
    python edit_image.py portrait.png "Remove the background" nobg.png
    python edit_image.py logo.png "Make the text bolder and add blue gradient" logo_v2.png
"""

import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Edit images with Gemini Nano Banana Pro")
    parser.add_argument("input", help="Input image file path")
    parser.add_argument("prompt", help="Editing instruction")
    parser.add_argument("output", help="Output file path")
    parser.add_argument("--aspect", default=None,
                        choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
                        help="Output aspect ratio (default: preserve original)")
    parser.add_argument("--model", default="gemini-3-pro-image-preview",
                        help="Model to use (default: gemini-3-pro-image-preview)")

    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
        from PIL import Image
    except ImportError as e:
        missing = "google-genai" if "genai" in str(e) else "Pillow"
        print(f"Error: {missing} package not installed. Run: pip install {missing}", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    img = Image.open(args.input)

    print(f"Editing image: '{args.input}'")
    print(f"Instruction: '{args.prompt}'")

    config_kwargs = {
        'response_modalities': ['TEXT', 'IMAGE']
    }
    if args.aspect:
        config_kwargs['image_config'] = types.ImageConfig(aspect_ratio=args.aspect)

    response = client.models.generate_content(
        model=args.model,
        contents=[args.prompt, img],
        config=types.GenerateContentConfig(**config_kwargs)
    )

    image_saved = False
    for part in response.parts:
        if part.inline_data:
            result_image = part.as_image()
            result_image.save(args.output)
            print(f"Edited image saved to: {args.output}")
            image_saved = True
            break
        elif part.text:
            print(f"Response text: {part.text}")

    if not image_saved:
        print("Warning: No image was generated in the response", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
