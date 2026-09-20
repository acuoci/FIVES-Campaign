#!/bin/bash
#$ -cwd
#$ -N FIV_CH4
#$ -j y
#$ -S /bin/bash
#$ -l h_rt=240:00:00
#$ -q acch2.q
#$ -pe mpi 18
#$ -o output.log

# Queues available: agri1.q, cmic1.q, acch2.q

set -euo pipefail

NP="${NSLOTS:-18}"

if ! [[ "$NP" =~ ^[0-9]+$ ]] || [ "$NP" -lt 1 ]; then
    echo "Error: invalid number of slots: ${NP}" >&2
    exit 1
fi

# One OpenSMOKE++ process is launched per case. Keep each process single
# threaded so NP parallel cases use NP cores in total.
export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE

# GCC 13.2 runtime
export PATH="/software/chimica2/tools/gcc/gcc-13.2.0/bin:${PATH}"
export LD_LIBRARY_PATH="/software/chimica2/tools/gcc/gcc-13.2.0/lib:${LD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="/software/chimica2/tools/gcc/gcc-13.2.0/lib64:${LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH="/software/chimica2/libraries/mpfr/mpfr-4.2.1-gcc-12.2.0/lib:${LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH="/software/chimica2/libraries/gmp/gmp-6.3.0-gcc-12.2.0/lib:${LD_LIBRARY_PATH}"

# Boost 1.85.0
export LD_LIBRARY_PATH="/software/chimica2/libraries/boost/boost-1.85.0-gcc-13.2.0/lib:${LD_LIBRARY_PATH}"

# Intel MKL
export LD_LIBRARY_PATH="/software/chimica2/libraries/intel/oneapi/mkl/latest/lib/intel64:${LD_LIBRARY_PATH}"

# OpenSMOKE++ 0.23.0
export PATH="/software/chimica2/tools/opensmoke++/opensmoke++0.23.0/gcc-13.2.0/bin:${PATH}"
export LD_LIBRARY_PATH="/software/chimica2/tools/opensmoke++/opensmoke++0.23.0/gcc-13.2.0/lib:${LD_LIBRARY_PATH}"

# SUNDIALS
export LD_LIBRARY_PATH="/software/chimica2/libraries/sundials/sundials-7.1.1-opensmoke++/serial-gcc-13.2.0/lib64:${LD_LIBRARY_PATH}"

# SuiteSparse
export LD_LIBRARY_PATH="/software/chimica2/libraries/suitesparse/suitesparse-7.7.1-gcc-13.2.0/lib64:${LD_LIBRARY_PATH}"

# File transfers from local machines can drop executable permissions. Restore
# them inside the allocated job before checking or launching the scripts.
if [ -f "./RunAll.sh" ]; then
    chmod a+x ./RunAll.sh
fi

find . -mindepth 2 -maxdepth 2 -type f -name "Run.sh" -exec chmod a+x {} \;


# Check
if [ ! -x "./RunAll.sh" ]; then
    echo "Error: RunAll.sh was not found or is not executable in ${PWD}" >&2
    exit 1
fi

if ! command -v OpenSMOKEpp_CounterFlowFlame1D.sh >/dev/null 2>&1; then
    echo "Error: OpenSMOKEpp_CounterFlowFlame1D.sh was not found in PATH" >&2
    exit 1
fi

# Output on the screen
echo "Start parallel running"
echo "Working directory: ${PWD}"
echo "Host: $(hostname)"
echo "Queue: ${QUEUE:-unset}"
echo "Job ID: ${JOB_ID:-unset}"
echo "Job name: ${JOB_NAME:-unset}"
echo "NSLOTS: ${NSLOTS:-unset}"
echo "NP used by RunAll.sh: ${NP}"
echo "OMP_NUM_THREADS: ${OMP_NUM_THREADS}"
echo "OMP_DYNAMIC: ${OMP_DYNAMIC}"
echo "OpenSMOKE++ executable: $(command -v OpenSMOKEpp_CounterFlowFlame1D.sh)"
echo "Started at: $(date)"

./RunAll.sh "$NP"

echo "End parallel running"
echo "Finished at: $(date)"