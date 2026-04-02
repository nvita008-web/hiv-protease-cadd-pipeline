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
                                                 Consensus Selection → MD
                                                              ↓
                                                 MMGBSA Re-scoring (planned)
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

## Part 4: Reinforcement Learning Scoring Function

### Design
A custom external scoring script (`vina_scorer.py`) interfaces REINVENT4 with AutoDock Vina via the `ExternalProcess` component. The pipeline for each generated molecule:

```
SMILES → RDKit 3D embedding (ETKDGv3) → MMFF optimization → Meeko PDBQT → Vina → Score
```

Vina scores (kcal/mol) transformed to [0,1] reward:
- Score of 0.0 = no binding (-12 kcal/mol anchor)
- Score of 1.0 = perfect binding (0 kcal/mol anchor)

Multiprocessing enabled (9 parallel docking jobs on MacBook Air M-series, 10 logical CPUs).

### RL Configuration
| Parameter | Value |
|-----------|-------|
| Prior | `hiv_protease_TL.model` |
| Steps per pass | 100 (Pass 1), 300 (Passes 2-4) |
| Batch size | 16 |
| Exhaustiveness | 2 (speed optimized for RL) |
| Diversity filter | IdenticalMurckoScaffold |
| Device | CPU |

---

## Part 5: Multi-Pass RL Campaign Results

### Campaign Summary
| Pass | Steps | Compounds Generated | Best Vina (kcal/mol) | Unique SMILES |
|------|-------|--------------------|-----------------------|---------------|
| Pass 1 | 100 | 368 | -11.52 | 365 |
| Pass 2 | 300 | 4800 | -13.25 | 4764 |
| Pass 3 | 300 | 4800 | -12.73 | 4771 |
| Pass 4 | 300 | 4800 | -13.12 | 4768 |
| **Total** | **1000** | **14,968** | **-13.25** | **14,226** |

All passes consistently outperformed the native ligand redock (-11.55 kcal/mol), with the best generated compound scoring -13.25 kcal/mol — a 1.7 kcal/mol improvement.

### Key Observations
Generated compounds are dominated by fused aromatic cores consistent with the hydrophobic character of the HIV protease S1/S1' pockets. This is mechanistically expected — the large hydrophobic pockets lined with Leu23, Leu24, Ile50, Ile84, and Val82 favor flat, rigid aromatic systems that maximize van der Waals contact while displacing ordered water molecules. The model learned this preference directly from the docking scores without explicit pharmacophore constraints, supporting the validity of the physics-based scoring approach.

---

## Part 6: Chemical Space Analysis

### UMAP by RL Pass (ECFP6, n=14,226)
Four independent RL campaigns colored by pass. Chemical space is well distributed across all passes with no single pass dominating, confirming the diversity filter is functioning correctly and the agent continues exploring rather than collapsing to previously found solutions.

### UMAP by Murcko Scaffold
Top 10 Murcko scaffolds identified across the full campaign. Despite 14,226 unique compounds, 4,554 unique scaffolds were identified — indicating meaningful scaffold-level convergence around HIV protease-relevant chemotypes. The pyridine-amide core dominates the most populated region, consistent with known HIV protease SAR. The fused aromatic dominance is mechanistically consistent with the hydrophobic S1/S1' pocket geometry.

### SAR Observations
Two dominant chemotype families emerge across the full 4-pass campaign, each mechanistically consistent with known HIV protease pharmacology.

The first is a pyridine/pyrimidine-amide series (Scaffolds 1, 2, 5, 6) with piperidine or cyclohexyl capping groups. The amide carbonyl is the key pharmacophoric element, positioned to interact with the catalytic Asp25/Asp25' dyad, mimicking the transition state of the natural substrate cleavage reaction. This is the most populated scaffold family and presents clean SAR vectors for medicinal chemistry optimization: the capping group, the heterocycle, and the amide substitution pattern can all be varied independently.

The second family is an indole-heterocycle series (Scaffolds 3, 7, 8, 9, 10) featuring oxadiazole, oxazole, or thiadiazole appendages on an indole core. The indole NH provides a hydrogen bond donor for interaction with the flap water molecule or backbone carbonyls, while the fused aromatic system fills the hydrophobic S1/S1' pockets. The variation in the distal heterocycle across scaffolds 7-10 represents a natural bioisostere series worth prosecuting.

The highest-scoring consensus hits likely combine a carbonyl or hydrogen bond donor positioned toward the catalytic dyad and an extended aromatic system filling the hydrophobic core. This dual pharmacophore hypothesis will be tested directly in the OpenMM MD simulations by monitoring Asp25/Asp25' contact distances and water displacement in the S1/S1' pockets. This hypothesis could be further tested using a QM/MM calculation to identify the transition state structure of the endogenous ligand and comparing to predicted actives that may mimic the transition state.

For a prospective HTS campaign, R-group enumeration around the pyridine-amide core and the indole-oxadiazole series would be the recommended starting point. A quick validation for the pyridine amide core and indole-oxadiazole could be to order available ligands with those cores and test against the HIV protease before building an entire HTS campaign around those scaffold groups.

---

## Part 7: Consensus Hit Selection for MD Simulation

### Methodology
Exact SMILES matching across passes yields zero consensus hits due to the generative model's inherent diversity. Instead, a Tanimoto similarity threshold of ≥0.15 (ECFP6) was applied — compounds in the top 20 of any pass with at least one structural neighbor scoring similarly in 2 or more other passes were selected. This approach identifies chemotypes that are reproducibly sampled across independent campaigns, reducing the likelihood of selecting docking artifacts.

### Consensus Hits Selected for MD (n=10)
| SMILES | Vina (kcal/mol) | Passes | Source |
|--------|-----------------|--------|--------|
| O=C(Nc1cc2ncc(-c3ccc4ccccc4c3)cc2n1C1CCCNC1)c1ccc2cc(Cl)ccc2c1 | -13.25 | 3 | Pass 2 |
| O=C(Nc1ccccc1)c1scc2ccc(-c3c(-c4ccccc4)nnc4cc(-c5cccc(OC(F)(F)F)c5)ccc34)cc12 | -13.12 | 2 | Pass 4 |
| O=c1ccccn1-c1cccc(-c2ccnc3cc(-c4ccc(CN5CCC(n6c(=O)[nH]c7ccccc76)CC5)cc4F)ccc23)c1 | -12.98 | 3 | Pass 4 |
| CC(=O)Nc1ccc2ccc(-c3nc(-c4ccc5cc(-c6cc7cc(F)ccc7[nH]6)ccc5c4)c[nH]3)cc2c1 | -12.88 | 2 | Pass 4 |
| Nc1ccc(C#Cc2ccc(Nc3cnc4c(-c5nc6cc(C(=O)O)ccc6[nH]5)cccc4c3-c3cccc(C(=O)Nc4c(F)cccc4F)c3)cc2)cc1 | -12.84 | 2 | Pass 4 |
| CN1CCN(Cc2ccc(-c3nc4c(nc3-c3c(F)cccc3F)c(N3CCCC(N)C3)nc3ccccc34)cc2)CC1 | -12.77 | 3 | Pass 2 |
| Oc1cc2cc(-c3cccc(-c4nccc5c(-c6ccc7ccc(Br)cc7c6)cccc45)c3)ccc2[nH]1 | -12.73 | 3 | Pass 3 |
| Cc1nc2cccc(-c3ccc4ncn(-c5ccc(CNC6CCN(C)CC6)cc5)c(=O)c4c3)c2nc1N1CCCN2C(=O)c3ccccc3CC21 | -12.66 | 2 | Pass 3 |
| Cn1c(NC(C)(C)C)nc2cc(-c3cccc4ccc(N5CCN(c6ccc7cc(C(=O)O)ccc7c6Cl)CC5)cc34)ccc2c1=O | -12.61 | 2 | Pass 3 |
| Cc1cc(F)ccc1-c1cnc2c(-c3ccc4c(C(=O)Nc5ccc6ccccc6c5)cccc4c3)[nH]nc2c1 | -12.56 | 3 | Pass 3 |

---

## Part 8: MD Simulation (In Progress)

Top 10 consensus hits will be subjected to explicit solvent MD simulation in OpenMM to:
- Assess binding pose stability over simulation time
- Calculate MM-GBSA binding free energies
- Identify key protein-ligand interactions — particularly carbonyl interactions with the catalytic Asp25/Asp25' dyad
- Validate the water displacement hypothesis in the S1/S1' pockets

---

## Environment
- MacBook Air M-series, CPU only
- Google Colab T4 (tested, Mac CPU faster for this workload due to parallelization)
- Python 3.10, REINVENT4 v4.7.15, AutoDock Vina 1.2.7, RDKit, Meeko, OpenMM

## Dependencies
```
reinvent4
autodock-vina
meeko
biopython
prody
gemmi
rdkit
openmm
umap-learn
plotly
```
