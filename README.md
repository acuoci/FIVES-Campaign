# FIVES Counterflow Diffusion Flame Campaign Tools

FIVES is a small workflow for preparing, running, monitoring, and post-processing
OpenSMOKE++ counterflow diffusion flame simulations.  The project is centered on
a C++ campaign generator (`CFDF.cpp`) and a Python post-processing module
(`postprocess_fives.py`).

The C++ program creates one simulation case for every requested combination of
the stream-composition parameters `alpha`, `beta`, and `gamma`.  For each case it
writes:

- `definition.json`, containing the stream velocities, temperatures,
  composition, strain rate, and geometric distance.
- One `StepXX/input.dic` file per available template in `templates/FUEL`.
- A case-level `Run.sh` script that executes the available steps in sequence.
- A campaign-level `RunAll.sh` script that runs multiple independent cases in
  parallel while respecting a user-specified number of available cores.
- A campaign summary CSV containing the same stream-definition data written to
  the JSON files.

The Python program reads completed campaign folders, imports OpenSMOKE++
profiles into pandas data structures, writes compact one-row-per-case metrics,
and generates heatmap-slice plots over the `alpha`, `beta`, and `gamma`
parameter space.

## Repository Layout

```text
.
|-- CFDF.cpp                    # C++ campaign generator
|-- postprocess_fives.py         # Python post-processing and plotting tools
|-- JobScript.sh                 # Example Sun Grid Engine job script
|-- templates/
|   |-- CH4/
|   |-- C2H4/
|   |-- C3H8/
|   `-- C7H8/
|       `-- stepN.template       # OpenSMOKE++ input templates
|-- examples/
|   `-- CH4/a_25/                # Example completed campaign data
`-- FUEL/a_STRAIN_RATE/          # Generated campaign folders
```

Generated campaign folders have this structure:

```text
FUEL/
`-- a_WWW/
    |-- RunAll.sh
    |-- Campaign.log
    |-- CampaignStatus.csv
    |-- Alpha_XXX_Beta_YYY_Gamma_ZZZ/
    |   |-- definition.json
    |   |-- Run.sh
    |   |-- Run.log
    |   |-- StepStatus.csv
    |   |-- Step01/
    |   |   |-- input.dic
    |   |   `-- Output/
    |   |       |-- Output.xml
    |   |       |-- Solution.final.out
    |   |       `-- Solution.soot.out        # optional
    |   `-- Step02/
    `-- ...
```

Here `WWW` is the strain rate in `1/s`, and `XXX`, `YYY`, and `ZZZ` are the
values of `alpha`, `beta`, and `gamma`.

## Physical Meaning of `alpha`, `beta`, and `gamma`

The `Calculate()` function in `CFDF.cpp` uses one unit mass of pure fuel as the
reference:

```cpp
m1f = 1.0
```

The parameters `alpha`, `beta`, and `gamma` define how steam and additional air
are added to the fuel and oxidizer streams.

### `alpha`: total steam addition

`alpha` is the total mass of steam added per unit mass of pure fuel:

```text
total added H2O = alpha * m1f
```

For example:

```text
alpha = 0.4
```

means that the total steam addition is:

```text
0.4 kg H2O / kg pure fuel
```

### `beta`: additional-air-to-steam ratio

`beta` controls the amount of additional air supplied together with the steam.
The total added air is:

```text
total added air = alpha * beta * m1f
```

For example, if:

```text
alpha = 0.4
beta  = 20
```

then:

```text
total added air = 0.4 * 20 = 8 kg air / kg pure fuel
```

If `alpha = 0`, no steam is added and no additional air is added through this
mechanism, so `beta` has no practical effect.

### `gamma`: split between fuel and oxidizer streams

`gamma` controls where the added steam and added air are injected:

```text
gamma       -> fraction sent to the fuel stream
1 - gamma   -> fraction sent to the oxidizer stream
```

Therefore:

```cpp
m1s = alpha * gamma * m1f              // steam on fuel side
m2s = alpha * (1 - gamma) * m1f        // steam on oxidizer side

m1a = alpha * beta * gamma * m1f       // added air on fuel side
m2a = alpha * beta * (1 - gamma) * m1f // added air on oxidizer side
```

Special cases:

- `gamma = 1`: all added steam and added air go to the fuel stream.
- `gamma = 0`: all added steam and added air go to the oxidizer stream.
- `gamma = 0.5`: the additions are split equally between the two streams.

### Air and oxidizer assumptions

Both the base oxidizer stream and the additional air are treated as regular air:

```text
Y_O2 = 0.232
Y_N2 = 0.768
```

The code assumes:

```text
MW_H2O = 18 kg/kmol
MW_air = 28.84 kg/kmol
```

### Velocity and strain-rate relation

The burner distance `L` is provided from the command line.  The default value is:

```text
L = 1.5 cm
```

The oxidizer-side velocity is imposed from the strain rate `a` and the distance
`L`:

```text
v2 = a * L / 4
```

The fuel-side velocity is then:

```text
v1 = R * v2
```

where `R = v1/v2` is solved iteratively because the stream molecular weights
depend on the stream compositions.

## Building the Campaign Generator

Compile the C++ program with a C++17 compiler:

```bash
g++ -std=c++17 -O2 CFDF.cpp -o cfdf
```

The investigated fuel, fuel molecular weight, strain rate, and burner distance
are command-line options.  Their default values are:

```text
fuel name               = C7H8
fuel molecular weight   = 92 kg/kmol
strain rate             = 25 1/s
distance L              = 1.5 cm
```

The template folder for the selected fuel must exist:

```text
templates/FUEL/
```

and must contain one or more files named:

```text
step1.template
step2.template
...
```

The generator automatically creates `Step01`, `Step02`, etc.  The width is at
least two digits.

## Running the Campaign Generator

The executable accepts the fuel definition, the strain rate, the burner
distance, and lists of values for `alpha`, `beta`, and `gamma`.  Each
`alpha`/`beta`/`gamma` list is comma-separated.  All possible combinations are
generated.

```bash
./cfdf --fuel CH4 \
       --fuel-mw 16 \
       --strain-rate 100 \
       --distance 1.5 \
       --alpha 0,0.2,0.4,0.6,0.8,1 \
       --beta 0,4,8,20 \
       --gamma 0,0.2,0.4,0.6,0.8,1 \
       --csv CFDF_results.csv
```

The equivalent `--option=value` syntax is also supported:

```bash
./cfdf --fuel=CH4 --fuel-mw=16 --strain-rate=100 --distance=1.5 \
       --alpha=0,0.5,1 --beta=0,8 --gamma=0,0.5,1
```

### Generator options

| Option | Meaning |
|---|---|
| `--fuel <name>`, `--fuel-name <name>` | Fuel name. The same name must exist under `templates/FUEL`. Default: `C7H8`. |
| `--fuel-mw <value>`, `--molecular-weight <value>`, `--mw <value>` | Pure-fuel molecular weight in `kg/kmol`. Default: `92`. |
| `--strain-rate <value>`, `--a <value>` | Counterflow strain rate in `1/s`. Default: `25`. |
| `--distance <value>`, `--L <value>` | Burner distance `L` in `cm`. Default: `1.5`. |
| `--alpha <values>` | Comma-separated list of `alpha` values. |
| `--beta <values>` | Comma-separated list of `beta` values. |
| `--gamma <values>` | Comma-separated list of `gamma` values. |
| `--csv <file>` | Name of the campaign-definition CSV file. Default: `CFDF_results.csv`. |
| `--help`, `-h` | Print usage information. |

If `NA`, `NB`, and `NG` values are provided for `alpha`, `beta`, and `gamma`,
the generator creates:

```text
NC = NA * NB * NG
```

independent cases.

## Generated Input Files and Placeholders

Each template file is copied into the corresponding `StepXX/input.dic` file.
The generator replaces placeholders enclosed in dollar signs using the values
computed by `Calculate()`.

Supported placeholders include:

| Placeholder | Meaning |
|---|---|
| `$VFUEL$` | Fuel-stream velocity, `cm/s`. |
| `$VOX$` | Oxidizer-stream velocity, `cm/s`. |
| `$TFUEL$` | Fuel-stream temperature, `K`. |
| `$TOX$` | Oxidizer-stream temperature, `K`. |
| `$ALPHA$` | Current `alpha` value. |
| `$BETA$` | Current `beta` value. |
| `$GAMMA$` | Current `gamma` value. |
| `$STRAINRATE$` | Current strain rate, `1/s`. |
| `$Y1FUEL$` | Fuel mass fraction in the fuel stream. |
| `$Y1H2O$` | H2O mass fraction in the fuel stream. |
| `$Y1O2$` | O2 mass fraction in the fuel stream. |
| `$Y1N2$` | N2 mass fraction in the fuel stream. |
| `$Y2H2O$` | H2O mass fraction in the oxidizer stream. |
| `$Y2O2$`, `$YO2$` | O2 mass fraction in the oxidizer stream. |
| `$Y2N2$` | N2 mass fraction in the oxidizer stream. |

## Running Simulations

### Running one case

Each case folder contains a `Run.sh` script:

```bash
cd FUEL/a_WWW/Alpha_XXX_Beta_YYY_Gamma_ZZZ
./Run.sh
```

`Run.sh` runs all `StepXX` folders in sequence using:

```bash
OpenSMOKEpp_CounterFlowFlame1D.sh
```

After every step, it reads:

```text
StepXX/Output/Output.xml
```

extracts the temperature profile from the `<profiles>` section, computes the
maximum temperature, and writes diagnostics.

If the maximum temperature is below:

```text
1000 K
```

the current case is marked as failed and the remaining steps of that same case
are not executed.  Other campaign cases are still allowed to continue when
launched through `RunAll.sh`.

Case-level diagnostics:

| File | Meaning |
|---|---|
| `Run.log` | Human-readable step-by-step log. |
| `Run.stdout` | Standard output captured by `RunAll.sh`. |
| `Run.stderr` | Standard error captured by `RunAll.sh`. |
| `StepStatus.csv` | Status of each step, including maximum temperature. |
| `status.txt` | Current or final case status. |
| `exit_code.txt` | Final case exit code. |
| `max_temperature_K.txt` | Last extracted maximum temperature. |
| `last_update.txt` | Last update timestamp. |

### Running a full campaign

The strain-rate folder contains `RunAll.sh`:

```bash
cd FUEL/a_WWW
./RunAll.sh NP
```

where `NP` is the number of independent cases allowed to run in parallel.

For example, to run at most 18 cases simultaneously:

```bash
./RunAll.sh 18
```

`RunAll.sh` schedules all generated cases, keeps at most `NP` active background
jobs, and continuously updates the campaign status.

Campaign-level diagnostics:

| File | Meaning |
|---|---|
| `Campaign.log` | Campaign-level log. |
| `CampaignStatus.csv` | Status table for all cases. |

The generated `Run.sh` and `RunAll.sh` files are marked executable by the C++
generator.  If files are copied to another machine and lose executable
permissions, run:

```bash
chmod +x RunAll.sh
find . -name Run.sh -exec chmod +x {} \;
```

### Example queue submission

A typical queue job should change to the campaign directory before launching
`RunAll.sh`.

```bash
#!/bin/bash
#$ -cwd
#$ -N FIVES_CH4
#$ -j y
#$ -S /bin/bash
#$ -l h_rt=240:00:00
#$ -q agri1.q
#$ -pe mpi 18
#$ -o output.log

set -u

export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export OMP_PROC_BIND=FALSE
export OMP_PLACES=cores

CAMPAIGN_DIR="/home/chimica2/cuoci/MyRuns/FIVES/CFDF/CH4/a_100"
cd "$CAMPAIGN_DIR"

chmod +x RunAll.sh
find . -name Run.sh -exec chmod +x {} \;

./RunAll.sh "${NSLOTS:-18}"
```

Adapt the module paths, queue name, and campaign directory to your cluster.

## Post-Processing Overview

`postprocess_fives.py` reads completed campaign results for one selected step.
It uses `CampaignStatus.csv` to identify the available simulations and imports
only the cases reported as successful.

The main OpenSMOKE++ file is:

```text
StepXX/Output/Solution.final.out
```

Optionally, if available, the soot file can also be read:

```text
StepXX/Output/Solution.soot.out
```

Both files are assumed to have a header line with entries such as:

```text
T[K](3)
CH4_w(210)
fv(tot)[-](7)
```

The parser extracts:

- clean variable name, for example `T`, `CH4_w`, or `fv(tot)`;
- unit, when available;
- original one-based column number;
- a unique pandas label.

## Python Dependencies

The post-processing tools require:

```bash
python3 -m pip install pandas numpy matplotlib
```

If you only load data and do not plot, `matplotlib` and `numpy` are not imported
until plotting is requested.

## Loading Campaign Data from Python

```python
from postprocess_fives import load_campaign_step

data = load_campaign_step(
    "examples/CH4/a_25",
    step="Step07",
    columns=["x", "T", "CH4_w", "O2_w"],
)

print(data.campaign_status)
print(data.columns)
print(data.profiles["Alpha_0.4_Beta_20_Gamma_0.4"])
```

To include soot data:

```python
data = load_campaign_step(
    "examples/CH4/a_25",
    step="Step07",
    columns=["x", "T"],
    include_soot=True,
    soot_columns=["fv(tot)", "N(tot)", "d32(agg)"],
)
```

Soot columns are prefixed by default with `soot_`, so `fv(tot)` becomes:

```text
soot_fv(tot)
```

### Main Python API

The most useful functions exposed by `postprocess_fives.py` are:

| Function | Purpose |
|---|---|
| `load_campaign_step(...)` | Read all successful cases for one selected step into pandas DataFrames. |
| `summarize_campaign_step(...)` | Convert loaded profiles into one-row-per-case metrics. |
| `write_campaign_step_metrics(...)` | Write those metrics to CSV. |
| `load_and_write_campaign_step_metrics(...)` | Convenience function combining loading and CSV writing. |
| `plot_metric_slices(...)` | Plot heatmap slices from an in-memory metrics DataFrame. |
| `plot_metric_slices_from_csv(...)` | Plot heatmap slices directly from an existing metrics CSV. |

Example using an existing metrics CSV:

```python
from postprocess_fives import plot_metric_slices_from_csv

plot_metric_slices_from_csv(
    "Step07_soot_metrics.csv",
    metric="soot_fv(tot)_max",
    fixed="gamma",
    output_file="Step07_soot_fv_max_by_gamma.png",
    cmap="magma",
    vmin=1e-22,
    vmax=1e-9,
    log_scale=True,
)
```

## Writing Metrics CSV Files

The metrics workflow writes one row per simulation.  For each selected variable,
it computes:

- maximum value;
- spatial location of the maximum;
- integral along the selected coordinate, usually `x`.

Cases that did not complete successfully are retained in the output and receive
`NaN` for all metric columns.

Example:

```bash
python3 postprocess_fives.py examples/CH4/a_25 \
    --step Step07 \
    --columns x,T,CH4_w,O2_w \
    --metrics-output Step07_metrics.csv \
    --summary
```

This creates columns such as:

```text
alpha,beta,gamma,T_max,T_x_at_max,T_integral,CH4_w_max,...
```

To include diagnostic status columns:

```bash
python3 postprocess_fives.py examples/CH4/a_25 \
    --step Step07 \
    --columns x,T \
    --metrics-output Step07_metrics_with_status.csv \
    --include-status
```

To process soot data:

```bash
python3 postprocess_fives.py examples/CH4/a_25 \
    --step Step07 \
    --columns x,T \
    --include-soot \
    --soot-columns 'fv(tot),N(tot)' \
    --metrics-output Step07_soot_metrics.csv
```

## Plotting Metrics

The plotting tool produces 2D heatmap slices through the three-dimensional
`alpha`/`beta`/`gamma` space.  One parameter is held fixed in each panel, and
the other two parameters define the axes.

Example:

```bash
python3 postprocess_fives.py examples/CH4/a_25 \
    --step Step07 \
    --columns x,T \
    --metrics-output Step07_metrics.csv \
    --plot-metric T_max \
    --plot-output Step07_Tmax_by_gamma.png \
    --plot-fixed gamma
```

This plots `T_max` as a function of `alpha` and `beta`, with one panel for each
value of `gamma`.

### Log-scale soot plot

```bash
python3 postprocess_fives.py examples/CH4/a_25 \
    --step Step07 \
    --columns x \
    --include-soot \
    --soot-columns 'fv(tot),N(tot)' \
    --metrics-output Step07_soot_metrics.csv \
    --plot-metric 'soot_fv(tot)_max' \
    --plot-output Step07_soot_fv_max_by_gamma.png \
    --plot-log \
    --plot-cmap magma \
    --plot-vmin 1e-22 \
    --plot-vmax 1e-9
```

For logarithmic plots, `--plot-vmin` and `--plot-vmax` must be positive.
Non-positive values are shown as gray cells, like missing or failed cases.

## Post-Processing Command-Line Options

| Option | Meaning |
|---|---|
| `campaign_directory` | Folder containing `CampaignStatus.csv`, for example `CH4/a_25`. |
| `--step STEP` | Step folder to read. Accepts `7`, `Step7`, or `Step07`. Default: `Step07`. |
| `--columns COLUMNS` | Comma-separated columns from `Solution.final.out`; accepts names, tags, or one-based numbers. |
| `--include-soot` | Also read `Solution.soot.out` when available. |
| `--soot-columns COLUMNS` | Comma-separated soot columns to read. |
| `--soot-prefix PREFIX` | Prefix added to soot labels. Default: `soot_`. |
| `--combine` | Build one stacked DataFrame in memory. Useful in Python workflows but potentially large. |
| `--missing {warn,ignore,raise}` | Behavior when a successful case is missing `Solution.final.out`. Default: `warn`. |
| `--missing-soot {warn,ignore,raise}` | Behavior when a successful case is missing `Solution.soot.out`. Default: `ignore`. |
| `--summary` | Print a compact loading summary. |
| `--metrics-output FILE` | Write one-row-per-simulation metrics to a CSV file. |
| `--metrics-variables VARIABLES` | Variables to summarize. Defaults to all loaded variables except the coordinate. |
| `--coordinate COORDINATE` | Coordinate used for locations and integrals. Default: `x`. |
| `--include-status` | Include case name, status, and exit code in the metrics CSV. |
| `--plot-metric METRIC` | Metric column to plot, for example `T_max` or `CH4_w_integral`. |
| `--plot-output FILE` | Output image file, for example `.png` or `.pdf`. |
| `--plot-fixed {alpha,beta,gamma}` | Parameter held fixed in each heatmap panel. Default: `gamma`. |
| `--plot-x {alpha,beta,gamma}` | Explicit heatmap x-axis parameter. |
| `--plot-y {alpha,beta,gamma}` | Explicit heatmap y-axis parameter. |
| `--plot-cmap NAME` | Matplotlib colormap name. Default: `viridis`. |
| `--plot-vmin VALUE` | Minimum color-scale value. |
| `--plot-vmax VALUE` | Maximum color-scale value. |
| `--plot-annotate` | Write metric values inside heatmap cells. |
| `--plot-log` | Use logarithmic color scaling. |

## Recommended Workflow

1. Prepare or verify the corresponding templates in `templates/FUEL`.
2. Compile the generator.
3. Generate the campaign folders by specifying fuel name, fuel molecular weight,
   strain rate, distance, and lists of `alpha`, `beta`, and `gamma`.
4. Confirm that `definition.json`, `input.dic`, `Run.sh`, and `RunAll.sh` were
   created in the expected campaign folders.
5. Move the generated campaign folder to the target machine if needed.
6. Submit the queue job from, or explicitly `cd` into, the campaign directory.
7. Monitor `CampaignStatus.csv`, `Campaign.log`, and case-level `Run.log` files.
8. Post-process a selected step using `postprocess_fives.py`.
9. Generate metrics CSV files and heatmap-slice plots.

## Notes and Limitations

- Stream temperatures are currently fixed in `Calculate()` at `293 K` for both
  streams.
- The oxidizer and added air are assumed to have the same composition and
  molecular weight.
- `RunAll.sh` treats each case as an independent serial job.  The `NP` argument
  controls how many cases are active at the same time.
- `Solution.soot.out` is optional.  Use `--missing-soot warn` or
  `--missing-soot raise` when you want stricter diagnostics.
- Large campaigns can contain many gigabytes of output.  Prefer loading only
  the columns needed for a given analysis.
