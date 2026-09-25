# Phase 1K.28 - Old-native software reference report

## Final classification

`GENERIC_ALE_ROLLBACK_STATE_CAUSAL`

The old authoritative mesh and its own native 30 s fields provide a valid
software-reference baseline for the tested one-window protocol. In B0, rollback
created an observable `meshPhi`/`meshPhi_0` runtime state absent at S0, and the
same-input attempts 3/4 produced different raw Fluid Force and adapter payload.
In B1, retaining only the existing G2 meshPhi canonicalization made all 15
paired solver-stage records equal and made direct raw Force and adapter
preWrite payload exactly repeatable. This supports the ALE rollback-state
mechanism on the tested old-native branch. It is an experimental diagnostic
result, not a production repair.

## Same-Fluid-input pair

Attempts 3 and 4 are valid in both B0 and B1:

| Quantity | Attempt 3 | Attempt 4 |
|---|---:|---:|
| Fluid read offset | `0.0002 s` | `0.0002 s` |
| Fluid read global time | `30 s` | `30 s` |
| Fluid read time index | `150000` | `150000` |
| displacement value count | 400 | 400 |
| displacement IEEE-754 SHA256 | `d32bcccbaeeca2e6685266c70dc358dfd0ba7a76ec226990fa27cc741b1fb339` | same |
| vertex-ID SHA256 | `de663cfb3b82787ec7c32624aba8cd8de6555fc906b507971a2c2f3207b5fe52` | same |

The pair is established from the complete Fluid `readData(Displacement)`
payload and timing identity, not inferred from Structure output.

## Force decomposition

### B0 old-native baseline

| Channel | Attempt 3 (N) | Attempt 4 (N) | Difference norm (N) |
|---|---:|---:|---:|
| pressure | `(-0.049222732356218483, -0.04205427689236253)` | `(-0.07706517482624795, -0.06705601731333005)` | `0.03742043060647941` |
| viscous | `(0.001634308720614958, 0.0005539861554143228)` | `(0.0016197674919248121, 0.0005409409198011974)` | `1.953523749589642e-05` |
| raw total | `(-0.047588423635603505, -0.04150029073694823)` | `(-0.0754454073343231, -0.06651507639352881)` | `0.03743996584180332` |
| adapter preWrite | same as raw total | same as raw total | `0.03743996584180332` |

All B0 per-face pressure, viscous, total, and 400-scalar payload hashes differ.

### B1 old-native G2 candidate

| Channel | Attempt 3 (N) | Attempt 4 (N) | Difference norm (N) |
|---|---:|---:|---:|
| pressure | `(-0.04224364385030843, -0.0357852107812658)` | same | `0` |
| viscous | `(0.0016379499747086125, 0.0005572535333593292)` | same | `0` |
| raw total | `(-0.04060569387559982, -0.03522795724790643)` | same | `0` |
| adapter preWrite | `(-0.04060569387559982, -0.03522795724790643)` | same | `0` |

The B1 pressure, viscous, total per-face hashes and complete adapter payload
hashes are equal between attempts 3/4. Fifteen paired stage records from S01
through S11 are equal after excluding only solve identity and process PID.

## Structure-side Force is downstream

B1 Structure reads remain different:

- attempt 3: `(0.04153131241933206, 0.03854455096128504) N`,
  `relativeReadTime=0.0002 s`;
- attempt 4: `(-0.04060569387559982, -0.03522795724790643) N`,
  `relativeReadTime=0 s`;
- difference norm: `0.1104032190226757 N`.

Because raw Fluid Force and adapter preWrite are exactly equal in B1, this
Structure discrepancy is downstream of the adapter write. The two reads are not
the same temporal request. This report does not claim IQN alone is the root
cause; the internal pre-acceleration vector was not directly observed.

## Required answers

1. Old authoritative mesh plus native restart consistent? **YES, scoped to the
   software reference input.**
2. Valid same-Fluid-input pair? **YES, attempts 3/4**, with the hash above.
3. Old-native rollback reproduces meshPhi/meshPhi_0 mismatch? **YES in B0**.
4. B1 raw pressure difference: **0 N**; viscous difference: **0 N**; raw
   total difference: **0 N**; adapter preWrite full-buffer difference: **0**.
5. Fluid operator repeatable? **SUPPORTED on the tested B1 G2 branch**. B0
   without G2 is **NOT_SUPPORTED** for this pair.
6. Is G2 required? **YES for this old-native baseline**, because B0 showed an
   effect-relevant mismatch and B1 removed the Force divergence.
7. Structure discrepancy downstream of adapter? **YES** for B1.
8. Comparison with K27 supports **C**: both tested branches are repeatable
   after G2, while downstream preCICE/Structure stateful behavior remains. This
   does not prove mapFields was the cause.
9. Next CFD inner-convergence A/B? **YES, authorized as the next diagnostic
   only on the B1 G2 software-reference branch**, not executed in K28. The gate
   is same Fluid input plus repeatable raw Force and preWrite payload.
10. IQN retest? **NO, not authorized.**

## Status and limitations

The one-window run reached the iteration ceiling and was **not converged**. No
claim is made about long-term old-mesh ALE stability, production mesh
suitability, HH06 validation, VIV validation, or a production adapter repair.
No fresh-process B1 A/B control was run after the B1 causal result because the
K28 stop rule required stopping once the minimal causal candidate restored the
tested raw/preWrite repeatability.

Evidence is preserved under:

- `evidence/phase1k28_old_native_reference/run-20260925T113000Z-fc0f94d-b0/`
- `evidence/phase1k28_old_native_reference/run-20260925T113000Z-fc0f94d-b1-g2b/`
