# Parts of this file written with help from Claude.
import io
import random

import requests
from PIL import Image


def distance(a, b):
    """How different two colors are"""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def get_palette(url, k=5, iterations=10):
    """Find the k main colors of an image using k-means"""
    data = requests.get(url, timeout=10).content
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((100, 100))
    pixels = list(image.getdata())

    random.seed(42)
    centers = random.sample(pixels, k)
    groups = []

    for _ in range(iterations):
        # Step 1: put every pixel into the group of its closest center
        groups = [[] for _ in range(k)]
        for pixel in pixels:
            closest = min(range(k), key=lambda i: distance(pixel, centers[i]))
            groups[closest].append(pixel)

        # Step 2: move every center to the middle of its group
        for i, group in enumerate(groups):
            if group:
                centers[i] = tuple(sum(channel) // len(group) for channel in zip(*group))

    # Biggest groups first: the most important colors of the cover
    order = sorted(range(k), key=lambda i: len(groups[i]), reverse=True)
    return ["#{:02x}{:02x}{:02x}".format(*centers[i]) for i in order]
