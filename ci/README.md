# CI

We use [Dagger](https://docs.dagger.io/cli/465058/install/) for our CI piplines.

## Install

Dagger use buidkit for running containers. A docker up and running installation is mandatory to run ci piplines.

The CI pipline use the python module `dagger-io`

```bash
pip install dagger-io
```

## Run 🛠️

```bash
dagger run python ci.py
```
