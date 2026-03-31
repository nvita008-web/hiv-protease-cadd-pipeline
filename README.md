# HIV Protease Structure-Based Generative Design Pipeline

## Overview
An end-to-end computational drug discovery pipeline applying generative AI with physics-based scoring to identify novel HIV protease inhibitors. Built entirely in open source tools (REINVENT4, AutoDock Vina, RDKit, OpenMM) on a MacBook Air M-series CPU.

**Target:** HIV Protease (PDB: 1HVR)  
**Approach:** Transfer Learning → Reinforcement Learning with Vina Docking → MMGBSA → MD

---

## Why HIV Protease (1HVR)
1HVR is a well-validated target with extensive crystallographic data, diverse known inhibitor chemotypes, and published binding affinity data across multiple scaffolds. The well-characterized active site water network — particularly in the S1/S1' pockets — makes it an ideal system for demonstrating physics-based scoring. Water displacement thermodynamics are a dominant contributor to binding affinity in this system, informed by prior project experience with KRAS and ClpP, where tuning water energetics was found to be the primary driver of potency optimization.

---

## Pipeline Architecture

```
ChEMBL Actives → SMILES Cleaning → Transfer Learning → Focused Prior
                                                              ↓
                                              Reinforcement Learning (Vina Scoring)
                                                              ↓
                                                     Top Hits → UMAP
                                                              ↓
                                                 MMGBSA Re-scoring → MD
```

---

## Part 1: Dataset Preparation

### Source
- Database: ChEMBL (target ID: CHEMBL4523, HIV Protease)
- Filter: IC50 ≤ 1µM, binding assays only
- Initial pull: 2488 compounds

### Cleaning Pipeline
Raw ChEMBL data required significant preprocessing before use as a REINVENT training set. REINVENT's vocabulary is constrained to a subset of druglike SMILES tokens, requiring the following steps:

1. RDKit SMILES validation and canonicalization
2. Deduplication by canonical SMILES
3. Desalting via largest fragment selection
4. Stereochemistry removal (not required for scaffold-level transfer learning)
5. Filtering of unsupported REINVENT tokens: iodine, charged carbons (`[C-]`, `[C+]`), extended SMILES notation (`|`, `$`, `^`)

**Final dataset: 1887 unique, clean, druglike HIV protease actives**

The cleaning rationale: using known actives as the training corpus biases generation toward chemotypes with demonstrated target engagement, reducing the chemical space the RL campaign needs to explore. Stereochemistry was deliberately removed because transfer learning operates at the scaffold level — stereocenters are better addressed downstream during hit optimization.

---

## Part 2: Transfer Learning

### Concept
REINVENT4 provides a pretrained general prior trained on millions of druglike molecules from ChEMBL. This model understands the grammar of valid SMILES but generates from broad druglike space. Transfer learning fine-tunes this prior on a target-specific dataset, biasing subsequent generation toward chemotypes with demonstrated target engagement.

### Configuration
| Parameter | Value |
|-----------|-------|
| Base prior | `reinvent.prior` (REINVENT4, Zenodo) |
| Epochs | 10 |
| Batch size | 50 |
| Device | CPU (Apple MacBook Air M-series) |
| num_refs | 0 (dataset > 200 molecules) |
| Stereochemistry | Removed prior to training |

### Results
| Metric | Value |
|--------|-------|
| Final training NLL loss | ~27.9 |
| Fraction valid SMILES at epoch 10 | 98% |
| Training time | ~2.1 minutes |
| Output model | `hiv_protease_TL.model` |

### TensorBoard Metrics
**A_Mean NLL Loss:** All curves decrease smoothly across 10 epochs with no flattening or divergence, indicating stable learning. The model is successfully learning to assign higher probability to HIV protease-like chemotypes.

**B_Fraction Valid SMILES:** Maintained at ~98% throughout training, confirming the model retained chemical grammar while adapting to the target-focused distribution. The brief dip at epochs 5-6 reflects normal exploratory behavior before recovery.

**Sampled Structures:** Molecules generated at step 10 show recognizably druglike scaffolds with appropriate MW and complexity. Structural diversity is maintained, confirming the model has not collapsed to a single chemotype.

---

## Part 3: Receptor Preparation

### Structure Preparation (1HVR)
- Source: RCSB PDB
- Heteroatoms identified: CSO (modified cysteine, retained as protein), XK2 (native inhibitor, used for box definition then removed)
- Receptor cleaned using BioPython, standard amino acids only
- Protonation and PDBQT conversion via Meeko + ProDy

### Docking Box Definition
Native ligand XK2 coordinates used to define the docking box:

| Parameter | Value |
|-----------|-------|
| Center X | -9.19 Å |
| Center Y | 15.91 Å |
| Center Z | 27.95 Å |
| Size X | 19.97 Å |
| Size Y | 17.46 Å |
| Size Z | 27.10 Å |

### Validation
Native ligand XK2 redocked to validate box and receptor preparation. Top pose affinity: **-11.55 kcal/mol**. Visual inspection in PyMOL confirmed pose recapitulates crystal geometry. Note: bond order assignment required correction via RDKit template matching due to PDBQT format limitations — sp2 geometry is critical for accurate pose reproduction and scoring.

---

## Part 4: Reinforcement Learning Campaign (Pass 1)

### Scoring Function
A custom external scoring script (`vina_scorer.py`) interfaces REINVENT4 with AutoDock Vina via the `ExternalProcess` component. The pipeline for each generated molecule:

```
SMILES → RDKit 3D embedding (ETKDGv3) → MMFF optimization → Meeko PDBQT → Vina → Score
```

Vina scores (kcal/mol) transformed to [0,1] reward:
- Score of 0.0 = no binding (-12 kcal/mol anchor)  
- Score of 1.0 = perfect binding (0 kcal/mol anchor)

Multiprocessing enabled (9 parallel docking jobs on MacBook Air M-series, 10 logical CPUs).

### Configuration
| Parameter | Value |
|-----------|-------|
| Prior | `hiv_protease_TL.model` |
| Steps | 100 |
| Batch size | 16 |
| Exhaustiveness | 2 (speed optimized for RL) |
| Diversity filter | IdenticalMurckoScaffold |
| Device | CPU |

### Results
| Metric | Value |
|--------|-------|
| Total compounds generated | 1600 |
| Unique SMILES | 1596 (99.75%) |
| Average total score | 0.719 (smoothed) |
| Best docking score | -11.84 kcal/mol |
| Valid SMILES per step | ~97-100% |
| Wall time | ~1.95 hours |

### Top Hits (Pass 1)
| SMILES | Score | Vina (kcal/mol) | Step |
|--------|-------|-----------------|------|
| O=C(Nc1cccc2c1cnn2-c1cccc(C(F)(F)F)c1)Nc1cccc2ccc(C#CCN3CCC(F)C3)nc12 | 0.987 | -11.84 | 74 |
| NC1CC(c2ccncc2NC(=O)c2nc(-c3cc(F)cc(C4CCCCC4)n3)ccc2F)CC(F)(F)C1 | 0.980 | -11.76 | 14 |
| Cc1cc(-c2nc(C3CCN(c4ncc5c(n4)COC5(C)C)C3)oc2-c2cccc(C(=O)NC(C)C)c2)ccc1F | 0.978 | -11.73 | 93 |

Top hits outscore the native ligand redock (-11.55 kcal/mol), suggesting the RL campaign is generating compounds with favorable active site complementarity.

---

## Next Steps
- Pass 2: Extended 300-step run from checkpoint
- Pass 3: Multi-component scoring (Vina + LogD + MMGBSA)
- UMAP visualization of generated chemical space
- MD simulation of top hits in OpenMM

---

## Environment
- MacBook Air M-series, CPU only
- Google Colab T4 (tested, Mac CPU faster for this workload due to parallelization)
- Python 3.10, REINVENT4 v4.7.15, AutoDock Vina 1.2.7, RDKit, Meeko, OpenMM
