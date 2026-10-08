# Application screening heuristics used by MOFChat

MOFChat's database contains geometry only, so application recommendations are transparent screening heuristics. They narrow 12,020 MOFs down to promising candidates. They do not replace adsorption simulations (GCMC) or experiments. Each heuristic is applied as explicit constraints and objectives that are shown to the user, and the user's own numeric constraints always take precedence.

## Hydrogen storage
- Physical basis: at cryogenic temperature (77 K), excess H2 uptake in porous materials grows roughly linearly with surface area, about 1 wt % per 500 m²/g ("Chahine's rule"; see for example Wong-Foy, Matzger & Yaghi, J. Am. Chem. Soc. 128, 3494 (2006)).
- Heuristic: PLD ≥ 2.89 Å (H2 must enter); maximise gravimetric accessible surface area and void fraction.
- Caveat: at room temperature, binding is too weak for this rule to give useful capacity; volumetric capacity also matters for tanks.

## Methane (natural gas) storage
- Physical basis: what matters for vehicles is volumetric deliverable capacity (cm³ of gas stored per cm³ of adsorbent, between charging and discharge pressure). That favours many adsorption sites per unit volume and enough free volume (see Mason, Veenstra & Long, Chem. Sci. 5, 32 (2014)).
- Heuristic: PLD ≥ 3.80 Å (CH4 must enter); maximise volumetric accessible surface area (m²/cm³) and void fraction.

## CO2 capture
- Physical basis: post-combustion flue gas has low CO2 partial pressure (about 0.15 bar), so affinity matters more than total surface area. Open metal sites bind CO2 strongly; MOF-74 analogues are the classic example (Britt, Furukawa, Wang, Glover & Yaghi, PNAS 106, 20637 (2009); Caskey, Wong-Foy & Matzger, J. Am. Chem. Soc. 130, 10870 (2008)). Narrow pores just above the CO2 size also strengthen adsorption.
- Heuristic: open metal site required; PLD ≥ 3.30 Å; maximise volumetric surface area and minimise largest cavity diameter (NSGA-II trade-off).
- Caveats: water competes for open metal sites, and many MOFs degrade in humid gas (Burtch, Jasuja & Walton, Chem. Rev. 114, 10575 (2014)). Stability is not in the dataset.

## Gas separation (size sieving)
- Heuristic: for gases A and B with kinetic diameters d_A < d_B, require d_A ≤ PLD ≤ d_B, then maximise void fraction. The user must name the gas pair (for example "separate CO2 from N2"). Without a pair, no window is applied.
- Caveat: many separations are adsorption-selective rather than size-selective.

## Heterogeneous catalysis
- Physical basis: coordinatively unsaturated (open) metal sites can act as Lewis-acid catalytic sites, and reactants must be able to reach them.
- Heuristic: open metal site required; PLD ≥ 5 Å; maximise surface area and PLD.
- Caveat: real catalytic activity depends on the reaction, the metal's oxidation state and stability, none of which are in the dataset.
