#!/usr/bin/env python3
"""
Nano Banana Pro - Image Generation Script
Generates images from text prompts using Google's Gemini 3 Pro Image model.

Usage:
    python generate_image.py "prompt" output.png [--aspect RATIO] [--size SIZE]

Examples:
    python generate_image.py "A cat wearing a wizard hat" cat.png
    python generate_image.py "Futuristic city" city.png --aspect 16:9 --size 2K
"""

import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Generate images with Gemini Nano Banana Pro")
    parser.add_argument("prompt", help="Text prompt for image generation")
    parser.add_argument("output", help="Output file path (e.g., output.png)")
    parser.add_argument("--aspect", default="1:1",
                        choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
                        help="Aspect ratio (default: 1:1)")
    parser.add_argument("--size", default="1K",
                        choices=["1K", "2K", "4K"],
                        help="Image resolution (default: 1K)")
    parser.add_argument("--model", default="gemini-3-pro-image-preview",
                        help="Model to use (default: gemini-3-pro-image-preview)")

    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("Error: google-genai package not installed. Run: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print(f"Generating image: '{args.prompt}'")
    print(f"Settings: aspect={args.aspect}, size={args.size}, model={args.model}")

    response = client.models.generate_content(
        model=args.model,
        contents=[args.prompt],
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE'],
            image_config=types.ImageConfig(
                aspect_ratio=args.aspect,
            )
        )
    )

    image_saved = False
    for part in response.parts:
        if part.inline_data:
            image = part.as_image()
            image.save(args.output)
            print(f"Image saved to: {args.output}")
            image_saved = True
            break
        elif part.text:
            print(f"Response text: {part.text}")

    if not image_saved:
        print("Warning: No image was generated in the response", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
