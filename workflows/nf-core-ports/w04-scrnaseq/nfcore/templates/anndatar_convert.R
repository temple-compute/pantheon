#!/usr/bin/env Rscript

# to use nf variables: "${meta.id}"

# load libraries
library(anndataR)
library(SeuratObject)
library(SingleCellExperiment)

# read input
adata <- read_h5ad(Sys.getenv("NF_H5AD"))

# convert to Seurat
obj <- adata$as_Seurat()

# save files
dir.create(file.path(Sys.getenv("NF_ID")), showWarnings = FALSE)
saveRDS(obj, file = paste0(Sys.getenv("NF_ID"), "_", Sys.getenv("NF_INPUT_TYPE"), "_matrix.seurat.rds"))

# convert to SingleCellExperiment
obj <- adata$as_SingleCellExperiment()

# save files
dir.create(file.path(Sys.getenv("NF_ID")), showWarnings = FALSE)
saveRDS(obj, file = paste0(Sys.getenv("NF_ID"), "_", Sys.getenv("NF_INPUT_TYPE"), "_matrix.sce.rds"))

#
# save versions file
#
versions_file <- file("versions.yml")
write(
    paste(
        paste0(Sys.getenv("NF_PROCESS"), ":"),
        paste0('  r-base: "', R.Version()$version.string, '"'),
        paste0('  anndataR: "', as.character(packageVersion("anndataR")), '"'),
        paste0('  SeuratObject: "', as.character(packageVersion("SeuratObject")), '"'),
        paste0('  SingleCellExperiment: "', as.character(packageVersion("SingleCellExperiment")), '"'),
        sep = "\n"
    ),
    versions_file
)
close(versions_file)
