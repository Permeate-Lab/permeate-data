#!/usr/bin/env python3
"""Verify or regenerate mirror-manifest.json against the live canonical publication.

  python3 scripts/verify_mirror.py --verify
  python3 scripts/verify_mirror.py --regenerate [--previous receipts/<old>.json]

Policy: verification-policy.json (2.2). Standard library only.
"""
import argparse, datetime, hashlib, json, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = json.loads((ROOT / "verification-policy.json").read_text())
IMAGE_RE = re.compile(POLICY["html"]["image_url_pattern"])
TEMPLATES = POLICY["html"]["block_templates"]
TEMPLATE = TEMPLATES["title_image"]
OG_DESCRIPTION_RE = re.compile(rb'<meta property="og:description" content="([^"<>]*)">')
OG_IMAGE_RE = re.compile(rb'<meta property="og:image" content="[^"<>]*">')
TW_IMAGE_RE = re.compile(rb'<meta name="twitter:image" content="[^"<>]*">')
HEAD_CLOSE = b"</head>"
RECORDED_HEADERS = ("x-deployment-id", "content-type", "cache-control", "cf-ray", "x-robots-tag")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_block(block: bytes):
    """Return (title, image_url_or_None, description_or_None) when block matches one recorded shape exactly, else None."""
    for template in TEMPLATES.values():
        pattern = re.escape(template.encode()).replace(rb"\{title\}", rb"(?P<title>[^\"<>]*)", 1)
        pattern = pattern.replace(rb"\{description\}", rb"(?P<description>[^\"<>]*)", 1)
        pattern = pattern.replace(rb"\{image\}", rb"(?P<image>[^\"<>]*)", 1)
        pattern = pattern.replace(rb"\{image\}", rb"(?P=image)", 1)
        m = re.fullmatch(pattern, block)
        if m:
            groups = m.groupdict()
            desc, image = groups.get("description"), groups.get("image")
            return m.group("title").decode(), (image.decode() if image is not None else None), (desc.decode() if desc is not None else None)
    return None


def source_declares_images(source: bytes) -> bool:
    return len(OG_IMAGE_RE.findall(source)) == 1 and len(TW_IMAGE_RE.findall(source)) == 1


def source_og_description(source: bytes):
    found = OG_DESCRIPTION_RE.findall(source)
    return found[0].decode() if len(found) == 1 else None


def check_html(source: bytes, live: bytes, recorded_block: str | None):
    """Apply policy 2.2 to one HTML document.

    Returns (ok, mode, image_url, reason).
    """
    if live == source:
        return True, "exact_source", None, ""
    if source.count(HEAD_CLOSE) != 1:
        return False, "reject", None, "source does not contain exactly one closing head tag"
    if live.count(HEAD_CLOSE) != 1:
        return False, "reject", None, "live does not contain exactly one closing head tag"
    cut = source.index(HEAD_CLOSE)
    prefix, suffix = source[:cut], source[cut:]
    if not live.startswith(prefix) or not live.endswith(suffix):
        return False, "reject", None, "source bytes outside the host block differ or block is not immediately before the closing head tag"
    block = live[len(prefix): len(live) - len(suffix)]
    parsed = parse_block(block)
    if parsed is None:
        return False, "reject", None, "host block does not match the permitted template shape"
    title, image, description = parsed
    if image is None and not source_declares_images(source):
        return False, "reject", None, "image-less host block on a source that declares no og:image and twitter:image"
    if image is not None and source_declares_images(source):
        return False, "reject", image, "host image tags on a source that declares its own og:image and twitter:image"
    if image is not None and not IMAGE_RE.match(image):
        return False, "reject", image, "image URL outside the permitted host, project prefix or filename pattern"
    if description is not None and description != source_og_description(source):
        return False, "reject", image, "twitter:description differs from the source og:description"
    if recorded_block is not None:
        rec = parse_block(recorded_block.encode())
        if rec is None:
            return False, "reject", image, "recorded block is malformed"
        if rec[0] != title:
            return False, "reject", image, "twitter:title differs from the recorded block"
        expected = (recorded_block if rec[1] is None or image is None else recorded_block.replace(rec[1], image)).encode()
        if block != expected:
            return False, "reject", image, "host block differs from the recorded block beyond the image filename"
    return True, "source_plus_bounded_host_block", image, ""


def deployment_uuid(header: str) -> str:
    """x-deployment-id is psr2.<deployment uuid>.<counter>.<signature>; only the uuid is stable."""
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", header)
    return m.group(0) if m else header


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": POLICY["transport"]["user_agent"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        headers = {k: r.headers.get(k) for k in RECORDED_HEADERS if r.headers.get(k)}
        return r.status, body, headers


def payload_files():
    return sorted(p for p in (ROOT / "payload").rglob("*") if p.is_file())


def run(manifest: dict | None, previous: dict | None, regenerate: bool):
    base = (manifest or previous or {}).get("canonical_base") or POLICY.get("canonical_base") or "https://permeatelab.com/research/northwest-florida-engineering-costs/"
    started = datetime.datetime.now(datetime.timezone.utc)
    files = {}
    failures = []
    url_changes = []
    for path in payload_files():
        key = path.relative_to(ROOT / "payload").as_posix()
        local = path.read_bytes()
        recorded = (manifest or {}).get("files", {}).get(key)
        prior = (previous or manifest or {}).get("files", {}).get(key)
        url = recorded["origin_url"] if recorded else base + key
        try:
            status, live, headers = fetch(url)
        except Exception as exc:  # noqa: BLE001
            failures.append((key, f"fetch failed: {exc}"))
            continue
        if status != POLICY["transport"]["required_http_status"]:
            failures.append((key, f"http {status}"))
            continue
        entry = {
            "path": f"payload/{key}", "origin_url": url, "sha256": sha256(local), "bytes": len(local),
            "http_status": status, "live_raw_sha256": sha256(live), "response_headers": headers,
        }
        if recorded and recorded.get("sha256") != entry["sha256"]:
            failures.append((key, "payload file differs from the manifest it is checked against"))
        if path.suffix == ".html":
            rec_block = (recorded or {}).get("host_block_utf8") or (recorded or {}).get("injected_block_utf8")
            ok, mode, image, reason = check_html(local, live, rec_block)
            entry.update({"parity_mode": mode, "host_block_image_url": image})
            if ok and mode == "source_plus_bounded_host_block":
                cut = local.index(HEAD_CLOSE)
                block = live[cut: len(live) - (len(local) - cut)]
                entry["host_block_utf8"] = block.decode()
                entry["host_block_sha256"] = sha256(block)
                entry["host_block_location"] = "Immediately before the sole closing head tag"
                entry["live_normalized_sha256"] = sha256(local)
                prior_block = (prior or {}).get("host_block_utf8") or (prior or {}).get("injected_block_utf8")
                prior_img = parse_block(prior_block.encode())[1] if prior_block and parse_block(prior_block.encode()) else None
                if prior_img and prior_img != image:
                    url_changes.append((key, prior_img, image))
                entry["host_block_image_url_changed_since_previous"] = bool(prior_img and prior_img != image)
            if not ok:
                failures.append((key, reason))
        else:
            entry["parity_mode"] = "exact_raw"
            if live != local:
                failures.append((key, "live bytes differ from payload"))
        files[key] = entry
    finished = datetime.datetime.now(datetime.timezone.utc)
    html_ok = sum(1 for k, e in files.items() if k.endswith(".html") and e["parity_mode"] != "reject" and not any(f[0] == k for f in failures))
    raw_ok = sum(1 for k, e in files.items() if not k.endswith(".html") and not any(f[0] == k for f in failures))
    summary = {
        "policy_version": POLICY["policy_version"], "observation_started": started.isoformat(), "observation_finished": finished.isoformat(),
        "files_total": len(files) + len({f[0] for f in failures} - set(files)), "html_pass": html_ok, "html_total": sum(1 for k in files if k.endswith(".html")),
        "non_html_raw_pass": raw_ok, "non_html_total": sum(1 for k in files if not k.endswith(".html")),
        "failures": [{"file": k, "reason": r} for k, r in failures],
        "image_url_changes": [{"file": k, "previous": a, "current": b} for k, a, b in url_changes],
        "deployment_ids": sorted({deployment_uuid(e["response_headers"].get("x-deployment-id")) for e in files.values() if e["response_headers"].get("x-deployment-id")}),
    }
    out = None
    if regenerate and not failures:
        src = manifest or previous or {}
        out = {
            "publisher": src.get("publisher", "Permeate Lab"), "publisher_affiliation": src.get("publisher_affiliation", "Nova3 AI"),
            "canonical_base": base, "release_id": src.get("release_id"), "policy_version": POLICY["policy_version"], "policy_file": "verification-policy.json",
            "payload_representation": "Exact reviewed public source bytes. Non-HTML live bytes must match exactly. HTML live bytes must equal source or source plus one bounded host block (verification-policy.json " + POLICY["policy_version"] + "). No raw HTML equality claim. Preview responses excluded.",
            "live_parity_status": "verified_under_policy_" + POLICY["policy_version"], "verified_at": finished.isoformat(),
            "observation_started": started.isoformat(), "previous_receipt": src.get("_receipt_path"),
            "file_count": len(files), "files": files,
        }
    return summary, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--manifest", default="mirror-manifest.json")
    ap.add_argument("--previous")
    ap.add_argument("--out", default="mirror-manifest.json")
    a = ap.parse_args()
    manifest = json.loads((ROOT / a.manifest).read_text()) if (ROOT / a.manifest).exists() else None
    previous = None
    if a.previous:
        previous = json.loads((ROOT / a.previous).read_text())
        previous["_receipt_path"] = a.previous
    if a.regenerate:
        summary, out = run(None, previous or manifest, regenerate=True)
        if out:
            (ROOT / a.out).write_text(json.dumps(out, indent=2) + "\n")
            summary["written"] = a.out
    else:
        if manifest is None:
            print("no manifest to verify", file=sys.stderr); sys.exit(2)
        summary, _ = run(manifest, previous, regenerate=False)
    print(json.dumps(summary, indent=2))
    sys.exit(1 if summary["failures"] else 0)


if __name__ == "__main__":
    main()
