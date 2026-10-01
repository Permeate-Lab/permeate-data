#!/usr/bin/env python3
"""Offline adversarial fixtures for verification-policy.json 2.0. Run: python3 scripts/test_wrapper_policy.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_mirror import check_html, TEMPLATE  # noqa: E402

HOST = "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/lovp_1dnx54hk2x8v1sxcvws2j8x4p3/"
OLD = HOST + "680c68439d4f80ff28d0bc14348216be_1790880801739.png"
NEW = HOST + "3720095dc287fc12b54291606fe501a5_1790881953604.png"
SOURCE = b'<!doctype html><html><head><meta charset="utf-8"><title>T | Permeate Lab</title></head><body><p>body</p></body></html>'
RECORDED = TEMPLATE.format(title="T", image=OLD)


def inject(block: str, source: bytes = SOURCE) -> bytes:
    i = source.index(b"</head>")
    return source[:i] + block.encode() + source[i:]


def block(title="T", image=NEW, image2=None):
    image2 = image if image2 is None else image2
    return (f'<script defer src="/~flock.js" data-proxy-url="/~api/analytics"></script><meta name="twitter:title" content="{title}">'
            f'<meta property="og:image" content="{image}"><meta name="twitter:image" content="{image2}">')


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
]


def main():
    failed = 0
    for name, live, expect in FIXTURES:
        ok, mode, image, reason = check_html(SOURCE, live, RECORDED)
        status = "PASS" if ok == expect else "FAIL"
        failed += status == "FAIL"
        print(f"{status}  {'accept' if expect else 'reject'}  {name}  -> {mode}{(' : ' + reason) if reason else ''}")
    print(f"\n{len(FIXTURES) - failed}/{len(FIXTURES)} fixtures passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
