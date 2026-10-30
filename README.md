# sheet2midi

Converts PDF music sheet scans to MusicXML (`.mxl`, compressed MusicXML) with
[Audiveris](https://github.com/Audiveris/audiveris).

## Setup

Requires Python and Audiveris 5.11 (Java 25+).

```powershell
winget install --id audiveris.org.Audiveris --exact
```

## Usage

```powershell
python convert.py                     # everything in scans/
python convert.py scans\some-file.pdf # one file
```

Each PDF gets its own folder in `output/`, holding the `.mxl` and Audiveris's log and project file.
A score with several movements produces one `.mxl` per movement.

Pages without staves, such as covers and publisher ads, are skipped. The output is raw OMR and
contains recognition errors, so it needs checking against the scan.
