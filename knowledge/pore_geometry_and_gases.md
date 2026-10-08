# Pore geometry, kinetic diameters and molecular sieving

## Kinetic diameters of common gases
Kinetic diameters are the size parameters usually compared with pore apertures (values as commonly tabulated from D. W. Breck, Zeolite Molecular Sieves, Wiley, 1974; different sources differ by about 0.1 Å):
- H2O 2.65 Å
- H2 2.89 Å
- CO2 3.30 Å
- Ar 3.40 Å
- O2 3.46 Å
- Kr 3.60 Å
- N2 3.64 Å
- CO 3.76 Å
- CH4 3.80 Å
- Xe about 4.1 Å (some sources quote 3.96 Å)

## Which diameter matters for what
- The pore limiting diameter (PLD) decides whether a molecule can enter and diffuse through the framework. A MOF whose PLD is smaller than a gas's kinetic diameter is, to a first approximation, closed to that gas. Frameworks are flexible and molecules are not hard spheres, so molecules slightly larger than the PLD can sometimes still diffuse; treat the PLD test as a screening rule, not a guarantee.
- The largest cavity diameter (LCD) describes the size of the cages where molecules are stored. Smaller pores (only somewhat larger than the guest) give stronger overlap of the attractive potentials from opposite walls and therefore stronger adsorption at low pressure; larger pores give more capacity at high pressure.
- Void fraction and pore volume describe how much empty space there is; surface area describes how much wall the gas can adsorb on.

## Molecular sieving (size-selective separation)
For two gases A and B with kinetic diameters d_A < d_B, a MOF with d_A ≤ PLD ≤ d_B can let A through while excluding B. Examples:
- CO2/N2 (flue gas): 3.30 Å ≤ PLD ≤ 3.64 Å
- CO2/CH4 (natural gas or biogas upgrading): 3.30 Å ≤ PLD ≤ 3.80 Å
- H2/CH4: 2.89 Å ≤ PLD ≤ 3.80 Å
- Kr/Xe: 3.60 Å ≤ PLD ≤ 4.1 Å
Many real separations are driven by adsorption strength (thermodynamics) rather than size exclusion, so MOFs outside the window can still be selective. Confirming selectivity needs mixture adsorption simulations (for example GCMC with IAST) or experiments.

## Note on the probe used in this dataset
The CoRE-MOF descriptors here used a 3.31 Å probe. A MOF with PLD below 3.31 Å is reported with zero accessible surface area even though a smaller molecule such as H2 or H2O might still enter it.
