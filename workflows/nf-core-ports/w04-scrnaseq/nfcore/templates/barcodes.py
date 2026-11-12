#!/usr/bin/env python3

import os
import platform

import anndata as ad
import pandas as pd
import yaml

df = pd.read_csv(os.environ["NF_BARCODES"], header=None)
adata = ad.read_h5ad(os.environ["NF_H5AD"])

adata = adata[df[0].values]

adata.write_h5ad(f"{os.environ['NF_PREFIX']}.h5ad")

# Versions

versions = {
    os.environ["NF_PROCESS"]: {"python": platform.python_version(), "anndata": ad.__version__, "pandas": pd.__version__}
}

with open("versions.yml", "w") as f:
    yaml.dump(versions, f)
