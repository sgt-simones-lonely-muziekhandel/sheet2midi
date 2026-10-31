"""Convert PDF scans to MusicXML (.mxl) with Audiveris."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIVERIS = Path(r"C:\Program Files\Audiveris\Audiveris.exe")
TIMEOUT_SECONDS = 4 * 60 * 60


def pdf_to_mxl(pdf, output, audiveris):
    """Run Audiveris on one PDF and return the MXL files it exported."""
    out_dir = output / pdf.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    # A page without staves (such as a cover) makes Audiveris exit with an error
    # before exporting, so export from the saved project in a second pass. That
    # pass skips the invalid pages.
    subprocess.run(
        [str(audiveris), "-batch", "-transcribe",
         "-output", str(out_dir), "--", str(pdf)],
        timeout=TIMEOUT_SECONDS,
        capture_output=True,
    )
    subprocess.run(
        [str(audiveris), "-batch", "-export",
         "-output", str(out_dir), "--", str(out_dir / f"{pdf.stem}.omr")],
        check=True,
        timeout=TIMEOUT_SECONDS,
        capture_output=True,
    )
    # A score with several movements exports one .mvtN.mxl file per movement.
    mxls = sorted(out_dir.rglob("*.mxl"))
    if not mxls:
        raise RuntimeError("Audiveris exported no MXL (check the .log in the output folder)")
    return mxls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="*", type=Path,
                        help="PDFs to convert (default: everything in scans/)")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--audiveris", type=Path, default=DEFAULT_AUDIVERIS)
    args = parser.parse_args()

    # Smallest first, so an interrupted run has finished as many scores as possible.
    pdfs = args.pdfs or sorted((ROOT / "scans").glob("*.pdf"), key=lambda p: p.stat().st_size)
    if not pdfs:
        sys.exit("No PDFs found")

    failed = []
    for pdf in pdfs:
        if any((args.output / pdf.stem).glob("*.mxl")):
            print(f"{pdf.name}: already converted, skipping", flush=True)
            continue
        print(f"{pdf.name}: converting...", flush=True)
        try:
            mxls = pdf_to_mxl(pdf, args.output, args.audiveris)
        except Exception as e:  # one bad scan must not stop the rest of the batch
            print(f"{pdf.name}: FAILED: {e}", flush=True)
            failed.append(pdf.name)
        else:
            print(f"{pdf.name}: wrote {len(mxls)} MXL file(s)", flush=True)

    print(f"Done: {len(pdfs) - len(failed)} of {len(pdfs)} succeeded")
    if failed:
        print("Failed: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
