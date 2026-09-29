# V2606 NM14 offline analysis package

This upload contains the offline NM14.1 postprocessing correction and its NM14.2 modal-family / distributed lift-coefficient correction.

## Authoritative latest interpretation

Use `v2606_nm14_2_modal_cl_correction/comparison/final_report.md` and its `comparison/final_classification.json` for the corrected modal and Cl conclusions. NM14.1 is retained as the historical Phase NM14.1 result; its raw-eigenvector modal labels and Cl source-definition status are superseded by NM14.2.

## Contents

- Analysis scripts for NM14.1 and NM14.2.
- Windowed response, frequency, hydrodynamic, modal-family, and Cl result JSON files.
- Six-family / twelve-eigenvector modal basis outputs and the M/K matrices used to generate them.
- Huera-Huarte source audit with thesis page and equation references.
- Full reports and classification records.
- Corrected editable SVG and PDF figures from NM14.1.

The thesis PDF was supplied from the user's Zotero library and is intentionally not copied here. The 10 s NM13 CFD fields, force histories, structural state records, raw OpenFOAM logs, and large raster/TIFF duplicates are also excluded.

## Re-running the scripts

These scripts require the completed NM13/NM14 input artifacts, which are intentionally excluded from this upload. With those artifacts available, set `V2606_PROJECT_ROOT` to the project root for NM14.1, and `V2606_EVIDENCE_ROOT` to its evidence directory for NM14.2. NM14.2 reads the NM14.1 modal matrices and writes into its own evidence folder.

No CFD, preCICE, or Structure execution is part of these scripts.
