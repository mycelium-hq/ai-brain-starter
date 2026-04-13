#!/usr/bin/env python3
"""
Nano Banana Pro - Google Search-Grounded Image Generation
Creates images using real-time data from Google Search.

Usage:
    python search_grounded_image.py "prompt" output.png [--aspect RATIO] [--size SIZE]

Examples:
    python search_grounded_image.py "Visualize today's weather in Tokyo as an infographic" weather.png
    python search_grounded_image.py "Create an infographic of current Bitcoin price trends" btc.png --aspect 16:9
    python search_grounded_image.py "Illustrate the latest news about AI" ai_news.png --size 2K

This enables:
- Live stock-market infographics
- Breaking-news visuals
- Real-time event visualizations
- Weather dashboards
- Current data visualizations
"""

import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Generate search-grounded images with Gemini Nano Banana Pro")
    parser.add_argument("prompt", help="Text prompt (can reference current/real-time data)")
    parser.add_argument("output", help="Output file path")
    parser.add_argument("--aspect", default="1:1",
                        choices=["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
                        help="Aspect ratio (default: 1:1)")
    parser.add_argument("--size", default="2K",
                        choices=["1K", "2K", "4K"],
                        help="Image resolution (default: 2K)")
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

    print(f"Generating search-grounded image: '{args.prompt}'")
    print(f"Settings: aspect={args.aspect}, size={args.size}")
    print("Searching for real-time data...")

    response = client.models.generate_content(
        model=args.model,
        contents=[args.prompt],
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE'],
            image_config=types.ImageConfig(
                aspect_ratio=args.aspect,
                image_size=args.size
            ),
            tools=[{"google_search": {}}]
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
