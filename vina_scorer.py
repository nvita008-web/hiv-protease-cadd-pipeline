import sys
import json
import os
import tempfile
import subprocess
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from multiprocessing import Pool, cpu_count

# Paths
VINA = "/opt/homebrew/bin/vina"
RECEPTOR = "/Users/nicolevita/Documents/Portfolio/1HVR_receptor.pdbqt"

# Docking box
CENTER = (-9.19, 15.91, 27.95)
SIZE = (19.97, 17.46, 27.10)

# Score transformation
SCORE_MIN = -12.0
SCORE_MAX = 0.0

def vina_score_to_reward(score):
    clipped = np.clip(score, SCORE_MIN, SCORE_MAX)
    return (clipped - SCORE_MAX) / (SCORE_MIN - SCORE_MAX)

def smiles_to_pdbqt(smi, tmpdir):
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    
    mol = Chem.AddHs(mol)
    result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    if result != 0:
        return None
    
    AllChem.MMFFOptimizeMolecule(mol)
    
    sdf_path = os.path.join(tmpdir, "ligand.sdf")
    writer = Chem.SDWriter(sdf_path)
    writer.write(mol)
    writer.close()
    
    pdbqt_path = os.path.join(tmpdir, "ligand.pdbqt")
    result = subprocess.run([
        "mk_prepare_ligand.py",
        "-i", sdf_path,
        "-o", pdbqt_path
    ], capture_output=True, text=True)
    
    if result.returncode != 0 or not os.path.exists(pdbqt_path):
        return None
    
    return pdbqt_path

def dock(pdbqt_path, tmpdir):
    out_path = os.path.join(tmpdir, "docked.pdbqt")
    
    result = subprocess.run([
        VINA,
        "--receptor", RECEPTOR,
        "--ligand", pdbqt_path,
        "--center_x", str(CENTER[0]),
        "--center_y", str(CENTER[1]),
        "--center_z", str(CENTER[2]),
        "--size_x", str(SIZE[0]),
        "--size_y", str(SIZE[1]),
        "--size_z", str(SIZE[2]),
        "--exhaustiveness", "2",
        "--num_modes", "1",
        "--out", out_path
    ], capture_output=True, text=True)
    
    for line in result.stdout.split('\n'):
        if line.strip().startswith('1'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass
    return 0.0

def dock_single(smi):
    """Dock a single SMILES — designed for multiprocessing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdbqt = smiles_to_pdbqt(smi, tmpdir)
        if pdbqt is None:
            return 0.0, 0.0
        raw = dock(pdbqt, tmpdir)
        return float(vina_score_to_reward(raw)), float(raw)

def main():
    smilies = [s.strip() for s in sys.stdin.readlines() if s.strip()]
    
    # Use all available CPUs minus 1
    n_cpus = max(1, cpu_count() - 1)
    
    with Pool(processes=n_cpus) as pool:
        results = pool.map(dock_single, smilies)
    
    scores = [r[0] for r in results]
    raw_scores = [r[1] for r in results]
    
    output = {
        "version": 1,
        "payload": {
            "docking_score": scores,
            "raw_vina_score": raw_scores
        }
    }
    
    print(json.dumps(output))

if __name__ == "__main__":
    main()