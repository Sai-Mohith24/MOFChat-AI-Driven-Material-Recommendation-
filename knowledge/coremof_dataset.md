# The CoRE-MOF dataset used by MOFChat

Source: Chung, Y. G. et al., "Advances, updates, and analytics for the computation-ready, experimental metal–organic framework database: CoRE MOF 2019", J. Chem. Eng. Data 64, 5985–5998 (2019); the table itself is the one distributed with ChatMOF (Kang & Kim, Nat. Commun. 15, 4705 (2024); figshare 24287731).

## What the table contains
CoRE MOF is a collection of experimentally synthesised MOF crystal structures (from the Cambridge Structural Database) that were cleaned so that they can be used directly in simulations ("computation-ready"). MOFChat uses the descriptor table with 12,020 MOFs and 17 columns. Each MOF is identified by its CSD refcode (for example ABAVIJ or FIQCEN) or, for structures taken from journal supporting information, by a file-based name such as c6ce00407e_c6ce00407e5.

## How the descriptors were computed
According to the ChatMOF methods section, the geometric descriptors were computed with Zeo++ (Willems et al., Microporous Mesoporous Mater. 149, 134–141 (2012)) in high-accuracy mode, using a hard-sphere probe of diameter 3.31 Å (nitrogen). "Accessible" therefore means "reachable by a 3.31 Å probe through the connected pore network".

## Column definitions
- Largest cavity diameter (LCD, Å): diameter of the largest sphere that fits anywhere in the pores.
- Pore limiting diameter (PLD, Å): diameter of the largest sphere that can pass through the pore network; it is set by the narrowest window and controls which molecules can diffuse through.
- Largest free pore diameter (LFPD, Å): the largest sphere that can travel along the free path. Always PLD ≤ LFPD ≤ LCD.
- Density (g/cm³): crystal density. The spreadsheet header says "cm^3/g" but the values are densities in g/cm³ (range 0.057–7.46).
- Accessible surface area (m²/g and m²/cm³): probe-accessible surface per gram and per volume.
- Non-accessible surface area and volume: pockets the probe cannot reach from the open network.
- Void fraction: fraction of the crystal volume that is accessible void (0–1).
- Accessible pore volume (cm³/g): accessible void volume per gram.
- Metal type, open metal site (yes/no) and the element(s) forming the open metal sites.

## Data-quality facts verified by MOFChat's ETL (setup_db.py)
- No missing values and no duplicate rows or names.
- "Accessible volume volume fraction" is identical to "void fraction", and "Accessible volume (cm³/g)" is identical to "Accessible pore volume (cm³/g)"; the duplicates are dropped.
- Pore volume equals void fraction divided by density (maximum relative error 6×10⁻⁶), and volumetric surface area equals gravimetric surface area times density. These columns are therefore derived, not independent information.
- 3,252 MOFs (27 %) have zero accessible surface area. Every one of them has PLD below 3.31 Å, and every MOF with PLD above 3.32 Å has non-zero accessible surface area: when the windows are narrower than the probe, nothing is accessible.
- 65 distinct metals; 2,087 MOFs contain more than one metal. Zn (2,347), Cu (1,901), Cd (1,207) and Co (1,164) are the most common. 66 % of MOFs are flagged as having an open metal site.

## What the table does not contain
There are no adsorption isotherms, gas uptakes, selectivities, stabilities or synthesis conditions in this table. Statements about gas uptake made by MOFChat are screening heuristics based on geometry, not measured or simulated uptakes. The hMOF folder in the project directory (hypothetical MOFs from the same figshare record) contains only structure and energy-grid files, no property table.
