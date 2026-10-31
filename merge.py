"""Join the .mxl files of each song, in page order, into one uncompressed MusicXML file."""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCTYPE = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">\n')
# Sets of instrument parts and songbooks: their .mxl files are not one continuous piece.
KEEP_SEPARATE = re.compile(r"_somsalon_|_som_populair_n0047$|_som_populair_81323_81323$")
DEFAULT_DIVISIONS = 16
DEFAULT_TIME = (4, 4)


def read_mxl(path):
    """Return the root element of the score inside an .mxl file."""
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        score_path = next(e.get("full-path") for e in container.iter() if e.tag == "rootfile")
        return ET.fromstring(z.read(score_path))


def movement_order(path):
    """Sort .mvt2.mxl before .mvt10.mxl."""
    match = re.search(r"\.mvt(\d+)\.mxl$", path.name)
    return int(match.group(1)) if match else 0


def count_notes(element):
    """Count the notes and rests inside an element."""
    return sum(1 for _ in element.iter("note"))


def time_at_each_measure(measures, start):
    """Return the time signature in force at each measure."""
    times = []
    current = start
    for measure in measures:
        time = measure.find("attributes/time")
        if time is not None and time.find("beats") is not None:
            try:
                current = (int(time.findtext("beats")), int(time.findtext("beat-type")))
            except (TypeError, ValueError):
                pass  # compound signatures such as 3+2 keep the previous value
        times.append(current)
    return times


def rest_measure(divisions, time, part_state):
    """Build a whole-measure rest, declaring divisions or time if the part needs them."""
    measure = ET.Element("measure")
    declare_divisions = part_state["divisions"] is None
    if declare_divisions:
        part_state["divisions"] = divisions
    if declare_divisions or part_state["time"] != time:
        attributes = ET.SubElement(measure, "attributes")
        if declare_divisions:
            ET.SubElement(attributes, "divisions").text = str(divisions)
        time_element = ET.SubElement(attributes, "time")
        ET.SubElement(time_element, "beats").text = str(time[0])
        ET.SubElement(time_element, "beat-type").text = str(time[1])
        part_state["time"] = time
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest", measure="yes")
    duration = round(part_state["divisions"] * 4 * time[0] / time[1])
    ET.SubElement(note, "duration").text = str(max(duration, 1))
    ET.SubElement(note, "voice").text = "1"
    return measure


def merge(scores):
    """Join scores in order and return (merged root, number of padding measures)."""
    merged = scores[0]
    part_list = merged.find("part-list")
    width = max(len(score.findall("part")) for score in scores)

    score_parts = []
    for index in range(width):
        source = next(s.findall("part-list/score-part")[index] for s in scores
                      if len(s.findall("part-list/score-part")) > index)
        score_parts.append(source)
    for child in list(part_list):
        part_list.remove(child)
    for index, score_part in enumerate(score_parts, start=1):
        score_part.set("id", f"P{index}")
        for element in score_part.iter():
            if element.get("id") and element is not score_part:
                element.set("id", f"P{index}-{element.tag}")
        part_list.append(score_part)

    collected = [[] for _ in range(width)]
    states = [{"divisions": None, "time": None} for _ in range(width)]
    padding = 0
    running_time = DEFAULT_TIME
    for score in scores:
        parts = [p.findall("measure") for p in score.findall("part")]
        length = max(len(m) for m in parts)
        reference = max(parts, key=len)
        times = time_at_each_measure(reference, running_time)
        running_time = times[-1]
        for index in range(width):
            state = states[index]
            measures = parts[index] if index < len(parts) else []
            for measure in measures:
                divisions = measure.find("attributes/divisions")
                if divisions is not None:
                    state["divisions"] = int(float(divisions.text))
                collected[index].append(measure)
            if measures:
                state["time"] = time_at_each_measure(measures, state["time"] or running_time)[-1]
            for position in range(len(measures), length):
                divisions = state["divisions"] or DEFAULT_DIVISIONS
                collected[index].append(rest_measure(divisions, times[position], state))
                padding += 1

    for part in merged.findall("part"):
        merged.remove(part)
    for index, measures in enumerate(collected, start=1):
        part = ET.SubElement(merged, "part", id=f"P{index}")
        for number, measure in enumerate(measures, start=1):
            measure.set("number", str(number))
            measure.attrib.pop("implicit", None)
            for note in measure.findall("note"):
                # Instrument ids point at the old part-list and are optional.
                for instrument in note.findall("instrument"):
                    note.remove(instrument)
            part.append(measure)
    return merged, padding


def merge_song(folder):
    """Write folder/<song>.xml from the song's .mxl files and return a summary line."""
    mxls = sorted(folder.glob("*.mxl"), key=movement_order)
    scores = [read_mxl(path) for path in mxls]
    expected_notes = sum(count_notes(score) for score in scores)
    merged, padding = merge(scores)

    target = folder / f"{folder.name}.xml"
    temporary = target.with_suffix(".xml.tmp")
    temporary.write_text(DOCTYPE + ET.tostring(merged, encoding="unicode"), encoding="utf-8")

    # Check what was written, not what is in memory.
    written = ET.parse(temporary).getroot()
    parts = written.findall("part")
    lengths = {len(part.findall("measure")) for part in parts}
    if count_notes(written) != expected_notes + padding:
        raise ValueError(f"expected {expected_notes + padding} notes, wrote {count_notes(written)}")
    if len(lengths) != 1:
        raise ValueError(f"parts have different lengths: {sorted(lengths)}")
    temporary.replace(target)
    return (f"{len(mxls)} file(s), {len(parts)} part(s), {lengths.pop()} measures, "
            f"{expected_notes} notes, {padding} padding measures")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()

    done = 0
    failed = []
    for folder in sorted(p for p in args.output.iterdir() if p.is_dir()):
        if not any(folder.glob("*.mxl")):
            continue
        if KEEP_SEPARATE.search(folder.name):
            (folder / f"{folder.name}.xml").unlink(missing_ok=True)
            print(f"{folder.name}: kept separate", flush=True)
            continue
        try:
            print(f"{folder.name}: {merge_song(folder)}", flush=True)
            done += 1
        except Exception as e:  # one bad song must not stop the rest
            print(f"{folder.name}: FAILED: {e}", flush=True)
            failed.append(folder.name)

    print(f"Done: {done} merged, {len(failed)} failed")
    if failed:
        print("Failed: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
