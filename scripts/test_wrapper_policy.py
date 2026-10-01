#!/usr/bin/env python3
"""Offline adversarial fixtures for verification-policy.json 2.2. Run: python3 scripts/test_wrapper_policy.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_mirror import check_html, TEMPLATE, TEMPLATES  # noqa: E402

HOST = "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/lovp_1dnx54hk2x8v1sxcvws2j8x4p3/"
OLD = HOST + "680c68439d4f80ff28d0bc14348216be_1790880801739.png"
NEW = HOST + "3720095dc287fc12b54291606fe501a5_1790881953604.png"
SOURCE = b'<!doctype html><html><head><meta charset="utf-8"><title>T | Permeate Lab</title></head><body><p>body</p></body></html>'
RECORDED = TEMPLATE.format(title="T", image=OLD)
DESC = "Summary of T."
SOURCE_WITH_OG = SOURCE.replace(b"<title>", f'<meta property="og:description" content="{DESC}"><title>'.encode(), 1)
RECORDED_WITH_DESC = TEMPLATES["title_description_image"].format(title="T", description=DESC, image=OLD)
OWN = "https://permeatelab.com/brand/permeatelab-og-1200x630.png"
SOURCE_WITH_IMG = SOURCE_WITH_OG.replace(b"<title>", f'<meta property="og:image" content="{OWN}"><meta name="twitter:image" content="{OWN}"><title>'.encode(), 1)
RECORDED_NO_IMG = TEMPLATES["title_description"].format(title="T", description=DESC)


def inject(block: str, source: bytes = SOURCE) -> bytes:
    i = source.index(b"</head>")
    return source[:i] + block.encode() + source[i:]


def block(title="T", image=NEW, image2=None, description=None):
    image2 = image if image2 is None else image2
    desc = "" if description is None else f'<meta name="twitter:description" content="{description}">'
    imgs = "" if image is None else f'<meta property="og:image" content="{image}"><meta name="twitter:image" content="{image2}">'
    return (f'<script defer src="/~flock.js" data-proxy-url="/~api/analytics"></script><meta name="twitter:title" content="{title}">'
            f'{desc}{imgs}')


FIXTURES = [
    ("exact source bytes", SOURCE, True),
    ("recorded block, identical", inject(RECORDED), True),
    ("recorded block with new valid image filename", inject(block()), True),
    ("extra meta tag inside block", inject(block() + '<meta name="x" content="y">'), False),
    ("extra script inside block", inject(block() + '<script src="/evil.js"></script>'), False),
    ("another image host", inject(block(image="https://evil.example/" + "a" * 32 + "_1790881953604.png")), False),
    ("another project prefix on same host", inject(block(image="https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/lovp_other/" + "a" * 32 + "_1790881953604.png")), False),
    ("unequal og:image and twitter:image", inject(block(image=NEW, image2=OLD)), False),
    ("block moved to start of head", SOURCE.replace(b"<head>", b"<head>" + block().encode()), False),
    ("source body edited", inject(block(), SOURCE.replace(b"body", b"edited")), False),
    ("twitter:title changed", inject(block(title="Other")), False),
    ("script attribute changed", inject(block().replace('data-proxy-url="/~api/analytics"', 'data-proxy-url="/~api/other"')), False),
    ("filename hash too short", inject(block(image=HOST + "a" * 31 + "_1790881953604.png")), False),
    ("filename not png", inject(block(image=HOST + "a" * 32 + "_1790881953604.svg")), False),
    ("two host blocks", inject(block() + block()), False),
    ("second closing head tag", inject(block()) + b"</head>", False),
    ("block missing twitter:image", inject(block().rsplit("<meta name=\"twitter:image\"", 1)[0]), False),
    ("http instead of https", inject(block(image=NEW.replace("https://", "http://"))), False),
    ("source head tag removed", inject(block()).replace(b"</head>", b"", 1), False),
    ("block before other head tags", SOURCE.replace(b"<title>", block().encode() + b"<title>"), False),
    ("description tag when source has no og:description", inject(block(description=DESC)), False),
]

DESC_FIXTURES = [
    ("source with og:description, exact source bytes", SOURCE_WITH_OG, True),
    ("description block, recorded, identical", inject(RECORDED_WITH_DESC, SOURCE_WITH_OG), True),
    ("description block with new valid image filename", inject(block(description=DESC), SOURCE_WITH_OG), True),
    ("description differs from source og:description", inject(block(description="Other text."), SOURCE_WITH_OG), False),
    ("description block missing twitter:description", inject(block(), SOURCE_WITH_OG), False),
    ("description block with extra tag", inject(block(description=DESC) + '<meta name="x" content="y">', SOURCE_WITH_OG), False),
    ("description block with unequal images", inject(block(description=DESC, image2=OLD), SOURCE_WITH_OG), False),
    ("description block, title changed", inject(block(title="Other", description=DESC), SOURCE_WITH_OG), False),
]


IMG_FIXTURES = [
    ("source with own images, exact source bytes", SOURCE_WITH_IMG, True),
    ("image-less block, recorded, identical", inject(RECORDED_NO_IMG, SOURCE_WITH_IMG), True),
    ("host image tags on a source with own images", inject(block(description=DESC), SOURCE_WITH_IMG), False),
    ("image-less block on a source without images", inject(block(image=None, description=DESC), SOURCE_WITH_OG), False),
    ("image-less block on a source without images or description", inject(block(image=None)), False),
    ("image-less block missing twitter:description", inject(block(image=None), SOURCE_WITH_IMG), False),
    ("image-less block, description differs", inject(block(image=None, description="Other text."), SOURCE_WITH_IMG), False),
    ("image-less block, title changed", inject(block(image=None, title="Other", description=DESC), SOURCE_WITH_IMG), False),
    ("image-less block with extra tag", inject(block(image=None, description=DESC) + '<meta name="x" content="y">', SOURCE_WITH_IMG), False),
    ("image-less block with extra script", inject(block(image=None, description=DESC) + '<script src="/evil.js"></script>', SOURCE_WITH_IMG), False),
    ("source own image edited", inject(block(image=None, description=DESC), SOURCE_WITH_IMG.replace(OWN.encode(), NEW.encode(), 1)), False),
]


def main():
    failed = 0
    cases = ([(SOURCE, RECORDED, f) for f in FIXTURES] + [(SOURCE_WITH_OG, RECORDED_WITH_DESC, f) for f in DESC_FIXTURES]
             + [(SOURCE_WITH_IMG, RECORDED_NO_IMG, f) for f in IMG_FIXTURES])
    for source, recorded, (name, live, expect) in cases:
        ok, mode, image, reason = check_html(source, live, recorded)
        status = "PASS" if ok == expect else "FAIL"
        failed += status == "FAIL"
        print(f"{status}  {'accept' if expect else 'reject'}  {name}  -> {mode}{(' : ' + reason) if reason else ''}")
    print(f"\n{len(cases) - failed}/{len(cases)} fixtures passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
